# -*- coding: utf-8 -*-
"""Excel导入导出工具"""

import io
from datetime import datetime
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Alignment, PatternFill


def export_records_to_excel(records):
    """导出记录到Excel"""
    wb = Workbook()
    ws = wb.active
    ws.title = "工时记录"
    
    # 设置标题行
    headers = ['ID', '日期', '星期', '正常工时', '加班工时', '状态', '创建时间']
    headers = ['ID', '日期', '星期', '正常工时', '加班工时', '工作内容', '状态', '创建时间']
    
    # 设置标题行样式
    header_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF')
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
    
    # 添加数据行
    weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    
    for record in records:
        work_date = datetime.strptime(record['date'], '%Y-%m-%d') if isinstance(record['date'], str) else record['date']
        weekday = weekdays[work_date.weekday()]
        
        ws.append([
            record['id'],
            record['date'],
            weekday,
            record['normal_hours'],
            record['overtime_hours'],
            record.get('work_content', ''),
            record['status'],
            record.get('created_at', '')
        ])
    
    # 设置列宽
    ws.column_dimensions['A'].width = 8
    ws.column_dimensions['B'].width = 12
    ws.column_dimensions['C'].width = 8
    ws.column_dimensions['D'].width = 12
    ws.column_dimensions['E'].width = 12
    ws.column_dimensions['F'].width = 28
    ws.column_dimensions['G'].width = 10
    ws.column_dimensions['H'].width = 20
    
    # 保存到内存
    excel_file = io.BytesIO()
    wb.save(excel_file)
    excel_file.seek(0)
    
    return excel_file


def import_records_from_excel(excel_file):
    """从Excel导入记录"""
    wb = load_workbook(excel_file)
    ws = wb.active
    
    records = []
    
    # 跳过标题行，从第2行开始读取
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row[0]:  # 如果ID为空，跳过
            continue
        
        record = {
            'id': row[0],
            'date': row[1] if isinstance(row[1], str) else row[1].strftime('%Y-%m-%d'),
            'normal_hours': float(row[3]) if row[3] else 0.0,
            'overtime_hours': float(row[4]) if row[4] else 0.0,
            'work_content': row[5] or ''
        }
        records.append(record)
    
    return records
