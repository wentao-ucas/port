# -*- coding: utf-8 -*-
"""我的任务 + 懒人模式（预览任务 / 快速配置）。"""
import os
import json
import time
import asyncio
import tornado.escape
import requests
from sqlalchemy import select

from handlers.base import BaseHandler
from handlers.common import (MOCK_TASKS, parse_auth_from_curl, identity_from_token,
                             build_lazy_template, fetch_my_tasks)
from utils import db
from utils.logger import log_api_call, log_business, log_error
from models import UserConfig


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
                    uc.display_name = display_name or uc.display_name
                    uc.template_data = td_json
                else:
                    uc = UserConfig(username=username, display_name=display_name or None, curl_template=fake_curl,
                                    authorization=authorization, cookie=cookie, template_data=td_json)
                    session.add(uc)
                await session.commit()
            log_business('懒人配置', username, f"任务={task.get('rwMc')}")
            self.write({'success': True, 'username': username, 'display_name': display_name or username,
                        'can_submit': True, 'task_name': task.get('rwMc', '')})
        except Exception as e:
            log_error('QuickConfigHandler.post', str(e))
            self.write({'success': False, 'message': str(e)})
