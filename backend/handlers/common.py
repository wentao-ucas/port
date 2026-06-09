# -*- coding: utf-8 -*-
"""跨 handler 共享的助手与常量：身份/时间解析、门禁令牌、任务与提交助手。"""
import os
import re
import json
import time
import base64
import hashlib
import hmac
from datetime import datetime, timezone, timedelta
import asyncio
import requests
import urllib3

from config import ACCESS_USER, ACCESS_PASSWORD, ACCESS_SALT

urllib3.disable_warnings()


# 东八区：报工时间戳显式按 Asia/Shanghai 计算，避免服务器时区(如UTC)导致日期错位
CST = timezone(timedelta(hours=8))


def date_to_ms(d):
    """某日 00:00（东八区）的毫秒时间戳"""
    return int(datetime.combine(d, datetime.min.time(), tzinfo=CST).timestamp() * 1000)


def identity_from_token(authorization):
    """从 Authorization(JWT) 解析稳定身份。
    返回 (user_id, user_name)，解析失败返回 (None, None)。
    注意：只解码 payload，不校验签名（过期 token 也能解析出身份）。
    """
    if not authorization:
        return None, None
    token = authorization.strip()
    if token.lower().startswith('bearer '):
        token = token[7:].strip()
    try:
        parts = token.split('.')
        if len(parts) < 2:
            return None, None
        payload = parts[1]
        payload += '=' * (-len(payload) % 4)  # 补齐 base64 padding
        data = json.loads(base64.urlsafe_b64decode(payload))
        uid = str(data.get('user_id') or '').strip()
        uname = str(data.get('user_name') or '').strip()
        return (uid or None), (uname or None)
    except Exception:
        return None, None


def exp_from_token(authorization):
    """从 JWT 解析 exp（毫秒时间戳），失败返回 None。用于前端认证过期提醒。"""
    if not authorization:
        return None
    token = authorization.strip()
    if token.lower().startswith('bearer '):
        token = token[7:].strip()
    try:
        parts = token.split('.')
        if len(parts) < 2:
            return None
        payload = parts[1] + '=' * (-len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        exp = data.get('exp')
        return int(exp) if exp is not None else None
    except Exception:
        return None


# 访问令牌：登录成功后下发「带签发时间戳 + HMAC 签名」的令牌，受保护接口校验签名+有效期（全局共享密码门禁）
ACCESS_TTL = 24 * 3600  # 门禁登录有效期(秒)：超过则需重新登录。要改时长改这里即可


_ACCESS_SECRET = f"{ACCESS_USER}:{ACCESS_PASSWORD}:{ACCESS_SALT}".encode()


def make_access_token():
    """生成门禁令牌：base64(签发时间戳.hmac签名)。每次登录都不同（含当时时间戳）。"""
    ts = str(int(time.time()))
    sig = hmac.new(_ACCESS_SECRET, ts.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{ts}.{sig}".encode()).decode()


def verify_access_token(token):
    """校验门禁令牌：签名正确 且 距签发未超过 ACCESS_TTL。"""
    if not token:
        return False
    try:
        ts, sig = base64.urlsafe_b64decode(token.encode()).decode().split('.', 1)
        expect = hmac.new(_ACCESS_SECRET, ts.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expect):
            return False
        return (int(time.time()) - int(ts)) <= ACCESS_TTL
    except Exception:
        return False


# ===== 懒人模式：用任意认证 curl + 选中任务，合成提交配置 =====
# 提交报工的固定字段（实测跨用户/项目/任务恒定）
REPORT_FIXED = {
    "gstbId": 0, "flowId": "", "status": 1, "freeapproveruserid": "",
    "flowUrgent": 1, "gstbGzlx": "378106982789290181", "gstbFj": "[]",
    "gstbTbrq": "", "gstbRwzt": "402723309315163141",
    "type": "424180858316970501", "gstbRbztName": "",
    "gstbZcgz": "0.0", "gstbPtjb": "0.0", "gstbGzbg": "", "gstbBgsj": 0,
    "gstbRwjz": "0",
}


def build_lazy_template(task):
    """用选中任务合成提交模板 template_data。
    _jhKsDate/_jhJsDate 仅供提交时算 gstbRwjz，发请求前会删除，不发给原系统。"""
    td = dict(REPORT_FIXED)
    td["gstbRwId"] = str(task.get("id", ""))
    td["gstbRwmc"] = str(task.get("rwMc", ""))
    td["gstbSsxm"] = str(task.get("xmId", ""))
    td["_jhKsDate"] = task.get("jhKsDate", "") or ""
    td["_jhJsDate"] = task.get("jhJsDate", "") or ""
    return td


def parse_auth_from_curl(curl):
    """从任意 curl 抽 Authorization + Cookie。"""
    auth = re.search(r"-H\s+'Authorization:\s*([^']+)'", curl or '')
    cookie = re.search(r"-b\s+'([^']+)'", curl or '')
    return (auth.group(1).strip() if auth else ''), (cookie.group(1).strip() if cookie else '')


# 本地演示假任务（WT_MOCK=1 时返回），覆盖进行中/已完成 + 不同时间，便于看排序
MOCK_TASKS = [
    {"id": "1", "rwMc": "可观测-业务系统接入", "rwZt": "进行中", "ssXm": "2026年生产云可观测平台升级优化研发项目", "xmId": "806492261847146437", "jhKsDate": "2026-03-02", "jhJsDate": "2026-12-30", "yqTs": 0, "roleName": "参与人", "lx": "工程化"},
    {"id": "2", "rwMc": "需求分析与设计", "rwZt": "进行中", "ssXm": "2025年数据服务目录与元数据管理研发", "xmId": "557094664985907077", "jhKsDate": "2025-09-01", "jhJsDate": "2026-08-30", "yqTs": 12, "roleName": "负责人", "lx": "研发"},
    {"id": "3", "rwMc": "集成联调", "rwZt": "进行中", "ssXm": "2025年生产系统运维系统集成项目", "xmId": "557094700000000001", "jhKsDate": "2025-06-15", "jhJsDate": "2026-03-31", "yqTs": 0, "roleName": "参与人", "lx": "工程化"},
    {"id": "4", "rwMc": "接口联调测试", "rwZt": "进行中", "ssXm": "2025年跨行账户信息认证平台改造", "xmId": "557088896165057925", "jhKsDate": "2025-11-10", "jhJsDate": "2026-05-30", "yqTs": 0, "roleName": "参与人", "lx": "工程化"},
    {"id": "5", "rwMc": "二期需求调研", "rwZt": "未开始", "ssXm": "2026年湖管平台优化改造工程", "xmId": "557090524704542597", "jhKsDate": "2026-07-01", "jhJsDate": "2026-10-31", "yqTs": 0, "roleName": "负责人", "lx": "研发"},
    {"id": "6", "rwMc": "性能优化方案", "rwZt": "未开始", "ssXm": "2026年交易核算系统功能优化工程", "xmId": "557090608926166917", "jhKsDate": "2026-05-20", "jhJsDate": "2026-09-30", "yqTs": 0, "roleName": "参与人", "lx": "工程化"},
    {"id": "7", "rwMc": "安全加固实施", "rwZt": "未开始", "ssXm": "2026年账户与支付业务风险监测系统优化", "xmId": "557090674789322629", "jhKsDate": "2026-04-15", "jhJsDate": "2026-08-15", "yqTs": 0, "roleName": "参与人", "lx": "工程化"},
    {"id": "8", "rwMc": "数据迁移评估", "rwZt": "已暂停", "ssXm": "2025年数据中台功能优化改造工程", "xmId": "557090642610622341", "jhKsDate": "2025-08-01", "jhJsDate": "2026-02-28", "yqTs": 30, "roleName": "参与人", "lx": "研发"},
    {"id": "9", "rwMc": "报表模块重构", "rwZt": "已暂停", "ssXm": "2025年计费管理子系统完善工程", "xmId": "557090707060297605", "jhKsDate": "2025-03-10", "jhJsDate": "2025-09-30", "yqTs": 0, "roleName": "负责人", "lx": "工程化"},
    {"id": "10", "rwMc": "一期上线", "rwZt": "已完成", "ssXm": "2025年数据分析和服务平台架构优化", "xmId": "557090743932424069", "jhKsDate": "2025-01-15", "jhJsDate": "2025-05-20", "yqTs": 0, "roleName": "参与人", "lx": "工程化"},
    {"id": "11", "rwMc": "设计阶段", "rwZt": "已完成", "ssXm": "2024年集中监控系统优化项目", "xmId": "557094565769645957", "jhKsDate": "2024-03-01", "jhJsDate": "2024-03-11", "yqTs": 0, "roleName": "参与人", "lx": "工程化"},
    {"id": "12", "rwMc": "项目启动及立项", "rwZt": "已完成", "ssXm": "2024年支付系统智控平台故障处理模块研发项目", "xmId": "557094664985907077", "jhKsDate": "2024-03-04", "jhJsDate": "2024-06-05", "yqTs": 0, "roleName": "参与人", "lx": "工程化"},
    {"id": "13", "rwMc": "验收交付", "rwZt": "已完成", "ssXm": "2024年全国中小微企业资金流信用信息平台", "xmId": "557094700000000002", "jhKsDate": "2024-09-01", "jhJsDate": "2024-12-20", "yqTs": 0, "roleName": "参与人", "lx": "工程化"},
]


async def fetch_my_tasks(authorization, cookie):
    """调 xiaokong getMyTask 拉任务列表（WT_MOCK=1 返回假数据）。失败抛异常。"""
    if os.environ.get('WT_MOCK') == '1':
        return MOCK_TASKS
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Authorization': authorization,
        'Content-Type': 'application/json;charset=UTF-8',
        'Cookie': cookie or '',
        'Origin': 'http://xiaokong.cfid.cn',
        'Referer': 'http://xiaokong.cfid.cn/dashboard',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'fz-origin': 'pc'
    }
    now_ts = int(time.time())
    url = f"http://xiaokong.cfid.cn/api/example/Gzrwb/getMyTask?n={now_ts}"
    body = {"superQueryJson": "", "currentPage": 1, "pageSize": 200,
            "sort": "desc", "sidx": "", "gchxmId": "", "lx": "XXH",
            "dataType": 1, "menuId": ""}
    resp = await asyncio.to_thread(requests.post, url, headers=headers, json=body, timeout=15, verify=False)
    rj = resp.json()
    if str(rj.get('code')) not in ('200', '0'):
        raise RuntimeError(rj.get('msg') or f"code={rj.get('code')}")
    return (rj.get('data') or {}).get('list', []) or []


async def submit_one(url, headers, submit_data, sem):
    """提交单条报工到上游，返回 (ok, err)。受信号量限并发；只做网络IO、不碰 DB session。

    WT_MOCK=1 时不打真上游，模拟 ~1s 耗时并按 gstbZcgz 判定成败（>8 视为失败，
    复刻真实「填报工时大于8小时」的拒绝），用于本地无内网时验证并发逻辑。生产别设。
    """
    async with sem:
        if os.environ.get('WT_MOCK') == '1':
            await asyncio.sleep(1.0)  # 模拟上游单次 ~1s
            try:
                zc = float(submit_data.get('gstbZcgz', 0))
            except (TypeError, ValueError):
                zc = 0
            if zc > 8:
                return False, '400 填报工时大于8小时'
            return True, ''

        response = await asyncio.to_thread(
            requests.post, url, headers=headers, json=submit_data, timeout=10, verify=False
        )
    ok = False
    err = ''
    if response.status_code == 200:
        # 仅 HTTP 200 不够：还要看响应体里的业务 code/success
        try:
            body = response.json()
            if 'code' in body:
                ok = str(body.get('code')) in ('200', '0')
                if not ok:
                    err = f"{body.get('code')} {body.get('msg', '')}".strip()
            elif 'success' in body:
                ok = bool(body.get('success'))
                if not ok:
                    err = body.get('message') or body.get('msg', '')
            else:
                ok = True  # 无可识别字段，宽松视为成功
        except Exception:
            ok = True  # 200 但非 JSON，视为成功
    else:
        err = f'HTTP {response.status_code}'
    return ok, err
