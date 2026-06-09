# -*- coding: utf-8 -*-
"""Excel 导入 / 导出。"""
from datetime import datetime
from sqlalchemy import select, update, and_

from handlers.base import BaseHandler
from utils import db
from utils.logger import log_api_call, log_business, log_db_operation, log_error
from utils.excel_helper import export_records_to_excel, import_records_from_excel
from models import WorkRecord


class ExcelExportHandler(BaseHandler):
    """Excel导出"""
    
    async def get(self):
        """导出Excel"""
        try:
            username = self.get_current_user()
            log_api_call('ExcelExportHandler', 'GET', {'username': username})
            
            async with db.async_session_maker() as session:
                result = await session.execute(
                    select(WorkRecord)
                    .where(WorkRecord.username == username)
                    .order_by(WorkRecord.work_date.desc())
                )
                records = result.scalars().all()
                
                record_list = []
                for record in records:
                    record_list.append({
                        'id': record.id,
                        'date': record.work_date.strftime('%Y-%m-%d'),
                        'normal_hours': record.normal_hours,
                        'overtime_hours': record.overtime_hours,
                        'work_content': record.work_content or '',
                        'status': record.status,
                        'created_at': record.created_at.strftime('%Y-%m-%d %H:%M:%S') if record.created_at else ''
                    })
            
            excel_file = export_records_to_excel(record_list)
            
            self.set_header('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            self.set_header('Content-Disposition', f'attachment; filename="worktime_{username}_{datetime.now().strftime("%Y%m%d")}.xlsx"')
            
            log_business('导出Excel', username, f'导出{len(record_list)}条记录')
            
            self.write(excel_file.getvalue())
        
        except Exception as e:
            log_error('ExcelExportHandler.get', str(e))
            self.set_header('Content-Type', 'application/json')
            self.write({'success': False, 'message': str(e)})


class ExcelImportHandler(BaseHandler):
    """Excel导入"""
    
    async def post(self):
        """导入Excel"""
        try:
            username = self.get_current_user()
            log_api_call('ExcelImportHandler', 'POST', {'username': username})
            
            if 'file' not in self.request.files:
                self.write({'success': False, 'message': '请上传Excel文件'})
                return
            
            file_info = self.request.files['file'][0]
            excel_data = file_info['body']
            
            import io
            excel_file = io.BytesIO(excel_data)
            records = import_records_from_excel(excel_file)
            
            async with db.async_session_maker() as session:
                updated_count = 0
                for record in records:
                    await session.execute(
                        update(WorkRecord)
                        .where(and_(
                            WorkRecord.id == record['id'],
                            WorkRecord.username == username
                        ))
                        .values(
                            normal_hours=record['normal_hours'],
                            overtime_hours=record['overtime_hours'],
                            work_content=record.get('work_content', '')
                        )
                    )
                    updated_count += 1
                
                await session.commit()
            
            log_business('导入Excel', username, f'更新{updated_count}条记录')
            log_db_operation('UPDATE', 'work_records', affected_rows=updated_count)
            
            self.write({
                'success': True,
                'message': f'成功导入并更新 {updated_count} 条记录'
            })
        
        except Exception as e:
            log_error('ExcelImportHandler.post', f'导入失败: {str(e)}')
            self.write({'success': False, 'message': f'导入失败: {str(e)}'})
