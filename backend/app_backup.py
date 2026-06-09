import tornado.ioloop
import tornado.web
import tornado.escape
import json
import os
import sqlite3
from datetime import datetime, timedelta
import time
import re
import requests
import urllib3

urllib3.disable_warnings()

# 数据库路径
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'worktime.db')

class DatabaseHandler:
    """数据库处理类"""
    
    @staticmethod
    def init_db():
        """初始化数据库"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 配置表 - 存储认证信息和请求模板
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 报工记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS work_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                work_date DATE NOT NULL,
                normal_hours REAL DEFAULT 0.0,
                overtime_hours REAL DEFAULT 0.0,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(work_date)
            )
        ''')
        
        # 项目任务配置表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS work_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                field_name TEXT NOT NULL,
                field_value TEXT NOT NULL,
                display_name TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    @staticmethod
    def get_config(name):
        """获取配置"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM config WHERE name = ?', (name,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    
    @staticmethod
    def set_config(name, value):
        """设置配置"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO config (name, value, updated_at) 
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(name) DO UPDATE SET value = ?, updated_at = CURRENT_TIMESTAMP
        ''', (name, value, value))
        conn.commit()
        conn.close()

# 初始化数据库
DatabaseHandler.init_db()


class BaseHandler(tornado.web.RequestHandler):
    """基础处理器，处理跨域"""
    
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "Content-Type")
    
    def options(self, *args):
        self.set_status(204)
        self.finish()


class ConfigHandler(BaseHandler):
    """配置管理"""
    
    def get(self):
        """获取所有配置"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT name, value FROM config')
        configs = {row[0]: row[1] for row in cursor.fetchall()}
        
        # 获取工作配置
        cursor.execute('SELECT field_name, field_value, display_name FROM work_config')
        work_configs = [
            {'field_name': row[0], 'field_value': row[1], 'display_name': row[2]}
            for row in cursor.fetchall()
        ]
        
        conn.close()
        
        self.write({
            'success': True,
            'data': {
                'configs': configs,
                'work_configs': work_configs
            }
        })
    
    def post(self):
        """保存配置 - 自动解析 curl 命令"""
        try:
            data = tornado.escape.json_decode(self.request.body)
            
            # 如果提供了 curl 模板，自动解析
            if 'curl_template' in data and data['curl_template']:
                parsed = self._parse_curl_command(data['curl_template'])
                
                # 自动保存解析出的信息
                if parsed['authorization']:
                    DatabaseHandler.set_config('authorization', parsed['authorization'])
                if parsed['cookie']:
                    DatabaseHandler.set_config('cookie', parsed['cookie'])
                if parsed['template_data']:
                    DatabaseHandler.set_config('template_data', json.dumps(parsed['template_data']))
                
                DatabaseHandler.set_config('curl_template', data['curl_template'])
                
                self.write({
                    'success': True, 
                    'message': '配置保存成功',
                    'parsed': parsed
                })
                return
            
            # 兼容手动配置
            if 'authorization' in data:
                DatabaseHandler.set_config('authorization', data['authorization'])
            if 'cookie' in data:
                DatabaseHandler.set_config('cookie', data['cookie'])
            
            # 保存工作配置
            if 'work_config' in data:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute('DELETE FROM work_config')
                
                for item in data['work_config']:
                    cursor.execute('''
                        INSERT INTO work_config (field_name, field_value, display_name)
                        VALUES (?, ?, ?)
                    ''', (item['field_name'], item['field_value'], item.get('display_name', '')))
                
                conn.commit()
                conn.close()
            
            self.write({'success': True, 'message': '配置保存成功'})
        except Exception as e:
            self.write({'success': False, 'message': str(e)})
    
    def _parse_curl_command(self, curl_str):
        """解析 curl 命令，提取认证信息和模板数据"""
        result = {
            'authorization': '',
            'cookie': '',
            'template_data': None,
            'url': ''
        }
        
        try:
            # 提取 Authorization
            auth_match = re.search(r"-H\s+'Authorization:\s*([^']+)'", curl_str)
            if auth_match:
                result['authorization'] = auth_match.group(1).strip()
            
            # 提取 Cookie
            cookie_match = re.search(r"-b\s+'([^']+)'", curl_str)
            if cookie_match:
                result['cookie'] = cookie_match.group(1).strip()
            
            # 提取 URL
            url_match = re.search(r"curl\s+'([^']+)'", curl_str)
            if url_match:
                result['url'] = url_match.group(1).strip()
            
            # 提取 --data-raw 中的 JSON 数据
            data_match = re.search(r"--data-raw\s+'({.*?})'", curl_str, re.DOTALL)
            if data_match:
                result['template_data'] = json.loads(data_match.group(1))
            
        except Exception as e:
            print(f"解析 curl 命令失败: {e}")
        
        return result


class QueryWorkTimeHandler(BaseHandler):
    """查询可报工时间"""
    
    def post(self):
        """查询指定日期范围的可报工时间"""
        try:
            data = tornado.escape.json_decode(self.request.body)
            start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
            end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
            
            # 获取认证信息
            authorization = DatabaseHandler.get_config('authorization')
            cookie = DatabaseHandler.get_config('cookie')
            
            if not authorization:
                self.write({'success': False, 'message': '请先配置 Authorization'})
                return
            
            headers = {
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'zh-CN,zh;q=0.9',
                'Authorization': authorization,
                'Connection': 'keep-alive',
                'Referer': 'http://xiaokong.cfid.cn/home',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'fz-origin': 'pc'
            }
            
            if cookie:
                headers['Cookie'] = cookie
            
            results = []
            current_date = start_date
            
            while current_date <= end_date:
                timestamp_ms = int(datetime.combine(current_date, datetime.min.time()).timestamp() * 1000)
                now_ts = int(time.time())
                url = f"http://xiaokong.cfid.cn/api/example/Gstb/getInitMsg/0/{timestamp_ms}?n={now_ts}"
                
                try:
                    response = requests.get(url, headers=headers, timeout=10, verify=False)
                    result = response.json()
                    data_obj = result.get("data", {})
                    
                    results.append({
                        'date': current_date.strftime('%Y-%m-%d'),
                        'normal_hours': data_obj.get("ktbGs", "0"),
                        'overtime_hours': data_obj.get("ktbJbGs", "0"),
                        'status': 'success'
                    })
                except Exception as e:
                    results.append({
                        'date': current_date.strftime('%Y-%m-%d'),
                        'normal_hours': "0",
                        'overtime_hours': "0",
                        'status': 'error',
                        'error': str(e)
                    })
                
                current_date += timedelta(days=1)
                time.sleep(0.2)
            
            self.write({'success': True, 'data': results})
        except Exception as e:
            self.write({'success': False, 'message': str(e)})


class WorkRecordsHandler(BaseHandler):
    """工作记录管理"""
    
    def get(self):
        """获取工作记录及统计信息"""
        start_date = self.get_argument('start_date', None)
        end_date = self.get_argument('end_date', None)
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        if start_date and end_date:
            cursor.execute('''
                SELECT id, work_date, normal_hours, overtime_hours, status, created_at
                FROM work_records
                WHERE work_date BETWEEN ? AND ?
                ORDER BY work_date DESC
            ''', (start_date, end_date))
        else:
            cursor.execute('''
                SELECT id, work_date, normal_hours, overtime_hours, status, created_at
                FROM work_records
                ORDER BY work_date DESC
                LIMIT 100
            ''')
        
        rows = cursor.fetchall()
        records = []
        total_normal = 0.0
        total_overtime = 0.0
        
        for row in rows:
            normal_hours = float(row[2])
            overtime_hours = float(row[3])
            total_normal += normal_hours
            total_overtime += overtime_hours
            
            records.append({
                'id': row[0],
                'date': row[1],
                'normal_hours': normal_hours,
                'overtime_hours': overtime_hours,
                'status': row[4],
                'created_at': row[5]
            })
        
        # 计算统计信息
        total_hours = total_normal + total_overtime
        person_days = total_hours / 8.0  # 8小时=1人天
        person_months = person_days / 21.75  # 21.75天=1人月
        
        statistics = {
            'total_normal_hours': round(total_normal, 2),
            'total_overtime_hours': round(total_overtime, 2),
            'total_hours': round(total_hours, 2),
            'person_days': round(person_days, 2),
            'person_months': round(person_months, 2)
        }
        
        conn.close()
        self.write({'success': True, 'data': records, 'statistics': statistics})
    
    def post(self):
        """添加或更新工作记录"""
        try:
            data = tornado.escape.json_decode(self.request.body)
            records = data.get('records', [])
            
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            for record in records:
                cursor.execute('''
                    INSERT INTO work_records (work_date, normal_hours, overtime_hours, status)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(work_date) DO UPDATE SET
                        normal_hours = ?,
                        overtime_hours = ?,
                        status = ?,
                        updated_at = CURRENT_TIMESTAMP
                ''', (
                    record['date'],
                    record.get('normal_hours', 0),
                    record.get('overtime_hours', 0),
                    record.get('status', 'pending'),
                    record.get('normal_hours', 0),
                    record.get('overtime_hours', 0),
                    record.get('status', 'pending')
                ))
            
            conn.commit()
            conn.close()
            
            self.write({'success': True, 'message': '记录保存成功'})
        except Exception as e:
            self.write({'success': False, 'message': str(e)})
    
    def put(self):
        """更新单条记录"""
        try:
            data = tornado.escape.json_decode(self.request.body)
            record_id = data.get('id')
            normal_hours = float(data.get('normal_hours', 0))
            overtime_hours = float(data.get('overtime_hours', 0))
            
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE work_records 
                SET normal_hours = ?, overtime_hours = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (normal_hours, overtime_hours, record_id))
            
            conn.commit()
            conn.close()
            
            self.write({'success': True, 'message': '记录更新成功'})
        except Exception as e:
            self.write({'success': False, 'message': str(e)})


class SubmitWorkHandler(BaseHandler):
    """提交报工"""
    
    def post(self):
        """批量提交报工"""
        try:
            data = tornado.escape.json_decode(self.request.body)
            record_ids = data.get('record_ids', [])
            
            # 获取配置
            curl_template = DatabaseHandler.get_config('curl_template')
            if not curl_template:
                self.write({'success': False, 'message': '请先配置 curl 模板'})
                return
            
            # 获取已保存的认证信息和模板数据
            authorization = DatabaseHandler.get_config('authorization')
            cookie = DatabaseHandler.get_config('cookie')
            template_data_str = DatabaseHandler.get_config('template_data')
            
            # 解析 URL
            url_match = re.search(r"curl '(.*?)'", curl_template)
            url = url_match.group(1) if url_match else ''
            
            # 构建 headers
            headers = {
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'zh-CN,zh;q=0.9',
                'Connection': 'keep-alive',
                'Content-Type': 'application/json;charset=UTF-8',
                'Origin': 'http://xiaokong.cfid.cn',
                'Referer': 'http://xiaokong.cfid.cn/home',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'fz-origin': 'pc'
            }
            
            if authorization:
                headers['Authorization'] = authorization
            if cookie:
                headers['Cookie'] = cookie
            
            # 使用保存的模板数据
            template_data = json.loads(template_data_str) if template_data_str else {}
            
            # 获取记录并提交
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            results = []
            for record_id in record_ids:
                cursor.execute('''
                    SELECT work_date, normal_hours, overtime_hours
                    FROM work_records
                    WHERE id = ?
                ''', (record_id,))
                
                row = cursor.fetchone()
                if not row:
                    continue
                
                work_date, normal_hours, overtime_hours = row
                
                # 构造请求数据
                post_data = template_data.copy()
                post_data['gstbZcgz'] = str(normal_hours)
                post_data['gstbPtjb'] = str(overtime_hours)
                
                # 转换日期为时间戳
                dt = datetime.strptime(work_date, '%Y-%m-%d')
                timestamp_ms = int(time.mktime(dt.timetuple())) * 1000
                post_data['gstbBgsj'] = timestamp_ms
                
                # 发送请求
                try:
                    now_ts = int(time.time())
                    submit_url = re.sub(r'\?n=\d+', f'?n={now_ts}', url)
                    
                    response = requests.post(submit_url, headers=headers, json=post_data, verify=False, timeout=10)
                    
                    if response.status_code == 200:
                        # 更新状态
                        cursor.execute('''
                            UPDATE work_records
                            SET status = 'submitted', updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        ''', (record_id,))
                        
                        results.append({
                            'id': record_id,
                            'date': work_date,
                            'status': 'success',
                            'message': '提交成功'
                        })
                    else:
                        results.append({
                            'id': record_id,
                            'date': work_date,
                            'status': 'failed',
                            'message': f'HTTP {response.status_code}'
                        })
                except Exception as e:
                    results.append({
                        'id': record_id,
                        'date': work_date,
                        'status': 'error',
                        'message': str(e)
                    })
                
                time.sleep(1)  # 避免请求过快
            
            conn.commit()
            conn.close()
            
            self.write({'success': True, 'data': results})
        except Exception as e:
            self.write({'success': False, 'message': str(e)})


class GenerateRecordsHandler(BaseHandler):
    """生成工作记录"""
    
    def post(self):
        """生成指定月份的工作日记录"""
        try:
            data = tornado.escape.json_decode(self.request.body)
            year = data['year']
            month = data['month']
            normal_hours = data.get('normal_hours', 8.0)
            overtime_hours = data.get('overtime_hours', 0.0)
            
            # 生成工作日（周一到周五）
            dates = []
            d = datetime(year, month, 1).date()
            while d.month == month:
                if d.weekday() < 5:  # 周一到周五
                    dates.append(d)
                d += timedelta(days=1)
            
            # 保存到数据库
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            for date in dates:
                cursor.execute('''
                    INSERT INTO work_records (work_date, normal_hours, overtime_hours, status)
                    VALUES (?, ?, ?, 'pending')
                    ON CONFLICT(work_date) DO UPDATE SET
                        normal_hours = ?,
                        overtime_hours = ?,
                        updated_at = CURRENT_TIMESTAMP
                ''', (
                    date.strftime('%Y-%m-%d'),
                    normal_hours,
                    overtime_hours,
                    normal_hours,
                    overtime_hours
                ))
            
            conn.commit()
            conn.close()
            
            self.write({
                'success': True,
                'message': f'成功生成 {len(dates)} 条记录'
            })
        except Exception as e:
            self.write({'success': False, 'message': str(e)})


def make_app():
    return tornado.web.Application([
        (r"/api/config", ConfigHandler),
        (r"/api/query-worktime", QueryWorkTimeHandler),
        (r"/api/records", WorkRecordsHandler),
        (r"/api/submit", SubmitWorkHandler),
        (r"/api/generate", GenerateRecordsHandler),
        (r"/(.*)", tornado.web.StaticFileHandler, {
            "path": os.path.join(os.path.dirname(__file__), '..', 'frontend', 'dist'),
            "default_filename": "index.html"
        }),
    ])


if __name__ == "__main__":
    app = make_app()
    port = 8888
    app.listen(port)
    print(f"服务器已启动: http://localhost:{port}")
    print(f"数据库路径: {DB_PATH}")
    tornado.ioloop.IOLoop.current().start()
