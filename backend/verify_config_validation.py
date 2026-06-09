# -*- coding: utf-8 -*-
"""验证 ConfigHandler 防呆：粘错(Copy all / 无效data-raw)要拦，单条正确 与 纯查询curl 要放行。"""
import io, sys, os, time, json, base64, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import requests

PORT = 18764
BASE = f'http://localhost:{PORT}/worktime-api'
def jwt():
    p = base64.urlsafe_b64encode(json.dumps({"user_id":"cfgval_uid","user_name":"校验"}).encode()).decode().rstrip('=')
    return f'bearer eyJhbGciOiJIUzI1NiJ9.{p}.sig'
A = jwt()

env = dict(os.environ, APP_PORT=str(PORT), WT_MOCK='1')
proc = subprocess.Popen([sys.executable, 'app.py'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
try:
    for _ in range(40):
        try: requests.post(f'{BASE}/login', json={}, timeout=2); break
        except Exception: time.sleep(0.5)
    tok = requests.post(f'{BASE}/login', json={'username':os.environ.get('ACCESS_USER','admin'),'password':os.environ.get('ACCESS_PASSWORD','changeme')}, timeout=5).json()['token']
    H = {'X-Access-Token': tok}
    def save(curl):
        return requests.post(f'{BASE}/config', headers=H, json={'curl_template': curl}, timeout=8).json()

    RW = 'http://xiaokong.cfid.cn/api/example/Gstb/reportWorkingHours?n=0'
    cases = [
        ("单条正确 reportWorkingHours", True,
         f"curl '{RW}' -H 'Authorization: {A}' --data-raw '{{\"gstbRwId\":\"816228889847144453\",\"gstbGzlx\":\"378106982789290181\",\"gstbZcgz\":\"0.0\"}}' "),
        ("Copy all(多条curl)", False,
         f"curl 'http://xiaokong.cfid.cn/api/example/Gzrwb/getMyTask' -H 'Authorization: {A}' \ncurl '{RW}' -H 'Authorization: {A}' --data-raw '{{\"gstbRwId\":\"1\"}}' "),
        ("含reportWorkingHours但无有效data-raw", False,
         f"curl '{RW}' -H 'Authorization: {A}' "),
        ("纯查询 getInitMsg(无reportWorkingHours)", True,
         f"curl 'http://xiaokong.cfid.cn/api/example/Gstb/getInitMsg/0/123' -H 'Authorization: {A}' "),
    ]
    allok = True
    for name, expect_ok, curl in cases:
        r = save(curl)
        got = bool(r.get('success'))
        ok = (got == expect_ok)
        allok &= ok
        print(f'[{"OK" if ok else "FAIL"}] {name}: success={got} (期望{expect_ok}) can_submit={r.get("can_submit")} msg={r.get("message","")[:40]}')
    print('\n结论:', '防呆校验全部符合预期' if allok else '有用例不符，需排查')
finally:
    proc.terminate()
    try: proc.wait(timeout=5)
    except Exception: proc.kill()
