# -*- coding: utf-8 -*-
"""工时报工系统 - 主应用 (MySQL异步版本)"""
import sys

# Windows 控制台默认 GBK，代码中大量 emoji print 会触发 UnicodeEncodeError 导致启动崩溃。
# 在入口处统一把标准输出/错误重配为 UTF-8（覆盖整个进程的所有 print）。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass

import tornado.ioloop
import tornado.web
import tornado.escape
import json
import os
import re
import time
import base64
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
import requests
import urllib3
from sqlalchemy import select, update, and_, delete as sqla_delete
import asyncio

# 导入配置和模型
from config import APP_CONFIG, DB_CONFIG, ACCESS_USER, ACCESS_PASSWORD, ACCESS_SALT, DEFAULT_WORK_CONTENT
from models import UserConfig, WorkRecord
from utils.excel_helper import export_records_to_excel, import_records_from_excel
from utils import db
from utils.logger import logger, log_api_call, log_db_operation, log_error, log_business, log_report

urllib3.disable_warnings()

# 东八区：报工时间戳显式按 Asia/Shanghai 计算，避免服务器时区(如UTC)导致日期错位
CST = timezone(timedelta(hours=8))


def date_to_ms(d):
    """某日 00:00（东八区）的毫秒时间戳"""
    return int(datetime.combine(d, datetime.min.time(), tzinfo=CST).timestamp() * 1000)


def identity_from_token(authorization):
    """从 Authorization(JWT) 解析稳定身份。
    返回 (user_id, user_name)，解析失败返回 (None, None)。
    注意：只解码 payload，不校验签名（过期 token 也能解析出身份）。
    """
    if not authorization:
        return None, None
    token = authorization.strip()
    if token.lower().startswith('bearer '):
        token = token[7:].strip()
    try:
        parts = token.split('.')
        if len(parts) < 2:
            return None, None
        payload = parts[1]
        payload += '=' * (-len(payload) % 4)  # 补齐 base64 padding
        data = json.loads(base64.urlsafe_b64decode(payload))
        uid = str(data.get('user_id') or '').strip()
        uname = str(data.get('user_name') or '').strip()
        return (uid or None), (uname or None)
    except Exception:
        return None, None


def exp_from_token(authorization):
    """从 JWT 解析 exp（毫秒时间戳），失败返回 None。用于前端认证过期提醒。"""
    if not authorization:
        return None
    token = authorization.strip()
    if token.lower().startswith('bearer '):
        token = token[7:].strip()
    try:
        parts = token.split('.')
        if len(parts) < 2:
            return None
        payload = parts[1] + '=' * (-len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        exp = data.get('exp')
        return int(exp) if exp is not None else None
    except Exception:
        return None


# 访问令牌：登录成功后下发「带签发时间戳 + HMAC 签名」的令牌，受保护接口校验签名+有效期（全局共享密码门禁）
ACCESS_TTL = 24 * 3600  # 门禁登录有效期(秒)：超过则需重新登录。要改时长改这里即可
_ACCESS_SECRET = f"{ACCESS_USER}:{ACCESS_PASSWORD}:{ACCESS_SALT}".encode()


def make_access_token():
    """生成门禁令牌：base64(签发时间戳.hmac签名)。每次登录都不同（含当时时间戳）。"""
    ts = str(int(time.time()))
    sig = hmac.new(_ACCESS_SECRET, ts.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{ts}.{sig}".encode()).decode()


def verify_access_token(token):
    """校验门禁令牌：签名正确 且 距签发未超过 ACCESS_TTL。"""
    if not token:
        return False
    try:
        ts, sig = base64.urlsafe_b64decode(token.encode()).decode().split('.', 1)
        expect = hmac.new(_ACCESS_SECRET, ts.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expect):
            return False
        return (int(time.time()) - int(ts)) <= ACCESS_TTL
    except Exception:
        return False


class CorsBase(tornado.web.RequestHandler):
    """统一 CORS 头 + OPTIONS 预检"""

    def set_default_headers(self):
        self.set_header('Content-Type', 'application/json; charset=UTF-8')
        self.set_header('Access-Control-Allow-Origin', '*')
        self.set_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.set_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Access-Token')

    def options(self, *args):
        self.set_status(204)
        self.finish()


class LoginHandler(CorsBase):
    """登录：校验全局账号密码，下发访问令牌（不需要令牌即可访问）"""

    async def post(self):
        try:
            data = tornado.escape.json_decode(self.request.body or b'{}')
            username = (data.get('username') or '').strip()
            password = data.get('password') or ''
            if username == ACCESS_USER and password == ACCESS_PASSWORD:
                log_business('登录', username, '成功')
                self.write({'success': True, 'token': make_access_token()})
            else:
                log_business('登录', username or '(空)', '失败')
                self.set_status(401)
                self.write({'success': False, 'message': '账号或密码错误'})
        except Exception as e:
            self.set_status(400)
            self.write({'success': False, 'message': f'登录请求异常: {str(e)}'})


class BaseHandler(CorsBase):
    """业务基类：所有数据接口都要先过访问令牌校验"""

    def prepare(self):
        # 预检放行
        if self.request.method == 'OPTIONS':
            return
        # 令牌来自请求头；导出/上传等无法带头的场景用 ?access= 查询参数
        token = self.request.headers.get('X-Access-Token') or self.get_argument('access', '')
        if not verify_access_token(token):
            self.set_status(401)
            self.finish({'success': False, 'message': '未登录或登录已过期'})

    def get_current_user(self):
        """获取当前用户名（业务身份，来自 token 解析后存的 user_id）"""
        username = self.get_argument('username', None)
        if not username:
            username = self.get_cookie('username', 'default_user')
        return username


class ConfigHandler(BaseHandler):
    """配置管理"""
    
    async def get(self):
        """获取用户配置"""
        try:
            username = self.get_current_user()
            log_api_call('ConfigHandler', 'GET', {'username': username})
            
            async with db.async_session_maker() as session:
                result = await session.execute(
                    select(UserConfig).where(UserConfig.username == username)
                )
                user_config = result.scalar_one_or_none()
                
                if user_config:
                    template_data = json.loads(user_config.template_data) if user_config.template_data else None
                    _, display_name = identity_from_token(user_config.authorization)
                    log_business('读取配置', username, f'配置存在')

                    can_submit = bool(user_config.curl_template and 'reportWorkingHours' in user_config.curl_template and user_config.template_data)
                    self.write({
                        'success': True,
                        'username': username,
                        'display_name': display_name or username,
                        'can_submit': can_submit,
                        'token_exp': exp_from_token(user_config.authorization),
                        'config': {
                            'curl_template': user_config.curl_template or '',
                            'authorization': user_config.authorization or '',
                            'cookie': user_config.cookie or ''
                        },
                        'parsed': {
                            'authorization': user_config.authorization or '',
                            'cookie': user_config.cookie or '',
                            'template_data': template_data
                        }
                    })
                else:
                    self.write({
                        'success': True,
                        'config': {'curl_template': '', 'authorization': '', 'cookie': ''},
                        'parsed': {'authorization': '', 'cookie': '', 'template_data': None}
                    })
        except Exception as e:
            log_error('ConfigHandler.get', str(e))
            self.write({'success': False, 'message': str(e)})
    
    async def post(self):
        """保存配置"""
        try:
            data = tornado.escape.json_decode(self.request.body)
            curl_template = data.get('curl_template', '')

            # 解析curl命令
            authorization = ''
            cookie = ''
            template_data = None
            url = ''
            
            if curl_template:
                auth_match = re.search(r"-H\s+'Authorization:\s*([^']+)'", curl_template)
                authorization = auth_match.group(1).strip() if auth_match else ''
                
                cookie_match = re.search(r"-b\s+'([^']+)'", curl_template)
                cookie = cookie_match.group(1).strip() if cookie_match else ''
                
                url_match = re.search(r"curl\s+'([^']+)'", curl_template)
                url = url_match.group(1).strip() if url_match else ''
                
                data_match = re.search(r"--data-raw\s+'({[\s\S]*?})'\s", curl_template)
                if data_match:
                    template_data = json.loads(data_match.group(1))

            # 用 token 内的 user_id 作为多用户隔离键（零登录自动身份）
            user_id, display_name = identity_from_token(authorization)
            if not user_id:
                self.write({'success': False, 'message': '无法从 Authorization(token) 解析用户身份，请确认粘贴的 curl 含有效的 Authorization'})
                return
            username = user_id
            log_api_call('ConfigHandler', 'POST', {'username': username, 'display_name': display_name})

            async with db.async_session_maker() as session:
                result = await session.execute(
                    select(UserConfig).where(UserConfig.username == username)
                )
                user_config = result.scalar_one_or_none()
                
                if user_config:
                    user_config.curl_template = curl_template
                    user_config.authorization = authorization
                    user_config.cookie = cookie
                    user_config.template_data = json.dumps(template_data, ensure_ascii=False) if template_data else None
                else:
                    user_config = UserConfig(
                        username=username,
                        curl_template=curl_template,
                        authorization=authorization,
                        cookie=cookie,
                        template_data=json.dumps(template_data, ensure_ascii=False) if template_data else None
                    )
                    session.add(user_config)
                
                await session.commit()
            
            log_business('保存配置', username, f'Authorization已解析')
            log_db_operation('INSERT/UPDATE', 'user_configs', {'username': username})
            
            can_submit = bool(curl_template and 'reportWorkingHours' in curl_template and template_data)
            self.write({
                'success': True,
                'message': '配置保存成功',
                'username': username,
                'display_name': display_name or username,
                'can_submit': can_submit,
                'parsed': {
                    'authorization': authorization,
                    'cookie': cookie,
                    'url': url,
                    'template_data': template_data
                }
            })
        except Exception as e:
            log_error('ConfigHandler.post', f'保存失败: {str(e)}')
            self.write({'success': False, 'message': f'保存失败: {str(e)}'})


class RecordsHandler(BaseHandler):
    """记录管理"""
    
    async def get(self):
        """获取记录列表和统计"""
        try:
            username = self.get_current_user()
            log_api_call('RecordsHandler', 'GET', {'username': username})
            
            async with db.async_session_maker() as session:
                result = await session.execute(
                    select(WorkRecord)
                    .where(WorkRecord.username == username)
                    .order_by(WorkRecord.work_date.desc())
                )
                records = result.scalars().all()
                
                total_normal = 0.0
                total_overtime = 0.0
                record_list = []
                
                for record in records:
                    total_normal += record.normal_hours
                    total_overtime += record.overtime_hours

                    record_list.append({
                        'id': record.id,
                        'date': record.work_date.strftime('%Y-%m-%d'),
                        'normal_hours': record.normal_hours,
                        'overtime_hours': record.overtime_hours,
                        'avail_normal': record.avail_normal,
                        'avail_overtime': record.avail_overtime,
                        'work_content': record.work_content or '',
                        'status': record.status,
                        'created_at': record.created_at.strftime('%Y-%m-%d %H:%M:%S') if record.created_at else ''
                    })
                
                total_hours = total_normal + total_overtime
                person_days = total_hours / 8.0
                person_months = person_days / 21.75
                
                statistics = {
                    'total_normal_hours': round(total_normal, 2),
                    'total_overtime_hours': round(total_overtime, 2),
                    'total_hours': round(total_hours, 2),
                    'person_days': round(person_days, 2),
                    'person_months': round(person_months, 2)
                }
                
                log_business('查询记录', username, f'返回{len(record_list)}条记录')
                
                self.write({
                    'success': True,
                    'data': record_list,
                    'statistics': statistics
                })
        except Exception as e:
            log_error('RecordsHandler.get', str(e))
            self.write({'success': False, 'message': str(e)})
    
    async def put(self):
        """更新单条记录"""
        try:
            username = self.get_current_user()
            data = tornado.escape.json_decode(self.request.body)
            record_id = data.get('id')
            log_api_call('RecordsHandler', 'PUT', {'username': username, 'record_id': record_id})
            normal_hours = float(data.get('normal_hours', 0))
            overtime_hours = float(data.get('overtime_hours', 0))
            work_content = data.get('work_content', '')

            async with db.async_session_maker() as session:
                result = await session.execute(
                    select(WorkRecord).where(and_(
                        WorkRecord.id == record_id,
                        WorkRecord.username == username
                    ))
                )
                record = result.scalar_one_or_none()
                if not record:
                    self.write({'success': False, 'message': '记录不存在'})
                    return

                # 校验：不能小于 0
                if normal_hours < -1e-6 or overtime_hours < -1e-6:
                    self.write({'success': False, 'message': '工时不能小于 0'})
                    return
                # 校验：单项封顶 8 小时
                if normal_hours > 8 + 1e-6:
                    self.write({'success': False, 'message': '正常工时不能超过 8 小时'})
                    return
                if overtime_hours > 8 + 1e-6:
                    self.write({'success': False, 'message': '加班工时不能超过 8 小时'})
                    return
                # 校验：不能超过当天可填报上限
                if record.avail_normal is not None and normal_hours > record.avail_normal + 1e-6:
                    self.write({'success': False, 'message': f'正常工时不能超过可填报上限 {record.avail_normal}'})
                    return
                if record.avail_overtime is not None and overtime_hours > record.avail_overtime + 1e-6:
                    self.write({'success': False, 'message': f'加班工时不能超过可填报上限 {record.avail_overtime}'})
                    return

                record.normal_hours = normal_hours
                record.overtime_hours = overtime_hours
                record.work_content = work_content
                await session.commit()

            log_business('更新记录', username, f'ID:{record_id}, 正常:{normal_hours}h, 加班:{overtime_hours}h, 内容:{work_content}')
            log_db_operation('UPDATE', 'work_records', affected_rows=1)
            
            self.write({'success': True, 'message': '记录更新成功'})
        except Exception as e:
            log_error('RecordsHandler.put', str(e))
            self.write({'success': False, 'message': str(e)})

    async def delete(self):
        """删除记录（仅删本地 MySQL，不影响已提交到原系统的数据）。支持 {id} 或 {ids:[...]}"""
        try:
            username = self.get_current_user()
            data = tornado.escape.json_decode(self.request.body or b'{}')
            ids = data.get('ids')
            if not ids and data.get('id') is not None:
                ids = [data.get('id')]
            log_api_call('RecordsHandler', 'DELETE', {'username': username, 'count': len(ids or [])})
            if not ids:
                self.write({'success': False, 'message': '没有要删除的记录'})
                return

            async with db.async_session_maker() as session:
                res = await session.execute(
                    sqla_delete(WorkRecord).where(and_(
                        WorkRecord.username == username,
                        WorkRecord.id.in_(ids)
                    ))
                )
                await session.commit()
                n = res.rowcount or 0

            log_business('删除记录', username, f'{n}条')
            log_db_operation('DELETE', 'work_records', affected_rows=n)
            self.write({'success': True, 'count': n, 'message': f'已删除 {n} 条'})
        except Exception as e:
            log_error('RecordsHandler.delete', str(e))
            self.write({'success': False, 'message': str(e)})


class BatchUpdateHandler(BaseHandler):
    """批量改整列：正常工时 / 加班工时 / 工作内容（工时自动按每天可填上限+8小时封顶、不小于0）"""

    async def post(self):
        try:
            username = self.get_current_user()
            data = tornado.escape.json_decode(self.request.body)
            field = data.get('field')          # normal | overtime | content
            value = data.get('value')
            ids = data.get('ids', [])
            log_api_call('BatchUpdateHandler', 'POST', {'username': username, 'field': field, 'count': len(ids)})

            if field not in ('normal', 'overtime', 'content'):
                self.write({'success': False, 'message': '非法字段'})
                return
            if not ids:
                self.write({'success': False, 'message': '没有要更新的记录'})
                return

            n = 0
            async with db.async_session_maker() as session:
                result = await session.execute(
                    select(WorkRecord).where(and_(
                        WorkRecord.username == username,
                        WorkRecord.id.in_(ids)
                    ))
                )
                records = result.scalars().all()
                for record in records:
                    if field == 'content':
                        record.work_content = str(value or '')
                    else:
                        try:
                            v = float(value or 0)
                        except Exception:
                            continue
                        v = max(0.0, min(v, 8.0))   # 夹到 [0, 8]
                        if field == 'normal':
                            cap = record.avail_normal if record.avail_normal is not None else 8.0
                            record.normal_hours = min(v, cap)   # 再按当天可填上限封顶
                        else:
                            cap = record.avail_overtime if record.avail_overtime is not None else 8.0
                            record.overtime_hours = min(v, cap)
                    n += 1
                await session.commit()

            log_business('批量更新', username, f'字段{field}, {n}条')
            log_db_operation('UPDATE', 'work_records', affected_rows=n)
            self.write({'success': True, 'count': n, 'message': f'已批量更新 {n} 条'})
        except Exception as e:
            log_error('BatchUpdateHandler.post', str(e))
            self.write({'success': False, 'message': f'批量更新失败: {str(e)}'})


class ExcelExportHandler(BaseHandler):
    """Excel导出"""
    
    async def get(self):
        """导出Excel"""
        try:
            username = self.get_current_user()
            log_api_call('ExcelExportHandler', 'GET', {'username': username})
            
            async with db.async_session_maker() as session:
                result = await session.execute(
                    select(WorkRecord)
                    .where(WorkRecord.username == username)
                    .order_by(WorkRecord.work_date.desc())
                )
                records = result.scalars().all()
                
                record_list = []
                for record in records:
                    record_list.append({
                        'id': record.id,
                        'date': record.work_date.strftime('%Y-%m-%d'),
                        'normal_hours': record.normal_hours,
                        'overtime_hours': record.overtime_hours,
                        'work_content': record.work_content or '',
                        'status': record.status,
                        'created_at': record.created_at.strftime('%Y-%m-%d %H:%M:%S') if record.created_at else ''
                    })
            
            excel_file = export_records_to_excel(record_list)
            
            self.set_header('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            self.set_header('Content-Disposition', f'attachment; filename="worktime_{username}_{datetime.now().strftime("%Y%m%d")}.xlsx"')
            
            log_business('导出Excel', username, f'导出{len(record_list)}条记录')
            
            self.write(excel_file.getvalue())
        
        except Exception as e:
            log_error('ExcelExportHandler.get', str(e))
            self.set_header('Content-Type', 'application/json')
            self.write({'success': False, 'message': str(e)})


class ExcelImportHandler(BaseHandler):
    """Excel导入"""
    
    async def post(self):
        """导入Excel"""
        try:
            username = self.get_current_user()
            log_api_call('ExcelImportHandler', 'POST', {'username': username})
            
            if 'file' not in self.request.files:
                self.write({'success': False, 'message': '请上传Excel文件'})
                return
            
            file_info = self.request.files['file'][0]
            excel_data = file_info['body']
            
            import io
            excel_file = io.BytesIO(excel_data)
            records = import_records_from_excel(excel_file)
            
            async with db.async_session_maker() as session:
                updated_count = 0
                for record in records:
                    await session.execute(
                        update(WorkRecord)
                        .where(and_(
                            WorkRecord.id == record['id'],
                            WorkRecord.username == username
                        ))
                        .values(
                            normal_hours=record['normal_hours'],
                            overtime_hours=record['overtime_hours'],
                            work_content=record.get('work_content', '')
                        )
                    )
                    updated_count += 1
                
                await session.commit()
            
            log_business('导入Excel', username, f'更新{updated_count}条记录')
            log_db_operation('UPDATE', 'work_records', affected_rows=updated_count)
            
            self.write({
                'success': True,
                'message': f'成功导入并更新 {updated_count} 条记录'
            })
        
        except Exception as e:
            log_error('ExcelImportHandler.post', f'导入失败: {str(e)}')
            self.write({'success': False, 'message': f'导入失败: {str(e)}'})


class CustomWorktimeHandler(BaseHandler):
    """自定义工时（批量设置）"""

    async def post(self):
        try:
            username = self.get_current_user()
            print(f"收到请求: CustomWorktimeHandler")
            print(f"请求体: {self.request.body}")
            data = tornado.escape.json_decode(self.request.body)
            print(f"解析后的数据: {data}")
            start_date_str = data.get('start_date')
            end_date_str = data.get('end_date')
            normal_hours = float(data.get('normal_hours', 0))
            overtime_hours = float(data.get('overtime_hours', 0))
            work_content = data.get('work_content', '')
            include_weekend = bool(data.get('include_weekend', False))
            
            print(f"用户: {username}")
            print(f"日期范围: {start_date_str} ~ {end_date_str}")
            print(f"⏰ 工时: 正常={normal_hours}, 加班={overtime_hours}, 包含周末={include_weekend}")
            
            log_api_call('CustomWorktimeHandler', 'POST', {
                'username': username,
                'start_date': start_date_str,
                'end_date': end_date_str,
                'normal_hours': normal_hours,
                'overtime_hours': overtime_hours,
                'include_weekend': include_weekend,
                'work_content': work_content
            })
            
            if not start_date_str or not end_date_str:
                self.write({'success': False, 'message': '请提供开始和结束日期'})
                return
            
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            if end_date < start_date:
                self.write({'success': False, 'message': '结束日期不能早于开始日期'})
                return
            
            updated = 0
            inserted = 0
            async with db.async_session_maker() as session:
                current_date = start_date
                while current_date <= end_date:
                    if include_weekend or current_date.weekday() < 5:
                        existing = await session.execute(
                            select(WorkRecord).where(and_(
                                WorkRecord.username == username,
                                WorkRecord.work_date == current_date
                            ))
                        )
                        record = existing.scalar_one_or_none()
                        if record:
                            record.normal_hours = normal_hours
                            record.overtime_hours = overtime_hours
                            record.work_content = work_content
                            updated += 1
                        else:
                            new_record = WorkRecord(
                                username=username,
                                work_date=current_date,
                                normal_hours=normal_hours,
                                overtime_hours=overtime_hours,
                                work_content=work_content,
                                status='pending'
                            )
                            session.add(new_record)
                            inserted += 1
                    current_date += timedelta(days=1)
                await session.commit()
            
            log_business('自定义工时', username, f'新增{inserted}条，更新{updated}条，范围{start_date}至{end_date}')
            log_db_operation('INSERT/UPDATE', 'work_records', affected_rows=inserted + updated)
            print(f"成功: 新增{inserted}条，更新{updated}条")
            self.write({'success': True, 'message': f'已处理 {inserted + updated} 条（新增 {inserted}，更新 {updated}）'})
        except Exception as e:
            print(f"错误: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            log_error('CustomWorktimeHandler.post', f'自定义工时失败: {str(e)}')
            self.write({'success': False, 'message': f'自定义工时失败: {str(e)}'})


class QueryWorktimeHandler(BaseHandler):
    """查询可填报工时（只查询，不写库）——对应 get_data_work_time.py"""

    async def post(self):
        try:
            username = self.get_current_user()
            data = tornado.escape.json_decode(self.request.body)
            start_date_str = data.get('start_date')
            end_date_str = data.get('end_date')

            log_api_call('QueryWorktimeHandler', 'POST', {
                'username': username,
                'start_date': start_date_str,
                'end_date': end_date_str
            })

            if not start_date_str or not end_date_str:
                self.write({'success': False, 'message': '请提供开始和结束日期'})
                return

            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            if end_date < start_date:
                self.write({'success': False, 'message': '结束日期不能早于开始日期'})
                return

            async with db.async_session_maker() as session:
                result = await session.execute(
                    select(UserConfig).where(UserConfig.username == username)
                )
                user_config = result.scalar_one_or_none()

                if not user_config or not user_config.authorization:
                    self.write({'success': False, 'message': '请先配置认证信息'})
                    return

                headers = {
                    'Accept': 'application/json, text/plain, */*',
                    'Accept-Language': 'zh-CN,zh;q=0.9',
                    'Authorization': user_config.authorization,
                    'Connection': 'keep-alive',
                    'Cookie': user_config.cookie or '',
                    'Referer': 'http://xiaokong.cfid.cn/home',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'fz-origin': 'pc'
                }

            # 查询范围内所有日期（含周末/节假日）：让前端能看到每天真实可报工时，
            # 周末/节假日是否可填由它返回的工时决定（>0 才可手动加班填报）
            # 查询范围内所有日期(含周末/节假日)：并发拉取，去掉串行+sleep。
            # xiaokong 吞吐天花板~6.5req/s、并发8是甜蜜点(实测)；一个月 ~40s → ~5s。
            days = []
            d = start_date
            while d <= end_date:
                days.append(d)
                d += timedelta(days=1)

            mock = os.environ.get('WT_MOCK') == '1'
            sem = asyncio.Semaphore(8)

            async def fetch_day(cur):
                row = {'date': cur.strftime('%Y-%m-%d'), 'normal_hours': '',
                       'overtime_hours': '', 'status': 'error', 'error': ''}
                if mock:
                    wd = cur.weekday(); dn = cur.day
                    if wd < 5:
                        if dn % 10 == 0:
                            row['normal_hours'] = '0.0'; row['overtime_hours'] = '0.0'
                        else:
                            row['normal_hours'] = '8.0' if dn % 7 != 0 else '4.0'
                            row['overtime_hours'] = '2.0' if dn % 5 == 0 else '0.0'
                    else:
                        row['normal_hours'] = '0.0'; row['overtime_hours'] = '4.0'
                    row['status'] = 'success'
                    return row
                async with sem:
                    timestamp_ms = date_to_ms(cur)
                    now_ts = int(time.time())
                    url = f"http://xiaokong.cfid.cn/api/example/Gstb/getInitMsg/0/{timestamp_ms}?n={now_ts}"
                    try:
                        response = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10, verify=False)
                        data_obj = response.json().get("data", {})
                        row['normal_hours'] = data_obj.get("ktbGs", "")
                        row['overtime_hours'] = data_obj.get("ktbJbGs", "")
                        row['status'] = 'success'
                    except Exception as e:
                        row['error'] = str(e)
                return row

            results = list(await asyncio.gather(*[fetch_day(dd) for dd in days]))

            success_days = sum(1 for r in results if r['status'] == 'success')
            log_business('查询工时', username, f'查询{len(results)}天，成功{success_days}天')

            self.write({'success': True, 'data': results})

        except Exception as e:
            log_error('QueryWorktimeHandler.post', f'查询失败: {str(e)}')
            self.write({'success': False, 'message': f'查询失败: {str(e)}'})


async def submit_one(url, headers, submit_data, sem):
    """提交单条报工到上游，返回 (ok, err)。受信号量限并发；只做网络IO、不碰 DB session。

    WT_MOCK=1 时不打真上游，模拟 ~1s 耗时并按 gstbZcgz 判定成败（>8 视为失败，
    复刻真实「填报工时大于8小时」的拒绝），用于本地无内网时验证并发逻辑。生产别设。
    """
    async with sem:
        if os.environ.get('WT_MOCK') == '1':
            await asyncio.sleep(1.0)  # 模拟上游单次 ~1s
            try:
                zc = float(submit_data.get('gstbZcgz', 0))
            except (TypeError, ValueError):
                zc = 0
            if zc > 8:
                return False, '400 填报工时大于8小时'
            return True, ''

        response = await asyncio.to_thread(
            requests.post, url, headers=headers, json=submit_data, timeout=10, verify=False
        )
    ok = False
    err = ''
    if response.status_code == 200:
        # 仅 HTTP 200 不够：还要看响应体里的业务 code/success
        try:
            body = response.json()
            if 'code' in body:
                ok = str(body.get('code')) in ('200', '0')
                if not ok:
                    err = f"{body.get('code')} {body.get('msg', '')}".strip()
            elif 'success' in body:
                ok = bool(body.get('success'))
                if not ok:
                    err = body.get('message') or body.get('msg', '')
            else:
                ok = True  # 无可识别字段，宽松视为成功
        except Exception:
            ok = True  # 200 但非 JSON，视为成功
    else:
        err = f'HTTP {response.status_code}'
    return ok, err


class SubmitHandler(BaseHandler):
    """提交报工"""

    async def post(self):
        """批量提交报工"""
        try:
            username = self.get_current_user()
            data = tornado.escape.json_decode(self.request.body)
            record_ids = data.get('record_ids', [])
            log_api_call('SubmitHandler', 'POST', {'username': username, 'record_count': len(record_ids)})
            
            if not record_ids:
                self.write({'success': False, 'message': '请选择要提交的记录'})
                return
            
            async with db.async_session_maker() as session:
                result = await session.execute(
                    select(UserConfig).where(UserConfig.username == username)
                )
                user_config = result.scalar_one_or_none()
                
                if not user_config or not user_config.authorization:
                    self.write({'success': False, 'message': '请先配置认证信息'})
                    return
                
                # 提交报工必须用 reportWorkingHours 的 cURL（含提交地址 + 任务模板）
                if (not user_config.curl_template
                        or 'reportWorkingHours' not in user_config.curl_template
                        or not user_config.template_data):
                    self.write({'success': False, 'message': '当前配置只能查询、不能提交报工，请用 reportWorkingHours 的 cURL 重新配置'})
                    return

                url_match = re.search(r"curl\s+'([^']+)'", user_config.curl_template)
                url = url_match.group(1) if url_match else ''

                template_data = json.loads(user_config.template_data) if user_config.template_data else {}
                
                headers = {
                    'Accept': 'application/json, text/plain, */*',
                    'Authorization': user_config.authorization,
                    'Content-Type': 'application/json;charset=UTF-8',
                    'Cookie': user_config.cookie or '',
                    'Origin': 'http://xiaokong.cfid.cn',
                    'Referer': 'http://xiaokong.cfid.cn/home',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'fz-origin': 'pc'
                }
                
                success_count = 0
                failed_count = 0
                results = []

                # ① 先串行从库里把记录取出 + 构造好提交体（DB 访问不并发，避免 async session 冲突）
                tasks = []   # [(record, submit_data, date_str)]
                for record_id in record_ids:
                    result = await session.execute(
                        select(WorkRecord).where(and_(
                            WorkRecord.id == record_id,
                            WorkRecord.username == username
                        ))
                    )
                    record = result.scalar_one_or_none()

                    if not record:
                        results.append({'id': record_id, 'status': 'failed', 'error': '记录不存在'})
                        failed_count += 1
                        continue

                    submit_data = template_data.copy()
                    # 懒人模式模板带 _jhKsDate/_jhJsDate：按报工日算 gstbRwjz(报工日在计划期内=1/否则0)，发请求前删辅助字段
                    ks = submit_data.pop('_jhKsDate', '')
                    js = submit_data.pop('_jhJsDate', '')
                    bg_date = record.work_date.strftime('%Y-%m-%d')
                    if ks and js:
                        submit_data['gstbRwjz'] = '1' if ks <= bg_date <= js else '0'
                    submit_data['gstbZcgz'] = str(record.normal_hours)
                    submit_data['gstbPtjb'] = str(record.overtime_hours)
                    submit_data['gstbBgsj'] = date_to_ms(record.work_date)

                    date_str = record.work_date.strftime('%Y-%m-%d')
                    tasks.append((record, submit_data, date_str))

                # ② 并发发请求（信号量限并发，上游最佳并发~8，这里取5较稳），只做网络IO、不碰 session
                sem = asyncio.Semaphore(5)
                outcomes = await asyncio.gather(
                    *(submit_one(url, headers, sd, sem) for (_, sd, _) in tasks),
                    return_exceptions=True
                )

                # ③ 串行回写状态 + 计数（按 record_ids 原顺序）
                for (record, _submit_data, date_str), outcome in zip(tasks, outcomes):
                    if isinstance(outcome, Exception):
                        print(f"提交记录 {record.id} 失败: {outcome}")
                        record.status = 'failed'
                        failed_count += 1
                        results.append({'id': record.id, 'date': date_str, 'status': 'failed', 'error': str(outcome)})
                        log_report(username, date_str, record.normal_hours, record.overtime_hours, 'error', str(outcome))
                        continue

                    ok, err = outcome
                    if ok:
                        record.status = 'submitted'
                        success_count += 1
                        results.append({'id': record.id, 'date': date_str, 'status': 'success', 'error': ''})
                        log_report(username, date_str, record.normal_hours, record.overtime_hours, 'success')
                    else:
                        record.status = 'failed'
                        failed_count += 1
                        results.append({'id': record.id, 'date': date_str, 'status': 'failed', 'error': err or '提交失败'})
                        log_report(username, date_str, record.normal_hours, record.overtime_hours, 'failed', err)

                await session.commit()
            
            log_business('提交报工', username, f'成功{success_count}条, 失败{failed_count}条')
            log_db_operation('UPDATE', 'work_records', affected_rows=success_count + failed_count)
            
            self.write({
                'success': True,
                'message': f'提交完成：成功 {success_count} 条，失败 {failed_count} 条',
                'success_count': success_count,
                'failed_count': failed_count,
                'data': results
            })

        except Exception as e:
            log_error('SubmitHandler.post', f'提交失败: {str(e)}')
            self.write({'success': False, 'message': f'提交失败: {str(e)}'})


class FillDraftHandler(BaseHandler):
    """日历选日 → 生成待填报列表（只写库为 pending，供用户编辑，不直接提交）"""

    async def post(self):
        try:
            username = self.get_current_user()
            data = tornado.escape.json_decode(self.request.body)
            items = data.get('items', [])  # [{date, normal_hours, overtime_hours}]
            log_api_call('FillDraftHandler', 'POST', {'username': username, 'count': len(items)})

            if not items:
                self.write({'success': False, 'message': '请选择要填报的日期'})
                return

            async with db.async_session_maker() as session:
                result = await session.execute(
                    select(UserConfig).where(UserConfig.username == username)
                )
                user_config = result.scalar_one_or_none()

                # 工作内容默认取提交模板里的（没有就留空，用户可在记录页自己填）
                default_content = ''
                if user_config and user_config.template_data:
                    try:
                        default_content = json.loads(user_config.template_data).get('gstbGzbg', '') or ''
                    except Exception:
                        default_content = ''
                if not default_content:
                    default_content = DEFAULT_WORK_CONTENT   # 模板没工作描述时用默认

                count = 0
                for it in items:
                    try:
                        # 正常/加班单项都夹到 [0, 8]
                        normal = min(max(float(it.get('normal_hours') or 0), 0.0), 8.0)
                        overtime = min(max(float(it.get('overtime_hours') or 0), 0.0), 8.0)
                        work_date = datetime.strptime(it.get('date'), '%Y-%m-%d').date()
                    except Exception:
                        continue

                    existing = await session.execute(
                        select(WorkRecord).where(and_(
                            WorkRecord.username == username,
                            WorkRecord.work_date == work_date
                        ))
                    )
                    record = existing.scalar_one_or_none()
                    if record:
                        record.normal_hours = normal
                        record.overtime_hours = overtime
                        record.avail_normal = normal       # 记下可填上限（来自当天可报工时）
                        record.avail_overtime = overtime
                        record.status = 'pending'          # 重新拉回待填报
                    else:
                        record = WorkRecord(
                            username=username, work_date=work_date,
                            normal_hours=normal, overtime_hours=overtime,
                            avail_normal=normal, avail_overtime=overtime,
                            work_content=default_content, status='pending'
                        )
                        session.add(record)
                    count += 1

                await session.commit()

            log_business('生成待填报', username, f'{count}条')
            log_db_operation('INSERT/UPDATE', 'work_records', affected_rows=count)

            self.write({
                'success': True,
                'count': count,
                'message': f'已生成 {count} 条待填报记录，请在「工时记录」里编辑后提交'
            })
        except Exception as e:
            log_error('FillDraftHandler.post', f'生成待填报失败: {str(e)}')
            self.write({'success': False, 'message': f'生成待填报失败: {str(e)}'})


# 本地演示假任务（WT_MOCK=1 时返回），覆盖进行中/已完成 + 不同时间，便于看排序
MOCK_TASKS = [
    {"id": "1", "rwMc": "可观测-业务系统接入", "rwZt": "进行中", "ssXm": "2026年生产云可观测平台升级优化研发项目", "xmId": "806492261847146437", "jhKsDate": "2026-03-02", "jhJsDate": "2026-12-30", "yqTs": 0, "roleName": "参与人", "lx": "工程化"},
    {"id": "2", "rwMc": "需求分析与设计", "rwZt": "进行中", "ssXm": "2025年数据服务目录与元数据管理研发", "xmId": "557094664985907077", "jhKsDate": "2025-09-01", "jhJsDate": "2026-08-30", "yqTs": 12, "roleName": "负责人", "lx": "研发"},
    {"id": "3", "rwMc": "集成联调", "rwZt": "进行中", "ssXm": "2025年生产系统运维系统集成项目", "xmId": "557094700000000001", "jhKsDate": "2025-06-15", "jhJsDate": "2026-03-31", "yqTs": 0, "roleName": "参与人", "lx": "工程化"},
    {"id": "4", "rwMc": "接口联调测试", "rwZt": "进行中", "ssXm": "2025年跨行账户信息认证平台改造", "xmId": "557088896165057925", "jhKsDate": "2025-11-10", "jhJsDate": "2026-05-30", "yqTs": 0, "roleName": "参与人", "lx": "工程化"},
    {"id": "5", "rwMc": "二期需求调研", "rwZt": "未开始", "ssXm": "2026年湖管平台优化改造工程", "xmId": "557090524704542597", "jhKsDate": "2026-07-01", "jhJsDate": "2026-10-31", "yqTs": 0, "roleName": "负责人", "lx": "研发"},
    {"id": "6", "rwMc": "性能优化方案", "rwZt": "未开始", "ssXm": "2026年交易核算系统功能优化工程", "xmId": "557090608926166917", "jhKsDate": "2026-05-20", "jhJsDate": "2026-09-30", "yqTs": 0, "roleName": "参与人", "lx": "工程化"},
    {"id": "7", "rwMc": "安全加固实施", "rwZt": "未开始", "ssXm": "2026年账户与支付业务风险监测系统优化", "xmId": "557090674789322629", "jhKsDate": "2026-04-15", "jhJsDate": "2026-08-15", "yqTs": 0, "roleName": "参与人", "lx": "工程化"},
    {"id": "8", "rwMc": "数据迁移评估", "rwZt": "已暂停", "ssXm": "2025年数据中台功能优化改造工程", "xmId": "557090642610622341", "jhKsDate": "2025-08-01", "jhJsDate": "2026-02-28", "yqTs": 30, "roleName": "参与人", "lx": "研发"},
    {"id": "9", "rwMc": "报表模块重构", "rwZt": "已暂停", "ssXm": "2025年计费管理子系统完善工程", "xmId": "557090707060297605", "jhKsDate": "2025-03-10", "jhJsDate": "2025-09-30", "yqTs": 0, "roleName": "负责人", "lx": "工程化"},
    {"id": "10", "rwMc": "一期上线", "rwZt": "已完成", "ssXm": "2025年数据分析和服务平台架构优化", "xmId": "557090743932424069", "jhKsDate": "2025-01-15", "jhJsDate": "2025-05-20", "yqTs": 0, "roleName": "参与人", "lx": "工程化"},
    {"id": "11", "rwMc": "设计阶段", "rwZt": "已完成", "ssXm": "2024年集中监控系统优化项目", "xmId": "557094565769645957", "jhKsDate": "2024-03-01", "jhJsDate": "2024-03-11", "yqTs": 0, "roleName": "参与人", "lx": "工程化"},
    {"id": "12", "rwMc": "项目启动及立项", "rwZt": "已完成", "ssXm": "2024年支付系统智控平台故障处理模块研发项目", "xmId": "557094664985907077", "jhKsDate": "2024-03-04", "jhJsDate": "2024-06-05", "yqTs": 0, "roleName": "参与人", "lx": "工程化"},
    {"id": "13", "rwMc": "验收交付", "rwZt": "已完成", "ssXm": "2024年全国中小微企业资金流信用信息平台", "xmId": "557094700000000002", "jhKsDate": "2024-09-01", "jhJsDate": "2024-12-20", "yqTs": 0, "roleName": "参与人", "lx": "工程化"},
]


class MyTasksHandler(BaseHandler):
    """获取我的填报任务列表（调 xiaokong getMyTask；只需认证，不需提交模板）"""

    async def post(self):
        try:
            username = self.get_current_user()
            log_api_call('MyTasksHandler', 'POST', {'username': username})

            async with db.async_session_maker() as session:
                result = await session.execute(
                    select(UserConfig).where(UserConfig.username == username)
                )
                user_config = result.scalar_one_or_none()
            if not user_config or not user_config.authorization:
                self.write({'success': False, 'message': '请先配置认证信息'})
                return

            # 本地演示开关：WT_MOCK=1 返回假任务（没内网时看页面）。生产别设。
            if os.environ.get('WT_MOCK') == '1':
                self.write({'success': True, 'data': MOCK_TASKS})
                return

            headers = {
                'Accept': 'application/json, text/plain, */*',
                'Authorization': user_config.authorization,
                'Content-Type': 'application/json;charset=UTF-8',
                'Cookie': user_config.cookie or '',
                'Origin': 'http://xiaokong.cfid.cn',
                'Referer': 'http://xiaokong.cfid.cn/dashboard',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'fz-origin': 'pc'
            }
            now_ts = int(time.time())
            url = f"http://xiaokong.cfid.cn/api/example/Gzrwb/getMyTask?n={now_ts}"
            body = {
                "superQueryJson": "", "currentPage": 1, "pageSize": 200,
                "sort": "desc", "sidx": "", "gchxmId": "", "lx": "XXH",
                "dataType": 1, "menuId": ""
            }
            try:
                resp = await asyncio.to_thread(requests.post, url, headers=headers, json=body, timeout=15, verify=False)
                rj = resp.json()
                if str(rj.get('code')) not in ('200', '0'):
                    self.write({'success': False, 'message': f"获取任务失败：{rj.get('msg', rj.get('code'))}"})
                    return
                tasks = (rj.get('data') or {}).get('list', []) or []
                log_business('查询任务', username, f'{len(tasks)} 个任务')
                self.write({'success': True, 'data': tasks})
            except Exception as e:
                log_error('MyTasksHandler.fetch', str(e))
                self.write({'success': False, 'message': f'获取任务失败：{str(e)}'})
        except Exception as e:
            log_error('MyTasksHandler.post', str(e))
            self.write({'success': False, 'message': str(e)})


# ===== 懒人模式：用任意认证 curl + 选中任务，合成提交配置 =====
# 提交报工的固定字段（实测跨用户/项目/任务恒定）
REPORT_FIXED = {
    "gstbId": 0, "flowId": "", "status": 1, "freeapproveruserid": "",
    "flowUrgent": 1, "gstbGzlx": "378106982789290181", "gstbFj": "[]",
    "gstbTbrq": "", "gstbRwzt": "402723309315163141",
    "type": "424180858316970501", "gstbRbztName": "",
    "gstbZcgz": "0.0", "gstbPtjb": "0.0", "gstbGzbg": "", "gstbBgsj": 0,
    "gstbRwjz": "0",
}


def build_lazy_template(task):
    """用选中任务合成提交模板 template_data。
    _jhKsDate/_jhJsDate 仅供提交时算 gstbRwjz，发请求前会删除，不发给原系统。"""
    td = dict(REPORT_FIXED)
    td["gstbRwId"] = str(task.get("id", ""))
    td["gstbRwmc"] = str(task.get("rwMc", ""))
    td["gstbSsxm"] = str(task.get("xmId", ""))
    td["_jhKsDate"] = task.get("jhKsDate", "") or ""
    td["_jhJsDate"] = task.get("jhJsDate", "") or ""
    return td


def parse_auth_from_curl(curl):
    """从任意 curl 抽 Authorization + Cookie。"""
    auth = re.search(r"-H\s+'Authorization:\s*([^']+)'", curl or '')
    cookie = re.search(r"-b\s+'([^']+)'", curl or '')
    return (auth.group(1).strip() if auth else ''), (cookie.group(1).strip() if cookie else '')


async def fetch_my_tasks(authorization, cookie):
    """调 xiaokong getMyTask 拉任务列表（WT_MOCK=1 返回假数据）。失败抛异常。"""
    if os.environ.get('WT_MOCK') == '1':
        return MOCK_TASKS
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Authorization': authorization,
        'Content-Type': 'application/json;charset=UTF-8',
        'Cookie': cookie or '',
        'Origin': 'http://xiaokong.cfid.cn',
        'Referer': 'http://xiaokong.cfid.cn/dashboard',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'fz-origin': 'pc'
    }
    now_ts = int(time.time())
    url = f"http://xiaokong.cfid.cn/api/example/Gzrwb/getMyTask?n={now_ts}"
    body = {"superQueryJson": "", "currentPage": 1, "pageSize": 200,
            "sort": "desc", "sidx": "", "gchxmId": "", "lx": "XXH",
            "dataType": 1, "menuId": ""}
    resp = await asyncio.to_thread(requests.post, url, headers=headers, json=body, timeout=15, verify=False)
    rj = resp.json()
    if str(rj.get('code')) not in ('200', '0'):
        raise RuntimeError(rj.get('msg') or f"code={rj.get('code')}")
    return (rj.get('data') or {}).get('list', []) or []


class PreviewTasksHandler(BaseHandler):
    """懒人模式步骤①：用粘贴的任意认证 curl 预览任务（不存库）"""

    async def post(self):
        try:
            data = tornado.escape.json_decode(self.request.body)
            authorization, cookie = parse_auth_from_curl(data.get('curl', ''))
            if not authorization:
                self.write({'success': False, 'message': '没解析到 Authorization，请粘含认证的 curl'})
                return
            user_id, display_name = identity_from_token(authorization)
            if not user_id:
                self.write({'success': False, 'message': 'Authorization 无效，无法解析身份'})
                return
            try:
                tasks = await fetch_my_tasks(authorization, cookie)
            except Exception as e:
                self.write({'success': False, 'message': f'拉取任务失败：{e}'})
                return
            self.write({'success': True, 'display_name': display_name or user_id, 'data': tasks})
        except Exception as e:
            log_error('PreviewTasksHandler.post', str(e))
            self.write({'success': False, 'message': str(e)})


class QuickConfigHandler(BaseHandler):
    """懒人模式步骤②：任意认证 curl + 选中任务 → 合成提交配置存库（等价配好 reportWorkingHours）"""

    async def post(self):
        try:
            data = tornado.escape.json_decode(self.request.body)
            curl = data.get('curl', '')
            task = data.get('task') or {}
            authorization, cookie = parse_auth_from_curl(curl)
            user_id, display_name = identity_from_token(authorization)
            if not user_id:
                self.write({'success': False, 'message': '无法解析身份，请粘含有效 Authorization 的 curl'})
                return
            if not task.get('id'):
                self.write({'success': False, 'message': '请选择一个任务'})
                return
            username = user_id
            template_data = build_lazy_template(task)
            # 合成等价 reportWorkingHours 的 curl_template（供 SubmitHandler 提取URL + 判定可提交）
            fake_curl = ("curl 'http://xiaokong.cfid.cn/api/example/Gstb/reportWorkingHours?n=0' "
                         f"--data-raw '{json.dumps(template_data, ensure_ascii=False)}' ")
            td_json = json.dumps(template_data, ensure_ascii=False)
            async with db.async_session_maker() as session:
                result = await session.execute(select(UserConfig).where(UserConfig.username == username))
                uc = result.scalar_one_or_none()
                if uc:
                    uc.curl_template = fake_curl
                    uc.authorization = authorization
                    uc.cookie = cookie
                    uc.template_data = td_json
                else:
                    uc = UserConfig(username=username, curl_template=fake_curl,
                                    authorization=authorization, cookie=cookie, template_data=td_json)
                    session.add(uc)
                await session.commit()
            log_business('懒人配置', username, f"任务={task.get('rwMc')}")
            self.write({'success': True, 'username': username, 'display_name': display_name or username,
                        'can_submit': True, 'task_name': task.get('rwMc', '')})
        except Exception as e:
            log_error('QuickConfigHandler.post', str(e))
            self.write({'success': False, 'message': str(e)})


def make_app():
    """创建应用"""
    return tornado.web.Application([
        (r'/worktime-api/login', LoginHandler),
        (r'/worktime-api/config', ConfigHandler),
        (r'/worktime-api/query-worktime', QueryWorktimeHandler),
        (r'/worktime-api/records', RecordsHandler),
        (r'/worktime-api/records/batch', BatchUpdateHandler),
        (r'/worktime-api/custom', CustomWorktimeHandler),
        (r'/worktime-api/excel/export', ExcelExportHandler),
        (r'/worktime-api/excel/import', ExcelImportHandler),
        (r'/worktime-api/submit', SubmitHandler),
        (r'/worktime-api/fill-draft', FillDraftHandler),
        (r'/worktime-api/my-tasks', MyTasksHandler),
        (r'/worktime-api/preview-tasks', PreviewTasksHandler),
        (r'/worktime-api/quick-config', QuickConfigHandler),
    ])


async def init_and_start():
    """初始化数据库并启动服务器"""
    # 初始化数据库
    print("正在初始化数据库...")
    logger.info("开始初始化数据库连接...")
    await db.init_db()
    logger.info(f"数据库初始化完成: {DB_CONFIG['database']}")
    
    # 创建应用
    app = make_app()
    app.listen(APP_CONFIG['port'])
    
    print(f"服务器已启动: http://localhost:{APP_CONFIG['port']}")
    print(f"数据库: MySQL - {DB_CONFIG['database']}")
    logger.info(f"服务器启动成功，监听端口: {APP_CONFIG['port']}")


if __name__ == '__main__':
    try:
        # 使用 Tornado 的 IOLoop 运行异步初始化
        tornado.ioloop.IOLoop.current().run_sync(init_and_start)
        # 启动事件循环
        tornado.ioloop.IOLoop.current().start()
    except KeyboardInterrupt:
        print("\n服务器已停止")
