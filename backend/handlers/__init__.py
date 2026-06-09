# -*- coding: utf-8 -*-
"""处理器模块：按领域拆分的 Tornado Handler（原先全在 app.py，2026-06 拆分）。"""
from handlers.base import CorsBase, BaseHandler
from handlers.auth import LoginHandler
from handlers.config import ConfigHandler
from handlers.records import (
    RecordsHandler, BatchUpdateHandler, CustomWorktimeHandler, FillDraftHandler,
)
from handlers.excel import ExcelExportHandler, ExcelImportHandler
from handlers.worktime import QueryWorktimeHandler, SubmitHandler
from handlers.tasks import MyTasksHandler, PreviewTasksHandler, QuickConfigHandler

__all__ = [
    'CorsBase', 'BaseHandler', 'LoginHandler', 'ConfigHandler',
    'RecordsHandler', 'BatchUpdateHandler', 'CustomWorktimeHandler', 'FillDraftHandler',
    'ExcelExportHandler', 'ExcelImportHandler',
    'QueryWorktimeHandler', 'SubmitHandler',
    'MyTasksHandler', 'PreviewTasksHandler', 'QuickConfigHandler',
]
