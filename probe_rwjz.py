# -*- coding: utf-8 -*-
"""
探查 gstbRwjz 字段来源（只读，调 getMyTask，不填报）。

思路：用 demo_user 的认证拉任务列表(getMyTask)，把【实测 gstbRwjz=0 的任务】和
     【=1 的任务】的全部字段拉出来逐个对比，看哪个字段驱动了 0/1。
     这两个任务都是 demo_user 的，一次就能同时拿到。

用法：把 demo_user 任意带认证的 curl 整段贴到下面 CURL=r'''...''' 之间，内网跑：
        python probe_rwjz.py
     把输出贴回来分析。
"""

# ============================================================
#  把 demo_user 的 curl 贴到这对三引号之间（任意带 Authorization 的都行）
# ============================================================
CURL = r'''

'''
# ============================================================

# 已知映射：任务id -> 实测提交时的 gstbRwjz（来自你给的 3 条报工 curl）
KNOWN = {
    "816228889847144453": 0,   # 系统上线
    "827434429352779845": 1,   # 可观测-业务系统接入
}

import re
import sys
import time
import json

import requests
try:
    from requests.packages.urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
except Exception:
    pass


def extract_headers(curl):
    headers = {}
    for h in re.findall(r"-H '([^']+)'", curl):
        if ":" in h:
            k, v = h.split(":", 1)
            headers[k.strip()] = v.strip()
    cb = re.search(r"-b '([^']+)'", curl)
    if cb:
        headers["Cookie"] = cb.group(1)
    return headers


def main():
    curl = CURL.strip()
    if not curl:
        print("[错误] 还没粘 curl。请贴到脚本顶部 CURL=r'''...''' 之间。")
        sys.exit(1)
    headers = extract_headers(curl)
    headers.setdefault('Content-Type', 'application/json;charset=UTF-8')
    if not any(k.lower() == 'authorization' for k in headers):
        print("[错误] curl 里没解析到 Authorization。")
        sys.exit(1)

    now = int(time.time())
    url = f"http://xiaokong.cfid.cn/api/example/Gzrwb/getMyTask?n={now}"
    body = {"superQueryJson": "", "currentPage": 1, "pageSize": 200,
            "sort": "desc", "sidx": "", "gchxmId": "", "lx": "XXH",
            "dataType": 1, "menuId": ""}
    try:
        r = requests.post(url, headers=headers, json=body, timeout=15, verify=False)
        rj = r.json()
    except Exception as e:
        print(f"[请求失败] {e}")
        sys.exit(1)

    if str(rj.get('code')) not in ('200', '0'):
        print("[接口返回非成功]", json.dumps(rj, ensure_ascii=False)[:300])
        sys.exit(1)

    tasks = (rj.get('data') or {}).get('list', []) or []
    print(f"共 {len(tasks)} 个任务")
    if tasks:
        print("getMyTask 返回字段:", list(tasks[0].keys()))

    found = {t.get('id'): t for t in tasks if t.get('id') in KNOWN}
    print(f"\n命中已知任务 {len(found)}/{len(KNOWN)} 个")
    for tid, t in found.items():
        print(f"\n===== 任务 {tid}  (实测 gstbRwjz={KNOWN[tid]})  {t.get('rwMc')} =====")
        print(json.dumps(t, ensure_ascii=False, indent=2))

    if len(found) >= 2:
        ids = list(found.keys())
        ta, tb = found[ids[0]], found[ids[1]]
        print(f"\n##### 字段差异：gstbRwjz={KNOWN[ids[0]]} 的任务  vs  gstbRwjz={KNOWN[ids[1]]} 的任务 #####")
        for k in sorted(set(ta) | set(tb)):
            if ta.get(k) != tb.get(k):
                print(f"  {k}:  [rwjz={KNOWN[ids[0]]}] {ta.get(k)}   |   [rwjz={KNOWN[ids[1]]}] {tb.get(k)}")
        print("\n=> 看上面哪个字段是 0/1 或层级类、且正好跟 rwjz 对得上，多半就是它的来源。")
    else:
        print("\n[提示] 没同时命中两个已知任务（可能不在你的任务列表里/被分页截断）。")
        print("       把 KNOWN 里的 id 换成你列表里看得到的任务，或抓「查看任务」弹窗的详情接口。")


if __name__ == "__main__":
    main()
