# -*- coding: utf-8 -*-
"""用户配置模型"""

from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from utils.db import Base


class UserConfig(Base):
    """用户配置表"""
    __tablename__ = 'user_configs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, comment='用户名(业务身份user_id)')
    display_name = Column(String(100), nullable=True, comment='显示名(token里的user_name/英文名)')
    authorization = Column(Text, comment='Authorization token')
    cookie = Column(String(500), comment='Cookie')
    curl_template = Column(Text, comment='完整的curl命令')
    template_data = Column(Text, comment='请求模板数据JSON')
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment='更新时间')
