# -*- coding: utf-8 -*-
"""把【懒人模式】【完整模式】最终提交体跟真实抓到的 reportWorkingHours --data-raw 逐字段 diff。
支持多条真实样本，并交叉核对"固定常量字段"在不同任务间是否真的恒定。
真实体只取字段值(不含 token，token 在 -H 头里)。stdout 强制 UTF-8 避免 GBK 报错。"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import datetime as dt
from types import SimpleNamespace
from handlers.common import build_lazy_template, date_to_ms
from handlers.worktime import build_submit_data

FIXED = ["gstbId","flowId","status","freeapproveruserid","flowUrgent","gstbGzlx","gstbFj",
         "gstbTbrq","gstbRwzt","type","gstbRbztName"]   # 应恒定的字段
TASKF = ["gstbRwId","gstbRwmc","gstbSsxm"]               # 任务带来的
USERF = ["gstbZcgz","gstbPtjb","gstbGzbg","gstbBgsj","gstbRwjz"]  # 用户/日期算出的

# 两条真实样本（--data-raw 字段值）+ 各自模拟的任务周期/记录（用于复现 gstbRwjz 与工时/内容）
SAMPLES = [
  {"name":"样本1 可观测-业务系统接入",
   "real":{"gstbId":0,"flowId":"","status":1,"freeapproveruserid":"","flowUrgent":1,"gstbGzlx":"378106982789290181","gstbZcgz":"0.0","gstbPtjb":"8.0","gstbGzbg":"系统开发","gstbFj":"[]","gstbTbrq":"","gstbBgsj":1775059200000,"gstbRwmc":"可观测-业务系统接入","gstbSsxm":"806492261847146437","gstbRwzt":"402723309315163141","gstbRwjz":"1","gstbRwId":"827434429352779845","type":"424180858316970501","gstbRbztName":""},
   "period":("2026-03-02","2026-12-30"), "date":dt.date(2026,4,2)},   # 在期内→gstbRwjz=1
  {"name":"样本2 系统上线",
   "real":{"gstbId":0,"flowId":"","status":1,"freeapproveruserid":"","flowUrgent":1,"gstbGzlx":"378106982789290181","gstbZcgz":"8.0","gstbPtjb":"0.0","gstbGzbg":"系统上线","gstbFj":"[]","gstbTbrq":"","gstbBgsj":1775232000000,"gstbRwmc":"系统上线","gstbSsxm":"668793195752069445","gstbRwzt":"402723309315163141","gstbRwjz":"0","gstbRwId":"816228889847144453","type":"424180858316970501","gstbRbztName":""},
   "period":("2024-01-01","2024-12-31"), "date":dt.date(2026,4,2)},   # 不在期内→gstbRwjz=0
]

def diff(label, sent, real):
    miss, extra = set(real)-set(sent), set(sent)-set(real)
    valdiff = [(k,sent.get(k),real[k]) for k in FIXED+TASKF+USERF
               if k != "gstbBgsj" and str(sent.get(k)) != str(real[k])]
    bgsj_ok = isinstance(sent.get("gstbBgsj"), int) and len(str(sent.get("gstbBgsj")))==13
    ok = not miss and not extra and not valdiff and bgsj_ok
    print(f'   {label:8} 漏发:{miss or "无"} 多发:{extra or "无"} 值不符:{valdiff or "无"} '
          f'gstbBgsj13位:{bgsj_ok} -> {"OK" if ok else "差异!"}')
    return ok

allok = True
for s in SAMPLES:
    real, (ks,js), d = s["real"], s["period"], s["date"]
    rec = SimpleNamespace(work_date=d, normal_hours=float(real["gstbZcgz"]),
                          overtime_hours=float(real["gstbPtjb"]), work_content=real["gstbGzbg"])
    task = {"id":real["gstbRwId"], "rwMc":real["gstbRwmc"], "xmId":real["gstbSsxm"], "jhKsDate":ks, "jhJsDate":js}
    print(f'\n== {s["name"]}  (真实 gstbRwjz={real["gstbRwjz"]}) ==')
    lazy = build_submit_data(build_lazy_template(task), rec)
    full = build_submit_data(dict(real), rec)
    allok &= diff("懒人模式", lazy, real)
    allok &= diff("完整模式", full, real)

# 交叉核对：两条样本的"固定字段"是否真的相同（证明 REPORT_FIXED 跨任务/项目恒定）
print('\n== 固定常量跨样本一致性 ==')
r1, r2 = SAMPLES[0]["real"], SAMPLES[1]["real"]
const_ok = all(r1[k]==r2[k] for k in FIXED)
for k in FIXED:
    flag = "一致" if r1[k]==r2[k] else f"不一致! {r1[k]} vs {r2[k]}"
    print(f'   {k:18} = {r1[k]!r:24} {flag}')
allok &= const_ok

print(f'\n总结: {"两条真实样本 × 两种模式 全部字段一致、常量跨任务恒定" if allok else "存在差异，需排查"}')
