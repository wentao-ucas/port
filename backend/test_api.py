# -*- coding: utf-8 -*-
"""后端API测试脚本"""
import requests
import json
from datetime import datetime, timedelta

BASE_URL = "http://localhost:18760"
USERNAME = "test_user"

# 模拟的curl命令
TEST_CURL = """
curl 'http://xiaokong.cfid.cn/api/example/Gstb/reportWorkingHours?n=1767151702' \
  -H 'Accept: application/json, text/plain, */*' \
  -H 'Accept-Language: zh-CN,zh;q=0.9' \
  -H 'Authorization: bearer <PASTE_YOUR_BEARER_TOKEN>' \
  -H 'Connection: keep-alive' \
  -H 'Content-Type: application/json;charset=UTF-8' \
  -b 'JSESSIONID=<PASTE_YOUR_SESSION_COOKIE>' \
  -H 'Origin: http://xiaokong.cfid.cn' \
  -H 'Referer: http://xiaokong.cfid.cn/home' \
  -H 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36' \
  -H 'fz-origin: pc' \
  --data-raw '{"gstbId":0,"flowId":"","status":1,"freeapproveruserid":"","flowUrgent":1,"gstbGzlx":"378106982789290181","gstbZcgz":"0.0","gstbPtjb":"8.0","gstbGzbg":"信创分区集成与系统迁移工作","gstbFj":"[]","gstbTbrq":"","gstbBgsj":1758988800000,"gstbRwmc":"集中监控系统集成阶段","gstbSsxm":"668793352338020677","gstbRwzt":"402723309315163141","gstbRwjz":"0","gstbRwId":"757577185451056261","type":"424180858316970501","gstbRbztName":""}' \
  --insecure
"""

def print_result(test_name, response):
    """打印测试结果"""
    print(f"\n{'='*60}")
    print(f"测试: {test_name}")
    print(f"{'='*60}")
    print(f"状态码: {response.status_code}")
    try:
        data = response.json()
        print(f"响应: {json.dumps(data, indent=2, ensure_ascii=False)}")
        return data
    except:
        print(f"响应: {response.text}")
        return None

def test_1_save_config():
    """测试1: 保存配置"""
    url = f"{BASE_URL}/worktime-api/config?username={USERNAME}"
    data = {
        "curl_template": TEST_CURL
    }
    response = requests.post(url, json=data)
    result = print_result("保存配置", response)
    
    assert response.status_code == 200, "保存配置失败"
    assert result['success'], "保存配置返回失败"
    assert result['parsed']['authorization'], "未能解析Authorization"
    assert result['parsed']['cookie'], "未能解析Cookie"
    assert result['parsed']['template_data'], "未能解析模板数据"
    
    print("配置保存成功，解析正确")
    return result

def test_2_get_config():
    """测试2: 获取配置"""
    url = f"{BASE_URL}/worktime-api/config?username={USERNAME}"
    response = requests.get(url)
    result = print_result("获取配置", response)
    
    assert response.status_code == 200, "获取配置失败"
    assert result['success'], "获取配置返回失败"
    assert result['config']['curl_template'], "未获取到curl_template"
    
    print("配置读取成功")
    return result

def test_3_mock_generate_records():
    """测试3: 模拟生成记录（不调用外部API）"""
    print(f"\n{'='*60}")
    print(f"测试: 模拟生成记录（手动插入数据）")
    print(f"{'='*60}")
    
    # 手动插入几条测试记录
    import os, pymysql
    conn = pymysql.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        user=os.environ.get('DB_USER', 'root'),
        password=os.environ.get('DB_PASSWORD', ''),
        database=os.environ.get('DB_NAME', 'chronos'),
        charset='utf8mb4'
    )
    cursor = conn.cursor()
    
    # 清空测试用户的旧数据
    cursor.execute("DELETE FROM work_records WHERE username = %s", (USERNAME,))
    
    # 插入测试数据
    test_dates = [
        ('2025-12-01', 8.0, 0.0),
        ('2025-12-02', 8.0, 2.0),
        ('2025-12-03', 8.0, 1.5),
        ('2025-12-04', 8.0, 0.0),
        ('2025-12-05', 8.0, 3.0),
    ]
    
    for date, normal, overtime in test_dates:
        cursor.execute("""
            INSERT INTO work_records (username, work_date, normal_hours, overtime_hours, status)
            VALUES (%s, %s, %s, %s, 'pending')
        """, (USERNAME, date, normal, overtime))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    print(f"已插入 {len(test_dates)} 条测试记录")

def test_4_get_records():
    """测试4: 获取记录列表和统计"""
    url = f"{BASE_URL}/worktime-api/records?username={USERNAME}"
    response = requests.get(url)
    result = print_result("获取记录和统计", response)
    
    assert response.status_code == 200, "获取记录失败"
    assert result['success'], "获取记录返回失败"
    assert len(result['data']) > 0, "没有记录数据"
    assert result['statistics'], "没有统计信息"
    
    print(f"获取到 {len(result['data'])} 条记录")
    print(f"统计信息:")
    stats = result['statistics']
    print(f"   正常工时: {stats['total_normal_hours']} 小时")
    print(f"   加班工时: {stats['total_overtime_hours']} 小时")
    print(f"   总工时: {stats['total_hours']} 小时")
    print(f"   人天: {stats['person_days']}")
    print(f"   人月: {stats['person_months']}")
    
    return result

def test_5_update_record():
    """测试5: 更新记录"""
    # 先获取一条记录
    url = f"{BASE_URL}/worktime-api/records?username={USERNAME}"
    response = requests.get(url)
    result = response.json()
    
    if result['data']:
        record = result['data'][0]
        record_id = record['id']
        
        # 更新工时
        url = f"{BASE_URL}/worktime-api/records?username={USERNAME}"
        update_data = {
            "id": record_id,
            "normal_hours": 7.5,
            "overtime_hours": 2.5
        }
        response = requests.put(url, json=update_data)
        result = print_result("更新记录", response)
        
        assert response.status_code == 200, "更新记录失败"
        assert result['success'], "更新记录返回失败"
        
        print(f"记录 {record_id} 更新成功")
        return result

def test_6_export_excel():
    """测试6: 导出Excel"""
    url = f"{BASE_URL}/worktime-api/excel/export?username={USERNAME}"
    response = requests.get(url)
    
    print(f"\n{'='*60}")
    print(f"测试: 导出Excel")
    print(f"{'='*60}")
    print(f"状态码: {response.status_code}")
    
    assert response.status_code == 200, "导出Excel失败"
    assert response.headers['Content-Type'].startswith('application/vnd.openxmlformats'), "返回类型不正确"
    
    # 保存Excel文件
    filename = f"test_export_{USERNAME}.xlsx"
    with open(filename, 'wb') as f:
        f.write(response.content)
    
    print(f"Excel导出成功，文件大小: {len(response.content)} 字节")
    print(f"已保存到: {filename}")
    
    return filename

def test_7_import_excel():
    """测试7: 导入Excel"""
    import openpyxl
    
    # 创建一个测试Excel文件
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "工时记录"
    
    # 先获取现有记录
    url = f"{BASE_URL}/worktime-api/records?username={USERNAME}"
    response = requests.get(url)
    records = response.json()['data']
    
    # 写入表头
    ws.append(['ID', '日期', '星期', '正常工时', '加班工时', '状态', '创建时间'])
    
    # 写入数据（修改工时）
    for record in records[:2]:  # 只修改前2条
        ws.append([
            record['id'],
            record['date'],
            '周一',
            9.0,  # 修改正常工时
            1.0,  # 修改加班工时
            record['status'],
            record['created_at']
        ])
    
    # 保存测试文件
    test_file = f"test_import_{USERNAME}.xlsx"
    wb.save(test_file)
    
    # 导入Excel
    url = f"{BASE_URL}/worktime-api/excel/import?username={USERNAME}"
    with open(test_file, 'rb') as f:
        files = {'file': (test_file, f, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
        response = requests.post(url, files=files)
    
    result = print_result("导入Excel", response)
    
    assert response.status_code == 200, "导入Excel失败"
    assert result['success'], "导入Excel返回失败"
    
    print(f"Excel导入成功")
    print(f"测试文件: {test_file}")
    
    return result

def run_all_tests():
    """运行所有测试"""
    print("\n" + "="*60)
    print("开始后端API测试")
    print("="*60)
    
    try:
        # 测试1: 保存配置
        test_1_save_config()
        
        # 测试2: 获取配置
        test_2_get_config()
        
        # 测试3: 生成记录（模拟数据）
        test_3_mock_generate_records()
        
        # 测试4: 获取记录和统计
        test_4_get_records()
        
        # 测试5: 更新记录
        test_5_update_record()
        
        # 测试6: 导出Excel
        test_6_export_excel()
        
        # 测试7: 导入Excel
        test_7_import_excel()
        
        # 再次获取记录验证更新
        print(f"\n{'='*60}")
        print("验证Excel导入后的数据")
        print("="*60)
        test_4_get_records()
        
        print("\n" + "="*60)
        print("所有测试通过！")
        print("="*60)
        
    except AssertionError as e:
        print(f"\n测试失败: {e}")
    except Exception as e:
        print(f"\n测试出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    run_all_tests()
