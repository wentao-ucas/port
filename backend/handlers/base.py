# -*- coding: utf-8 -*-
"""门禁基类：统一 CORS + 访问令牌校验。"""
import tornado.web

from handlers.common import verify_access_token


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
