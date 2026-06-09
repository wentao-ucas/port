# -*- coding: utf-8 -*-
"""工时记录：列表/编辑/删除、批量改列、自定义工时、生成待填报。"""
import json
import tornado.escape
from datetime import datetime, timedelta
from sqlalchemy import select, and_, delete as sqla_delete

from handlers.base import BaseHandler
from utils import db
from utils.logger import log_api_call, log_business, log_db_operation, log_error
from models import UserConfig, WorkRecord
from config import DEFAULT_WORK_CONTENT


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
                        'task_id': record.task_id or '',
                        'task_name': record.task_name or '',
                        'plan_start': record.plan_start or '',
                        'plan_end': record.plan_end or '',
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


class FillDraftHandler(BaseHandler):
    """日历选日 → 生成待填报列表（只写库为 pending，供用户编辑，不直接提交）"""

    async def post(self):
        try:
            username = self.get_current_user()
            data = tornado.escape.json_decode(self.request.body)
            items = data.get('items', [])  # [{date, normal_hours, overtime_hours}]
            # 任务快照（前端从"本次报工任务"传来：任务id/名/计划周期），盖到每条记录上 → 历史也能稳定判超期
            task = data.get('task') or {}
            t_id = str(task.get('task_id') or '').strip() or None
            t_name = str(task.get('task_name') or '').strip() or None
            t_ks = str(task.get('plan_start') or '').strip() or None
            t_js = str(task.get('plan_end') or '').strip() or None
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
                # 兜底：前端没传任务名/id 时，从配置模板补 gstbRwmc/gstbRwId（周期前端没传则留空）
                if user_config and user_config.template_data:
                    try:
                        _td = json.loads(user_config.template_data)
                        t_id = t_id or (str(_td.get('gstbRwId') or '').strip() or None)
                        t_name = t_name or (str(_td.get('gstbRwmc') or '').strip() or None)
                        t_ks = t_ks or (str(_td.get('_jhKsDate') or '').strip() or None)
                        t_js = t_js or (str(_td.get('_jhJsDate') or '').strip() or None)
                    except Exception:
                        pass

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
                        record.task_id = t_id              # 重新盖章为当前任务
                        record.task_name = t_name
                        record.plan_start = t_ks
                        record.plan_end = t_js
                    else:
                        record = WorkRecord(
                            username=username, work_date=work_date,
                            normal_hours=normal, overtime_hours=overtime,
                            avail_normal=normal, avail_overtime=overtime,
                            work_content=default_content, status='pending',
                            task_id=t_id, task_name=t_name, plan_start=t_ks, plan_end=t_js
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
