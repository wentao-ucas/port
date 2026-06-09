# -*- coding: utf-8 -*-
"""工时报工系统 - 主应用入口：DB 初始化 + 路由 + 启动。
   Handler 已按领域拆分到 handlers/（2026-06 重构），本文件只留装配与启动。"""
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

from config import APP_CONFIG, DB_CONFIG
from utils import db
from utils.logger import logger
from handlers import (
    LoginHandler, ConfigHandler, QueryWorktimeHandler, RecordsHandler,
    BatchUpdateHandler, CustomWorktimeHandler, ExcelExportHandler, ExcelImportHandler,
    SubmitHandler, FillDraftHandler, MyTasksHandler, PreviewTasksHandler, QuickConfigHandler,
)
# 兼容旧引用（如 test_submit_concurrency.py: from app import submit_one）
from handlers.common import submit_one  # noqa: F401


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
