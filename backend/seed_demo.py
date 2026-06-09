# -*- coding: utf-8 -*-
"""本地演示数据：造 demo_user 的 user_config + 混合状态 work_records，供本地点点看。
只连本地库(config 默认 localhost/chronos)。重复跑会先清该用户旧数据再插，幂等。
跑：  C:\\Users\\wentao\\.conda\\envs\\tornado\\python.exe seed_demo.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import base64
import json
import pymysql
from config import DB_CONFIG

UID = '100000000000000001'      # demo 用户 user_id（业务身份隔离键，演示用合成值）
UNAME = 'demo_user'


def _demo_token(uid, uname):
    """运行时合成一个 demo 身份 token（不验签，identity_from_token 只解 payload）。
    不含任何真实凭证；payload 的 user_id 与上面的 UID 保持一致以便演示数据自洽。"""
    b = lambda o: base64.urlsafe_b64encode(json.dumps(o).encode()).decode().rstrip('=')
    return ('bearer ' + b({"alg": "HS256", "typ": "JWT"}) + '.'
            + b({"user_id": uid, "user_name": uname, "exp": 4102329600000}) + '.demosig')


TOKEN = _demo_token(UID, UNAME)
COOKIE = 'JSESSIONID=DEMO00000000000000000000000000DEMO'
TEMPLATE = '{"gstbGzbg":"信创分区集成与系统迁移工作"}'

C1 = '信创分区集成与系统迁移工作'
C2 = '集中监控系统集成阶段'
C3 = '日常开发工作'

# (date, normal, overtime, content, status, avail_normal, avail_overtime)
records = [
    # ===== 历史已提交（1-5 月，进“历史记录”页）=====
    ('2026-01-05', 8, 0,   C1, 'submitted', 8, 0),
    ('2026-01-06', 8, 0,   C1, 'submitted', 8, 0),
    ('2026-01-07', 8, 2,   C1, 'submitted', 8, 2),
    ('2026-02-09', 8, 0,   C2, 'submitted', 8, 0),
    ('2026-02-10', 8, 0,   C2, 'submitted', 8, 0),
    ('2026-02-11', 8, 1.5, C2, 'submitted', 8, 2),
    ('2026-03-03', 8, 0,   C1, 'submitted', 8, 0),
    ('2026-03-04', 8, 0,   C1, 'submitted', 8, 0),
    ('2026-03-05', 8, 0,   C1, 'submitted', 8, 0),
    ('2026-04-01', 8, 0,   C2, 'submitted', 8, 0),
    ('2026-04-02', 8, 2,   C2, 'submitted', 8, 2),
    ('2026-04-03', 8, 0,   C2, 'submitted', 8, 0),
    ('2026-05-06', 8, 0,   C1, 'submitted', 8, 0),
    ('2026-05-07', 8, 2,   C1, 'submitted', 8, 2),
    ('2026-05-08', 8, 0,   C1, 'submitted', 8, 0),
    # ===== 本月待填报（pending，进“待处理”页）=====
    ('2026-06-02', 8, 0,   C3, 'pending',   8, 2),
    ('2026-06-03', 8, 0,   C3, 'pending',   8, 2),
    ('2026-06-04', 8, 0,   C3, 'pending',   8, 2),
    # ===== 提交失败（failed，也进“待处理”页，可补提交）=====
    ('2026-06-01', 8.5, 0, C3, 'failed',    8, 2),
    ('2026-06-05', 8, 0,   C3, 'failed',    8, 2),
]

conn = pymysql.connect(
    host=DB_CONFIG['host'], port=DB_CONFIG['port'],
    user=DB_CONFIG['user'], password=DB_CONFIG['password'],
    database=DB_CONFIG['database'], charset='utf8mb4'
)
try:
    cur = conn.cursor()
    cur.execute("DELETE FROM work_records WHERE username=%s", (UID,))
    cur.execute("DELETE FROM user_configs WHERE username=%s", (UID,))
    cur.execute(
        "INSERT INTO user_configs(username, authorization, cookie, curl_template, template_data) "
        "VALUES(%s,%s,%s,%s,%s)",
        (UID, TOKEN, COOKIE, '', TEMPLATE)
    )
    cur.executemany(
        "INSERT INTO work_records(username, work_date, normal_hours, overtime_hours, "
        "work_content, status, avail_normal, avail_overtime) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
        [(UID, *r) for r in records]
    )
    conn.commit()
    cur.execute("SELECT status, COUNT(*) FROM work_records WHERE username=%s GROUP BY status", (UID,))
    stat = dict(cur.fetchall())
    print(f"造数据完成（用户 demo_user / {UID}）:")
    print(f"  user_configs: 1 条")
    print(f"  work_records: {sum(stat.values())} 条 -> {stat}")
    cur.close()
finally:
    conn.close()
