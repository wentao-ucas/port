# -*- coding: utf-8 -*-
"""本地验证 SubmitHandler 的并发提交逻辑（无需内网/MySQL）。

直接 import 真实的 submit_one（app.py 里 handler 用的同一个函数），在 WT_MOCK=1 下
模拟上游 ~1s/条，对比「串行 vs 并发」耗时，并校验保序 + 成败计数。
跑：  C:\\Users\\wentao\\.conda\\envs\\tornado\\python.exe test_submit_concurrency.py
"""
import os
import sys
import time
import asyncio

os.environ['WT_MOCK'] = '1'   # 必须在 import app 前设，submit_one 据此走假提交
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import submit_one  # noqa: E402

URL = 'http://mock/local'
HEADERS = {}

# 5 条：4 条正常(8h)应成功，1 条(8.5h)应失败 —— 复刻真实「大于8小时」拒绝
SUBMITS = [
    {'gstbZcgz': '8'},
    {'gstbZcgz': '8'},
    {'gstbZcgz': '8.5'},   # 期望失败
    {'gstbZcgz': '8'},
    {'gstbZcgz': '8'},
]


async def run_concurrent(sem_size):
    sem = asyncio.Semaphore(sem_size)
    t0 = time.perf_counter()
    outcomes = await asyncio.gather(
        *(submit_one(URL, HEADERS, sd, sem) for sd in SUBMITS),
        return_exceptions=True,
    )
    return time.perf_counter() - t0, outcomes


async def run_serial():
    """模拟改之前的串行 + 每条 sleep(0.5)。"""
    sem = asyncio.Semaphore(1)  # 并发1=串行
    t0 = time.perf_counter()
    outcomes = []
    for sd in SUBMITS:
        outcomes.append(await submit_one(URL, HEADERS, sd, sem))
        await asyncio.sleep(0.5)  # 复刻旧代码逐条 sleep(0.5)
    return time.perf_counter() - t0, outcomes


def summarize(outcomes):
    ok = sum(1 for o in outcomes if not isinstance(o, Exception) and o[0])
    fail = len(outcomes) - ok
    return ok, fail


async def main():
    print(f"WT_MOCK={os.environ.get('WT_MOCK')}  共 {len(SUBMITS)} 条（含1条8.5h应失败）\n")

    t_serial, out_serial = await run_serial()
    ok_s, fail_s = summarize(out_serial)
    print(f"[串行+sleep0.5]  耗时 {t_serial:5.2f}s   成功 {ok_s} 失败 {fail_s}   结果序 {out_serial}")

    t_conc, out_conc = await run_concurrent(5)
    ok_c, fail_c = summarize(out_conc)
    print(f"[并发 sem=5  ]  耗时 {t_conc:5.2f}s   成功 {ok_c} 失败 {fail_c}   结果序 {out_conc}")

    print()
    # 校验：成败计数两种方式一致 & 保序（第3条必失败，其余成功）
    assert out_conc == out_serial, '并发结果顺序/内容与串行不一致！'
    assert (ok_c, fail_c) == (4, 1), f'计数不对：{(ok_c, fail_c)}'
    assert out_conc[2][0] is False and out_conc[2][1].startswith('400'), '第3条(8.5h)应失败'
    assert t_conc < t_serial / 2, f'并发未明显提速：{t_conc:.2f}s vs {t_serial:.2f}s'
    print(f"✅ 通过：保序OK、计数OK(4成1败)、并发提速 {t_serial / t_conc:.1f}x（{t_serial:.2f}s → {t_conc:.2f}s）")


if __name__ == '__main__':
    asyncio.run(main())
