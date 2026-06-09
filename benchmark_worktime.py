# -*- coding: utf-8 -*-
"""
批量拉取可报工时 + 性能基准 + 数据导出（只读 getInitMsg，绝不填报）。

目的：用真实网络数据，决定该用哪种缓存/优化策略。
它会用同一份认证，把指定日期范围(默认半年)拉两遍：
  [A] 串行   —— 复刻当前后端实现的体感（逐日请求）
  [B] 并发   —— 用线程池并发请求，看能压到多快
然后导出每天的可报工时到 worktime_dump.csv，并打印对比 + 建议。

用法：
  1. 把你那段有效的 curl 整个粘到下面 CURL = r'''...''' 之间。
  2. 内网机器上跑：  python benchmark_worktime.py
     （中文乱码就先 set PYTHONIOENCODING=utf-8）
  3. 把打印的“===== 结论 =====”那段贴回来即可。
"""

# ============================================================
#  把你的整段 curl 粘到这对三引号之间（CurrentUser / 任意带 Authorization 的都行）
# ============================================================
CURL = r'''

'''
# ============================================================

import csv
import re
import sys
import time
import datetime as dt
from concurrent.futures import ThreadPoolExecutor

import requests
try:
    from requests.packages.urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
except Exception:
    pass

# -------- 可调参数 --------
START_DATE = dt.date(2026, 1, 1)
END_DATE = dt.date(2026, 6, 30)      # 默认半年
CONCURRENCY = 8                       # 并发线程数（别太大，免得触发限流）
SERIAL_SLEEP = 0.0                    # 串行每次额外 sleep（后端现用 0.2，这里测纯速度，结论里换算）
OUT_CSV = "worktime_dump.csv"
TIMEOUT = 15
# --------------------------


def extract_headers(curl: str) -> dict:
    headers = {}
    for h in re.findall(r"-H '([^']+)'", curl):
        if ":" in h:
            k, v = h.split(":", 1)
            headers[k.strip()] = v.strip()
    cb = re.search(r"-b '([^']+)'", curl)
    if cb:
        headers["Cookie"] = cb.group(1)
    return headers


def date_range(a, b):
    cur = a
    while cur <= b:
        yield cur
        cur += dt.timedelta(days=1)


def fetch_one(headers, day):
    """拉单日可报工时，返回(行dict, 单次耗时秒)。只读 getInitMsg。"""
    ts_ms = int(dt.datetime.combine(day, dt.time.min).timestamp() * 1000)
    now_ts = int(time.time())
    url = f"http://xiaokong.cfid.cn/api/example/Gstb/getInitMsg/0/{ts_ms}?n={now_ts}"
    row = {"date": day.isoformat(), "weekday": day.weekday() + 1,
           "ktbGs": "", "ktbJbGs": "", "code": "", "status": "err"}
    t0 = time.perf_counter()
    try:
        r = requests.get(url, headers=headers, timeout=TIMEOUT, verify=False)
        j = r.json()
        row["code"] = j.get("code")
        data = j.get("data") or {}
        row["ktbGs"] = data.get("ktbGs", "")
        row["ktbJbGs"] = data.get("ktbJbGs", "")
        row["status"] = "ok" if j.get("code") == 200 else "bad"
    except Exception as e:
        row["err"] = str(e)[:120]
    return row, time.perf_counter() - t0


def pct(sorted_list, p):
    if not sorted_list:
        return 0.0
    k = int(round((len(sorted_list) - 1) * p))
    return sorted_list[k]


def report_times(name, wall, per_call):
    s = sorted(per_call)
    n = len(s)
    avg = sum(s) / n if n else 0
    print(f"\n--- {name} ---")
    print(f"天数: {n}   总墙钟: {wall:.2f}s")
    print(f"单次(ms)  avg={avg*1000:.0f}  min={s[0]*1000:.0f}  "
          f"p50={pct(s,0.5)*1000:.0f}  p95={pct(s,0.95)*1000:.0f}  max={s[-1]*1000:.0f}")
    return wall, avg


def main():
    curl = CURL.strip()
    if not curl:
        print("[错误] 还没粘 curl。请贴到脚本顶部 CURL = r'''...''' 之间。")
        sys.exit(1)
    headers = extract_headers(curl)
    if not any(k.lower() == "authorization" for k in headers):
        print("[错误] curl 里没解析到 Authorization 头。")
        sys.exit(1)

    days = list(date_range(START_DATE, END_DATE))
    print(f"范围: {START_DATE} ~ {END_DATE}  共 {len(days)} 天  并发={CONCURRENCY}")

    # [A] 串行
    print("\n[A] 串行拉取中...")
    rows_serial = {}
    serial_times = []
    t_start = time.perf_counter()
    for d in days:
        row, el = fetch_one(headers, d)
        rows_serial[d] = row
        serial_times.append(el)
        if SERIAL_SLEEP:
            time.sleep(SERIAL_SLEEP)
    serial_wall = time.perf_counter() - t_start
    report_times("串行", serial_wall, serial_times)

    # [B] 并发
    print("\n[B] 并发拉取中...")
    conc_times = []
    rows = {}
    t_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        futs = {ex.submit(fetch_one, headers, d): d for d in days}
        for fut in futs:
            d = futs[fut]
            row, el = fut.result()
            rows[d] = row
            conc_times.append(el)
    conc_wall = time.perf_counter() - t_start
    report_times("并发", conc_wall, conc_times)

    # 导出（用并发那轮的数据，含全部天）
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["date", "weekday", "ktbGs", "ktbJbGs", "code", "status"])
        for d in days:
            r = rows.get(d, {})
            w.writerow([r.get("date"), r.get("weekday"), r.get("ktbGs"),
                        r.get("ktbJbGs"), r.get("code"), r.get("status")])
    print(f"\n已导出每日可报工时 -> {OUT_CSV}")

    # 数据画像
    ok = [rows[d] for d in days if rows.get(d, {}).get("status") == "ok"]
    today = dt.date.today()
    hist = [d for d in days if d < today]
    print("\n===== 结论 =====")
    print(f"成功天数: {len(ok)}/{len(days)}  失败: {len(days)-len(ok)}")
    print(f"其中历史日期(<{today}): {len(hist)} 天 —— 这些可报工时是既成事实、永远不会再变。")

    serial_real = serial_wall + len(days) * SERIAL_SLEEP_REF  # 加回后端的 0.2 sleep
    print(f"\n现状(串行+每天0.2s sleep)实际约: {serial_real:.1f}s")
    print(f"纯串行(无sleep):            {serial_wall:.1f}s")
    print(f"并发({CONCURRENCY}线程):              {conc_wall:.1f}s  "
          f"=> 提速约 {serial_real/max(conc_wall,0.001):.1f} 倍")

    print("\n[建议]")
    print(" 1) 历史日期一次性落库(work_records)即可，永不重查 —— 缓存收益最大、最稳。")
    print(" 2) 查询先读库、只对缺失/当月日期打接口；当月给个几分钟短TTL。")
    print(" 3) 实在要实时拉，把串行改成并发(限并发)+去掉0.2 sleep，单这一项就能提速见上。")
    print(" 4) 看 worktime_dump.csv：若历史每天 ktbGs 都稳定(如恒为8.0)，更印证(1)可放心永久缓存。")


SERIAL_SLEEP_REF = 0.2  # 后端当前实现每天的 sleep，用于换算“现状”耗时

if __name__ == "__main__":
    main()
