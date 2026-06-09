# -*- coding: utf-8 -*-
"""重构后端到端冒烟：在 18761 起一个 WT_MOCK 测试实例，跑遍各 handler 模块的接口，跑完关掉。
跑：C:\\Users\\wentao\\.conda\\envs\\tornado\\python.exe run_smoke.py
"""
import os
import sys
import json
import time
import base64
import subprocess
import requests

# 给所有请求加默认超时 + 关 keep-alive（二进制响应后复用连接易卡），避免静默挂起
_req = requests.Session.request
def _patched(self, *a, **k):
    k.setdefault('timeout', 8)
    h = dict(k.get('headers') or {})
    h.setdefault('Connection', 'close')
    k['headers'] = h
    return _req(self, *a, **k)
requests.Session.request = _patched

PORT = 18761
BASE = f'http://localhost:{PORT}/worktime-api'
ZW = '100000000000000001'           # 种子 demo 用户的 user_id（与 seed_demo.py 一致，仅作隔离键）
T = f'smoke_{int(time.time())}'     # 每次唯一的一次性测试用户（避免跨run累积）

passed, failed = [], []
def ok(name, cond, extra=''):
    (passed if cond else failed).append(name)
    print(('  PASS ' if cond else '  FAIL ') + name + (f'  {extra}' if extra else ''))

def fake_token(uid, uname):
    p = base64.urlsafe_b64encode(json.dumps({'user_id': uid, 'user_name': uname}).encode()).decode().rstrip('=')
    return f'bearer eyJhbGciOiJIUzI1NiJ9.{p}.sig'

env = dict(os.environ, APP_PORT=str(PORT), WT_MOCK='1')
proc = subprocess.Popen([sys.executable, 'app.py'], env=env,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
try:
    # 等待启动
    up = False
    for _ in range(40):
        try:
            requests.post(f'{BASE}/login', json={}, timeout=2); up = True; break
        except Exception:
            time.sleep(0.5)
    if not up:
        print('!! 服务器未起来'); print(proc.stdout.read() if proc.stdout else ''); sys.exit(1)
    print(f'测试实例已起 (:{PORT}, WT_MOCK=1)\n')

    # ---- base + auth ----
    r = requests.post(f'{BASE}/login', json={'username': 'admin', 'password': 'wrong'})
    ok('登录-错密码返回401', r.status_code == 401)
    r = requests.post(f'{BASE}/login', json={'username': os.environ.get('ACCESS_USER', 'admin'), 'password': os.environ.get('ACCESS_PASSWORD', 'changeme')})
    tok = r.json().get('token')
    ok('登录-正确-拿到token', bool(tok))
    H = {'X-Access-Token': tok}
    ok('无token访问受保护接口401', requests.get(f'{BASE}/records', params={'username': ZW}).status_code == 401)
    ok('坏token访问401', requests.get(f'{BASE}/records', headers={'X-Access-Token': 'garbage'}, params={'username': ZW}).status_code == 401)

    # ---- config (GET) ----
    r = requests.get(f'{BASE}/config', headers=H, params={'username': ZW}).json()
    ok('config GET', r.get('success') is True, f"can_submit={r.get('can_submit')}")

    # ---- worktime: query (WT_MOCK 可报工时) ----
    r = requests.post(f'{BASE}/query-worktime', headers=H, params={'username': ZW},
                      json={'start_date': '2026-06-01', 'end_date': '2026-06-07'}).json()
    ok('query-worktime', r.get('success') and len(r.get('data', [])) == 7, f"days={len(r.get('data',[]))}")

    # ---- records GET ----
    r = requests.get(f'{BASE}/records', headers=H, params={'username': ZW}).json()
    ok('records GET (demo user)', r.get('success') and 'statistics' in r, f"n={len(r.get('data',[]))}")

    # ---- tasks: my-tasks (WT_MOCK 13) ----
    r = requests.post(f'{BASE}/my-tasks', headers=H, params={'username': ZW}, json={}).json()
    ok('my-tasks (mock=13)', r.get('success') and len(r.get('data', [])) == 13)

    # ---- tasks: preview-tasks (合成token) ----
    r = requests.post(f'{BASE}/preview-tasks', headers=H,
                      json={'curl': "curl 'x' -H 'Authorization: " + fake_token('smoke1', 'smoke') + "'"}).json()
    ok('preview-tasks (mock=13)', r.get('success') and len(r.get('data', [])) == 13)

    # ---- records lifecycle on throwaway user (fill-draft → batch → put → custom → excel → delete) ----
    r = requests.post(f'{BASE}/fill-draft', headers=H, params={'username': T},
                      json={'items': [{'date': '2026-06-10', 'normal_hours': 8, 'overtime_hours': 0},
                                      {'date': '2026-06-11', 'normal_hours': 8, 'overtime_hours': 2}]}).json()
    ok('fill-draft 生成', r.get('success') and r.get('count') == 2)
    r = requests.get(f'{BASE}/records', headers=H, params={'username': T}).json()
    recs = r.get('data', [])
    ids = [x['id'] for x in recs]
    ok('records GET (throwaway=2)', len(recs) == 2)
    r = requests.post(f'{BASE}/records/batch', headers=H, params={'username': T},
                      json={'field': 'content', 'value': '冒烟测试', 'ids': ids}).json()
    ok('records/batch 改列', r.get('success') and r.get('count') == 2)
    if ids:
        r = requests.put(f'{BASE}/records', headers=H, params={'username': T},
                         json={'id': ids[0], 'normal_hours': 4, 'overtime_hours': 1, 'work_content': '改一条'}).json()
        ok('records PUT 单条', r.get('success') is True)
    r = requests.post(f'{BASE}/custom', headers=H, params={'username': T},
                      json={'start_date': '2026-07-01', 'end_date': '2026-07-02', 'normal_hours': 8,
                            'overtime_hours': 0, 'work_content': 'custom', 'include_weekend': True}).json()
    ok('custom 自定义工时', r.get('success') is True)
    r = requests.get(f'{BASE}/excel/export', headers=H, params={'username': T})
    ok('excel 导出', r.status_code == 200 and r.content[:2] == b'PK', f'bytes={len(r.content)}')
    # 清理：删掉 throwaway 用户全部记录（teardown，带重试；失败不影响功能结论）
    allids = []
    for attempt in range(3):
        try:
            r = requests.get(f'{BASE}/records', headers=H, params={'username': T}).json()
            allids = [x['id'] for x in r.get('data', [])]
            break
        except Exception as e:
            print(f'  (cleanup GET 第{attempt+1}次: {type(e).__name__})')
    if allids:
        try:
            r = requests.request('DELETE', f'{BASE}/records', headers=H, params={'username': T}, json={'ids': allids}).json()
            ok('records DELETE 清理', r.get('success'), f"deleted={r.get('count')}")
        except Exception as e:
            print(f'  (cleanup DELETE 跳过: {type(e).__name__})')

    print(f'\n==== 通过 {len(passed)} / 失败 {len(failed)} ====')
    if failed:
        print('失败项:', failed)
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    print('测试实例已关闭')

sys.exit(1 if failed else 0)
