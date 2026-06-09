# -*- coding: utf-8 -*-
"""
并发压测：扫不同并发数，找“速度甜蜜点”和“出错上限”（只读 getInitMsg，绝不填报）。

回答两个问题：
  1. 并发能把拉取压多快？快到什么程度也许就不必上缓存。
  2. 服务端能扛多少并发？—— 这就是“多个同事同时拉”的总预算，
     因为对服务端而言，1个用户开32并发 == 32个用户各开1并发。

做法：对同一批 N 个日期，用不同并发数各拉一遍，记录总耗时/吞吐/单次分布/成功失败。
并发升高时若吞吐不再涨(饱和)或开始出现失败/超时 => 就到上限了。

用法：把有效 curl 贴进 CURL，内网跑：  python concurrency_sweep.py
（中文乱码先 set PYTHONIOENCODING=utf-8）
"""

# ============================================================
#  把你的整段 curl 粘到这对三引号之间
# ============================================================
CURL = r'''

'''
# ============================================================

import re
import sys
import time
import datetime as dt
from functools import partial
from concurrent.futures import ThreadPoolExecutor

import requests
try:
    from requests.packages.urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
except Exception:
    pass

# -------- 可调参数 --------
LEVELS = [1, 2, 4, 8, 16, 24, 32]   # 要扫的并发数
N_REQUESTS = 30                      # 每档拉多少个请求（同一批日期，保证可比）
TIMEOUT = 20
PAUSE_BETWEEN = 2.0                  # 每档之间歇口气，别把服务端打急
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


def fetch_one(headers, day):
    """拉单日，返回 (ok: bool, elapsed: float, tag: str)。tag 标记成功/失败原因。"""
    ts_ms = int(dt.datetime.combine(day, dt.time.min).timestamp() * 1000)
    now_ts = int(time.time())
    url = f"http://xiaokong.cfid.cn/api/example/Gstb/getInitMsg/0/{ts_ms}?n={now_ts}"
    t0 = time.perf_counter()
    try:
        r = requests.get(url, headers=headers, timeout=TIMEOUT, verify=False)
        el = time.perf_counter() - t0
        if r.status_code != 200:
            return False, el, f"http{r.status_code}"
        try:
            code = r.json().get("code")
        except ValueError:
            return False, el, "nonjson"
        if code == 200:
            return True, el, "ok"
        return False, el, f"code{code}"
    except requests.exceptions.Timeout:
        return False, time.perf_counter() - t0, "timeout"
    except Exception as e:
        return False, time.perf_counter() - t0, type(e).__name__


def pct(sorted_list, p):
    if not sorted_list:
        return 0.0
    k = int(round((len(sorted_list) - 1) * p))
    return sorted_list[k]


def run_level(headers, days, c):
    times, oks, fails = [], 0, {}
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=c) as ex:
        for ok, el, tag in ex.map(partial(fetch_one, headers), days):
            times.append(el)
            if ok:
                oks += 1
            else:
                fails[tag] = fails.get(tag, 0) + 1
    wall = time.perf_counter() - t0
    return wall, sorted(times), oks, fails


def main():
    curl = CURL.strip()
    if not curl:
        print("[错误] 还没粘 curl。请贴到脚本顶部 CURL = r'''...''' 之间。")
        sys.exit(1)
    headers = extract_headers(curl)
    if not any(k.lower() == "authorization" for k in headers):
        print("[错误] curl 里没解析到 Authorization 头。")
        sys.exit(1)

    today = dt.date.today()
    days = [today - dt.timedelta(days=i + 1) for i in range(N_REQUESTS)]
    print(f"每档 {N_REQUESTS} 个请求，扫并发: {LEVELS}\n")
    print(f"{'并发':>4} | {'总耗时s':>7} | {'吞吐req/s':>8} | {'avg':>5} | {'p95':>5} | "
          f"{'max':>5} | {'成功':>4} | 失败明细")
    print("-" * 78)

    results = []
    for c in LEVELS:
        wall, times, oks, fails = run_level(headers, days, c)
        thr = len(days) / wall if wall else 0
        avg = sum(times) / len(times) if times else 0
        fail_str = ", ".join(f"{k}:{v}" for k, v in fails.items()) or "-"
        print(f"{c:>4} | {wall:>7.2f} | {thr:>8.1f} | {avg*1000:>5.0f} | "
              f"{pct(times,0.95)*1000:>5.0f} | {times[-1]*1000:>5.0f} | "
              f"{oks:>4} | {fail_str}")
        results.append({"c": c, "wall": wall, "thr": thr, "fails": sum(fails.values())})
        time.sleep(PAUSE_BETWEEN)

    # ---- 结论 ----
    print("\n===== 结论 =====")
    best = max(results, key=lambda r: r["thr"])
    print(f"吞吐最高: 并发={best['c']}  {best['thr']:.1f} req/s  "
          f"(半年181天估算约 {181/best['thr']:.1f}s)")

    first_fail = next((r for r in results if r["fails"] > 0), None)
    if first_fail:
        print(f"首次出现失败: 并发={first_fail['c']}（{first_fail['fails']}个失败）"
              f" -> 安全并发上限约在它之下。")
    else:
        print(f"全程 0 失败 -> 到并发 {LEVELS[-1]} 都还稳，真实上限可能更高。")

    # 找吞吐饱和点：吞吐不再明显增长(<10%)的并发
    sat = None
    for i in range(1, len(results)):
        if results[i]["thr"] < results[i-1]["thr"] * 1.1:
            sat = results[i-1]["c"]
            break
    if sat:
        print(f"吞吐饱和点约在并发={sat}：再加并发基本不变快，服务端到瓶颈了。")

    print("\n[怎么用这些数]")
    print(" - 单用户拉半年的耗时 = 上面吞吐最高那档的估算值，自己判断够不够快。")
    print(" - 多个同事同时拉：他们共享同一个服务端，总并发别超过上面的安全上限；")
    print("   所以后端要对 xiaokong 的请求做【全局并发闸】(所有用户共用)，不是每人各开一把。")
    print(" - 若高并发已够快，可先不上复杂缓存，只做并发+全局限流；缓存留作进一步优化。")


if __name__ == "__main__":
    main()
