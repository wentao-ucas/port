# -*- coding: utf-8 -*-
"""
认证有效性自测脚本（单文件，只读，不会填报任何数据）。

它从你贴进来的 curl 里取出 token + cookie，然后只去调【只读】的 getInitMsg 查询接口，
看认证还认不认。绝不会调 reportWorkingHours（那个才会真填报）。

用法：
  1. 把你那段 curl（reportWorkingHours 那段就行）整个粘到下面 CURL = r'''...''' 之间。
  2. 内网机器上跑：  python test_auth.py
     （Windows 若中文乱码：先  set PYTHONIOENCODING=utf-8  再跑。）
"""

# ============================================================
#  把你的整段 curl 粘到这对三引号之间（保持原样，多行没关系）
# ============================================================
CURL = r'''

'''
# ============================================================

import re
import sys
import json
import time
import base64
import datetime as dt

import requests
try:
    from requests.packages.urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
except Exception:
    pass


def b64url_decode(s: str) -> bytes:
    s += "=" * (-len(s) % 4)  # 补齐 padding
    return base64.urlsafe_b64decode(s)


def extract_token(curl: str):
    m = re.search(r"Authorization:\s*bearer\s+([A-Za-z0-9._\-]+)", curl, re.I)
    return m.group(1) if m else None


def extract_headers(curl: str) -> dict:
    """从 curl 里抽出所有 -H 头 + -b 的 cookie，原样复用（保证和浏览器一致）。"""
    headers = {}
    for h in re.findall(r"-H '([^']+)'", curl):
        if ":" in h:
            k, v = h.split(":", 1)
            headers[k.strip()] = v.strip()
    cb = re.search(r"-b '([^']+)'", curl)
    if cb:
        headers["Cookie"] = cb.group(1)
    return headers


def fmt(ts_sec: float) -> str:
    return dt.datetime.fromtimestamp(ts_sec).strftime("%Y-%m-%d %H:%M:%S")


def main():
    curl = CURL.strip()
    if not curl:
        print("[错误] 还没粘 curl。请把你那段 curl 贴到脚本顶部 CURL = r'''...''' 之间。")
        sys.exit(1)

    token = extract_token(curl)
    if not token:
        print("[错误] 没在 curl 里找到 Authorization bearer token，检查是否贴全。")
        sys.exit(1)

    # ---------- [离线] 解 JWT exp，判断 token 自身是否过期 ----------
    print("===== [离线] JWT 载荷 =====")
    parts = token.split(".")
    if len(parts) < 2:
        print("[错误] 不是合法 JWT（缺少 . 分段）")
        sys.exit(1)
    payload = json.loads(b64url_decode(parts[1]))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\n用户: {payload.get('user_name')}  (user_id={payload.get('user_id')})")

    exp = payload.get("exp")
    now_ms = int(time.time() * 1000)
    expired_offline = None
    if exp is None:
        print("[警告] 载荷里没有 exp，无法离线判断过期")
    else:
        exp = int(exp)
        exp_sec = exp / 1000 if exp > 1e12 else exp  # 13位=毫秒，10位=秒
        remain_h = (exp_sec - now_ms / 1000) / 3600
        print(f"exp 过期时间: {fmt(exp_sec)}")
        print(f"当前时间:     {fmt(now_ms / 1000)}")
        if remain_h > 0:
            expired_offline = False
            print(f"[结论] token 自身未过期，还剩 {remain_h:.1f} 小时（约 {remain_h/24:.1f} 天）")
        else:
            expired_offline = True
            print(f"[结论] token 自身已过期 {-remain_h:.1f} 小时（约 {-remain_h/24:.1f} 天）")

    # ---------- [在线] 只读验证 getInitMsg（不会填报） ----------
    print("\n===== [在线] 只读验证 getInitMsg（不会填报任何数据） =====")
    headers = extract_headers(curl)
    today = dt.date.today()
    ts_ms = int(dt.datetime.combine(today, dt.time.min).timestamp() * 1000)
    now_ts = int(time.time())
    url = f"http://xiaokong.cfid.cn/api/example/Gstb/getInitMsg/0/{ts_ms}?n={now_ts}"
    print(f"查询日期: {today}")
    print(f"URL: {url}")
    try:
        r = requests.get(url, headers=headers, timeout=10, verify=False)
        print(f"HTTP 状态: {r.status_code}")
        body = r.text
        print("响应体(前 600 字):")
        print(body[:600] if body.strip() else "(空)")

        if r.status_code >= 500:
            print(f"\n[结论] 服务端 {r.status_code}（服务/网关临时问题），跟你的认证无关，过会儿再试。")
            return
        try:
            j = r.json()
        except ValueError:
            print("\n[结论] 响应不是 JSON（多半被重定向到登录页）-> 认证已失效，需要重新抓 curl 换 token。")
            return
        data = j.get("data")
        code = j.get("code")
        msg = j.get("msg") or ""
        if isinstance(data, dict) and ("ktbGs" in data or "ktbJbGs" in data):
            print(f"\n[结论] 认证有效！可报工时 ktbGs={data.get('ktbGs')} "
                  f"ktbJbGs={data.get('ktbJbGs')}（{today} 当天）")
        elif code in (401, 403, 600) or ("登录" in msg) or ("重新登录" in msg):
            print(f"\n[结论] 认证已失效（code={code}, msg={msg}），需要重新抓 curl 换 token。")
        else:
            print(f"\n[结论] 返回了 JSON 但不是预期工时结构（code={j.get('code')}, msg={j.get('msg')}），看上面响应体判断。")
    except requests.exceptions.RequestException as e:
        print(f"[请求失败] {e}")
        print("[提示] 连不上说明当前网络访问不了内网 xiaokong.cfid.cn。"
              "请确认在内网机器上跑。离线 exp 结论仍然有效。")
        if expired_offline:
            print("[补充] 离线已判定 token 过期，即便能连上也大概率失效。")


if __name__ == "__main__":
    main()
