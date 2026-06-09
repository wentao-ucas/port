# -*- coding: utf-8 -*-
"""应用配置"""

import os
import urllib.parse

# MySQL数据库配置
# 环境变量优先：本地/生产都通过环境变量(见 deploy/env.sh.example)注入，密码不进代码。
# 生产示例：
#   export DB_HOST=<your-db-host> DB_USER=root DB_PASSWORD='<your-db-password>' DB_NAME=chronos
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '3306')),
    'user': os.environ.get('DB_USER', 'root'),
    'password': os.environ.get('DB_PASSWORD', ''),
    'database': os.environ.get('DB_NAME', 'chronos'),
    'charset': 'utf8mb4',
    'autocommit': False,
}

# 应用配置
APP_CONFIG = {
    'port': int(os.environ.get('APP_PORT', '18760')),
    'debug': True,
}

# 访问门禁（全局共享账号密码，挡住安全扫描/路人直接看到数据）
# 生产改密码用环境变量 ACCESS_PASSWORD，不必改代码（改完重启后端，所有人需重新登录）
ACCESS_USER = os.environ.get('ACCESS_USER', 'admin')
ACCESS_PASSWORD = os.environ.get('ACCESS_PASSWORD', 'changeme')
ACCESS_SALT = os.environ.get('ACCESS_SALT', 'worktime-gate-2026')  # 生成访问令牌的盐，生产用环境变量覆盖

# 生成待填报时，若 curl 模板里没有工作描述(gstbGzbg)，用这个作默认工作内容
DEFAULT_WORK_CONTENT = '日常开发工作'

# URL编码密码（用于SQLAlchemy）
encoded_password = urllib.parse.quote_plus(DB_CONFIG['password'])

# 数据库URL（用于SQLAlchemy）
DATABASE_URL = f"mysql+aiomysql://{DB_CONFIG['user']}:{encoded_password}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}?charset={DB_CONFIG['charset']}"
