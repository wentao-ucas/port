# -*- coding: utf-8 -*-
"""门禁登录。"""
import tornado.escape

from handlers.base import CorsBase
from handlers.common import make_access_token
from config import ACCESS_USER, ACCESS_PASSWORD
from utils.logger import log_business


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
