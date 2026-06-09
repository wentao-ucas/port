# -*- coding: utf-8 -*-
"""可报工时查询 + 报工提交。"""
import os
import re
import json
import time
import asyncio
import tornado.escape
import requests
from datetime import datetime, timedelta
from sqlalchemy import select, and_

from handlers.base import BaseHandler
from handlers.common import date_to_ms, submit_one
from utils import db
from utils.logger import log_api_call, log_business, log_db_operation, log_error, log_report
from models import UserConfig, WorkRecord
from config import DEFAULT_WORK_CONTENT


def build_submit_data(template_data, record):
    """由提交模板 + 单条记录 构造发给上游的提交体。
    用记录覆盖工时/日期/超期标记/工作内容；其余字段沿用模板。
    懒人模板的 gstbGzbg 是空的，必须用记录里用户填/改的工作内容覆盖，否则上游收到空内容。
    """
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
    # 工作内容：记录里的优先（用户在工时记录页填/改的）→ 模板里的工作描述 → 默认
    submit_data['gstbGzbg'] = record.work_content or template_data.get('gstbGzbg') or DEFAULT_WORK_CONTENT
    return submit_data


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

                    submit_data = build_submit_data(template_data, record)
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
