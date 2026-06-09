# -*- coding: utf-8 -*-
"""用户配置（完整模式 curl）。"""
import re
import json
import tornado.escape
from sqlalchemy import select

from handlers.base import BaseHandler
from handlers.common import identity_from_token, exp_from_token
from utils import db
from utils.logger import log_api_call, log_business, log_db_operation, log_error
from models import UserConfig


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

            # 防呆：粘成 "Copy all as cURL"（多条请求拼一起）或复制错了请求 → --data-raw 解析不出有效提交模板，
            # 但 curl 里又含 reportWorkingHours 字样会被误判成"可提交"。这里拦掉并给明确提示。
            if 'reportWorkingHours' in curl_template:
                if curl_template.count("curl '") > 1:
                    self.write({'success': False, 'message': '检测到多条请求（像是 Copy all as cURL）。请在 Network 里只对【单条 reportWorkingHours】右键 Copy → Copy as cURL (bash) 再粘贴。'})
                    return
                if not template_data or 'gstbRwId' not in template_data:
                    self.write({'success': False, 'message': '没解析到有效的提交模板（--data-raw）。请确认复制的是单条 reportWorkingHours 请求的 Copy as cURL (bash)，不是 Copy all as cURL。'})
                    return

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
                    user_config.display_name = display_name or user_config.display_name
                    user_config.template_data = json.dumps(template_data, ensure_ascii=False) if template_data else None
                else:
                    user_config = UserConfig(
                        username=username,
                        display_name=display_name or None,
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
