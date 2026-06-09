# -*- coding: utf-8 -*-
"""配置体检：只读 user_configs，逐行解析校验（不碰内网）。
在能连到目标库的机器上跑：  python check_configs.py
加 --live 还会用每个 token 去 getInitMsg 实测一次（需内网，会真打 xiaokong）。
"""
import sys, io, json, base64, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pymysql
from config import DB_CONFIG

LIVE = '--live' in sys.argv
# 已实测的全局固定常量
CONST = {'gstbGzlx': '378106982789290181', 'gstbRwzt': '402723309315163141', 'type': '424180858316970501'}

def jwt_payload(auth):
    if not auth: return {}
    t = auth.strip()
    if t.lower().startswith('bearer '): t = t[7:].strip()
    try:
        p = t.split('.')[1]; p += '=' * (-len(p) % 4)
        return json.loads(base64.urlsafe_b64decode(p))
    except Exception:
        return {}

def tok_status(auth):
    exp = jwt_payload(auth).get('exp')
    if exp is None: return '无exp'
    try: exp = int(exp) / (1000 if int(exp) > 1e12 else 1)
    except Exception: return 'exp异常'
    left = exp - time.time()
    return f'已过期{int(-left/3600)}h前' if left < 0 else f'有效剩{left/3600:.1f}h'

def curl_kind(curl):
    c = curl or ''
    if 'reportWorkingHours' in c: return 'report(可提交)'
    if 'getMyProject' in c: return 'getMyProject(查询)'
    if 'getMyTask' in c: return 'getMyTask(查询)'
    if 'getInitMsg' in c: return 'getInitMsg(查询)'
    return '其他'

c = pymysql.connect(host=DB_CONFIG['host'], port=DB_CONFIG['port'], user=DB_CONFIG['user'],
                    password=DB_CONFIG['password'], database=DB_CONFIG['database'], charset='utf8mb4')
cur = c.cursor()
cur.execute('SELECT id, username, display_name, authorization, cookie, curl_template, template_data FROM user_configs ORDER BY id')
rows = cur.fetchall()
print(f'库 {DB_CONFIG["host"]}/{DB_CONFIG["database"]}  共 {len(rows)} 条配置\n')
for rid, uname, disp, auth, cookie, curl, td_json in rows:
    pl = jwt_payload(auth)
    td = {}
    try: td = json.loads(td_json) if td_json else {}
    except Exception: pass
    kind = curl_kind(curl)
    can_submit = ('reportWorkingHours' in (curl or '')) and bool(td) and ('gstbRwId' in td)
    name = disp or pl.get('user_name') or '?'
    print(f'[{rid}] user_id={uname}  显示名={name}  token={tok_status(auth)}')
    print(f'     配置类型={kind}  can_submit={can_submit}')
    if 'report' in kind:
        miss = [k for k in ('gstbRwId','gstbRwmc','gstbSsxm') if not td.get(k)]
        bad = [f'{k}={td.get(k)}!=应{v}' for k, v in CONST.items() if str(td.get(k)) != v]
        print(f'     任务={td.get("gstbRwmc","?")} 项目id={td.get("gstbSsxm","?")}'
              f'  缺字段={miss or "无"}  常量异常={bad or "无"}')
    else:
        print(f'     ⚠ 非报工模板,只能查询/识别身份,不能提交报工')
    if LIVE:
        import requests, urllib3; urllib3.disable_warnings()
        try:
            ms = int(time.time()) * 1000
            url = f'http://xiaokong.cfid.cn/api/example/Gstb/getInitMsg/0/{ms}?n={int(time.time())}'
            h = {'Authorization': auth, 'Cookie': cookie or '', 'fz-origin': 'pc',
                 'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json, text/plain, */*'}
            r = requests.get(url, headers=h, timeout=10, verify=False)
            print(f'     [live] getInitMsg HTTP {r.status_code}: {str(r.json())[:80]}')
        except Exception as e:
            print(f'     [live] 失败: {type(e).__name__} {e}')
    print()
c.close()
