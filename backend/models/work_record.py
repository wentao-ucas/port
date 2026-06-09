# -*- coding: utf-8 -*-
"""工时记录模型"""

from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Index, Text
from sqlalchemy.sql import func
from utils.db import Base


class WorkRecord(Base):
    """工时记录表"""
    __tablename__ = 'work_records'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), nullable=False, comment='用户名')
    work_date = Column(Date, nullable=False, comment='工作日期')
    normal_hours = Column(Float, default=0.0, comment='正常工时')
    overtime_hours = Column(Float, default=0.0, comment='加班工时')
    avail_normal = Column(Float, nullable=True, comment='可填正常工时上限')
    avail_overtime = Column(Float, nullable=True, comment='可填加班工时上限')
    work_content = Column(Text, nullable=True, comment='工作内容')
    status = Column(String(20), default='pending', comment='状态: pending/submitted/failed')
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment='更新时间')
    
    # 创建联合唯一索引
    __table_args__ = (
        Index('idx_user_date', 'username', 'work_date', unique=True),
    )
