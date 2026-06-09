# -*- coding: utf-8 -*-
"""前后端联动演示：工作内容是否真的传到上游。
开一个本地"假上游"抓包服务器，跑通 登录→保存配置(懒人式空gstbGzbg)→生成待填报→改工作内容→提交 整条链路，
看上游收到的 gstbGzbg。对比【修复前 app_pre_handlers_refactor.py】和【修复后 app.py】。
不涉及真实凭证（合成JWT），WT_MOCK 关闭（这样提交会真发 HTTP 到假上游）。
"""
import os, sys, time, json, base64, threading, subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
import requests

CAP_PORT = 18799
BE_PORT = 18763
CAP_URL = f'http://localhost:{CAP_PORT}/api/reportWorkingHours?n=0'
BASE = f'http://localhost:{BE_PORT}/worktime-api'
UID = 'demo_wc_uid'
CONTENT = '完成订单模块联调测试'   # 用户在记录页填的工作内容

captured = []   # 假上游收到的提交体

class Cap(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(n)
        try:
            captured.append(json.loads(body))
        except Exception:
            captured.append({'_raw': body.decode('utf-8', 'replace')})
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers()
        self.wfile.write(b'{"code":200,"msg":"ok"}')
    def log_message(self, *a): pass

def jwt(uid, uname):
    p = base64.urlsafe_b64encode(json.dumps({'user_id': uid, 'user_name': uname}).encode()).decode().rstrip('=')
    return f'bearer eyJhbGciOiJIUzI1NiJ9.{p}.sig'

# 懒人式配置：URL 指向假上游、含 reportWorkingHours(才能提交)，--data-raw 模板里 gstbGzbg 是空的
CURL = (f"curl '{CAP_URL}' -H 'Authorization: {jwt(UID, '内容演示')}' -b 'JSESSIONID=demo' "
        f"""--data-raw '{{"gstbGzbg": "", "gstbRwId": "T1", "gstbRwmc": "演示任务", "gstbSsxm": "X", """
        f""""gstbRwzt": "402723309315163141", "_jhKsDate": "2026-01-01", "_jhJsDate": "2026-12-31"}}' """)

def run_once(label, module):
    captured.clear()
    env = {k: v for k, v in os.environ.items() if k != 'WT_MOCK'}   # 关 WT_MOCK，提交才会真发HTTP
    env['APP_PORT'] = str(BE_PORT)
    proc = subprocess.Popen([sys.executable, module], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        for _ in range(40):
            try: requests.post(f'{BASE}/login', json={}, timeout=2); break
            except Exception: time.sleep(0.5)
        tok = requests.post(f'{BASE}/login', json={'username': os.environ.get('ACCESS_USER', 'admin'), 'password': os.environ.get('ACCESS_PASSWORD', 'changeme')}, timeout=5).json()['token']
        H = {'X-Access-Token': tok}
        # 1) 保存配置（前端"保存配置"做的事）
        r = requests.post(f'{BASE}/config', headers=H, json={'curl_template': CURL}, timeout=8).json()
        assert r.get('success'), r
        # 2) 生成待填报（前端日历"生成待填报"）
        requests.post(f'{BASE}/fill-draft', headers=H, params={'username': UID},
                      json={'items': [{'date': '2026-06-16', 'normal_hours': 8, 'overtime_hours': 0}]}, timeout=8)
        recs = requests.get(f'{BASE}/records', headers=H, params={'username': UID}, timeout=8).json()['data']
        rid = recs[0]['id']
        before_content = recs[0]['work_content']
        # 3) 记录页改工作内容（前端 el-input @change → PUT /records）
        requests.put(f'{BASE}/records', headers=H, params={'username': UID},
                     json={'id': rid, 'normal_hours': 8, 'overtime_hours': 0, 'work_content': CONTENT}, timeout=8)
        # 4) 提交（真发 HTTP 到假上游）
        requests.post(f'{BASE}/submit', headers=H, params={'username': UID}, json={'record_ids': [rid]}, timeout=15)
        time.sleep(0.3)
        # 清理本次记录
        requests.request('DELETE', f'{BASE}/records', headers=H, params={'username': UID}, json={'ids': [rid]}, timeout=8)
        sent = captured[0] if captured else {}
        print(f'\n===== {label} =====')
        print(f'  记录页工作内容(默认): {before_content!r}  → 用户改为: {CONTENT!r}')
        print(f'  上游实际收到 gstbGzbg = {sent.get("gstbGzbg")!r}')
        print(f'  (顺带核对 gstbZcgz={sent.get("gstbZcgz")!r}, gstbRwjz={sent.get("gstbRwjz")!r}, 含_jhKsDate={"_jhKsDate" in sent})')
        return sent.get('gstbGzbg')
    finally:
        proc.terminate()
        try: proc.wait(timeout=5)
        except Exception: proc.kill()

cap = HTTPServer(('localhost', CAP_PORT), Cap)
threading.Thread(target=cap.serve_forever, daemon=True).start()
print(f'假上游抓包服务器已起 :{CAP_PORT}')

old = run_once('修复前 (app_pre_handlers_refactor.py)', 'app_pre_handlers_refactor.py')
new = run_once('修复后 (app.py)', 'app.py')

print('\n' + '=' * 50)
print(f'修复前 上游收到工作内容: {old!r}')
print(f'修复后 上游收到工作内容: {new!r}')
ok = (not old) and (new == CONTENT)
print('结论:', '通过 —— 修复前传空、修复后正确带上用户填的内容' if ok else '!! 未达预期')
cap.shutdown()
sys.exit(0 if ok else 1)
