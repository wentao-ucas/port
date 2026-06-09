# -*- coding: utf-8 -*-
"""日志配置模块 - 30天轮询"""
import logging
from logging.handlers import TimedRotatingFileHandler
import os
from datetime import datetime

# 日志目录
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# 日志格式
LOG_FORMAT = '%(asctime)s [%(levelname)s] [%(name)s] %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

def get_logger(name='worktime'):
    """获取日志记录器
    
    Args:
        name: 日志记录器名称
        
    Returns:
        logging.Logger: 配置好的日志记录器
    """
    logger = logging.getLogger(name)
    
    # 避免重复添加handler
    if logger.handlers:
        return logger
    
    logger.setLevel(logging.INFO)
    
    # 创建格式化器
    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 应用日志 - 按天轮询，保留30天
    app_log_file = os.path.join(LOG_DIR, 'app.log')
    app_handler = TimedRotatingFileHandler(
        app_log_file,
        when='midnight',  # 每天午夜轮询
        interval=1,
        backupCount=30,  # 保留30天
        encoding='utf-8'
    )
    app_handler.setLevel(logging.INFO)
    app_handler.setFormatter(formatter)
    app_handler.suffix = '%Y%m%d'  # 备份文件后缀格式
    logger.addHandler(app_handler)
    
    # 错误日志 - 单独记录错误
    error_log_file = os.path.join(LOG_DIR, 'error.log')
    error_handler = TimedRotatingFileHandler(
        error_log_file,
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    error_handler.suffix = '%Y%m%d'
    logger.addHandler(error_handler)
    
    return logger


# 创建默认logger
logger = get_logger()


def _get_audit_logger():
    """报工审计日志：独立文件 report_audit.log，保留90天，不冒泡到 app.log"""
    name = 'worktime_audit'
    lg = logging.getLogger(name)
    if lg.handlers:
        return lg
    lg.setLevel(logging.INFO)
    lg.propagate = False
    fmt = logging.Formatter('%(asctime)s %(message)s', DATE_FORMAT)
    fh = TimedRotatingFileHandler(
        os.path.join(LOG_DIR, 'report_audit.log'),
        when='midnight', interval=1, backupCount=90, encoding='utf-8'
    )
    fh.setFormatter(fmt)
    fh.suffix = '%Y%m%d'
    lg.addHandler(fh)
    return lg


audit_logger = _get_audit_logger()


def log_report(username, date, normal, overtime, result, msg=''):
    """报工审计：每条提交记一行，便于事后排查"""
    audit_logger.info(
        f"REPORT user={username} date={date} normal={normal} overtime={overtime} result={result} msg={msg}"
    )


def log_api_call(handler_name, method, params=None, response_time=None):
    """记录API调用
    
    Args:
        handler_name: 处理器名称
        method: HTTP方法
        params: 请求参数
        response_time: 响应时间（毫秒）
    """
    msg = f"API调用 [{handler_name}] {method}"
    if params:
        msg += f" 参数: {params}"
    if response_time:
        msg += f" 耗时: {response_time}ms"
    logger.info(msg)


def log_db_operation(operation, table, params=None, affected_rows=None):
    """记录数据库操作
    
    Args:
        operation: 操作类型（SELECT/INSERT/UPDATE/DELETE）
        table: 表名
        params: 操作参数
        affected_rows: 影响行数
    """
    msg = f"数据库操作 [{operation}] 表: {table}"
    if params:
        msg += f" 参数: {params}"
    if affected_rows is not None:
        msg += f" 影响行数: {affected_rows}"
    logger.info(msg)


def log_error(error_type, message, traceback_info=None):
    """记录错误
    
    Args:
        error_type: 错误类型
        message: 错误消息
        traceback_info: 堆栈跟踪信息
    """
    msg = f"错误 [{error_type}] {message}"
    if traceback_info:
        msg += f"\n{traceback_info}"
    logger.error(msg)


def log_business(action, username=None, details=None):
    """记录业务操作
    
    Args:
        action: 操作动作（生成记录、提交报工等）
        username: 用户名
        details: 详细信息
    """
    msg = f"业务操作 [{action}]"
    if username:
        msg += f" 用户: {username}"
    if details:
        msg += f" 详情: {details}"
    logger.info(msg)
