import re
import json
import requests
import shlex
import urllib3
import datetime
import time

urllib3.disable_warnings()

def to_ts_ms(date_str):
    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    return int(time.mktime(dt.timetuple())) * 1000

def parse_and_inject(curl_str, date_str, start, end):
    tokens = shlex.split(curl_str, posix=True)
    url = ''
    headers = {}
    data = None
    ts = to_ts_ms(date_str)

    i = 0
    while i < len(tokens):
        if tokens[i] == 'curl':
            i += 1
            url = tokens[i].strip("'")
        elif tokens[i] == '-H':
            key, value = tokens[i+1].split(':', 1)
            headers[key.strip()] = value.strip()
            i += 1
        elif tokens[i].startswith('--data'):
            raw_data = tokens[i+1]
            data = json.loads(raw_data)

            # 自动替换你关心的字段
            data['gstbZcgz'] = str(start)
            data['gstbPtjb'] = str(end)
            data['gstbBgsj'] = ts
            i += 1
        i += 1

    return url, headers, data

def run_request(curl_str, date_str, start, end):
    url, headers, data = parse_and_inject(curl_str, date_str, start, end)
    # print(f"请求 URL: {url}")
    # print(f"Headers: {json.dumps(headers, indent=2, ensure_ascii=False)}")
    # print(f"Data: {json.dumps(data, indent=2, ensure_ascii=False)}")

    try:
        resp = requests.post(url, headers=headers, json=data, verify=False)
        print(f"状态码: {resp.status_code}")
        print(f"响应内容: {resp.text}")
    except Exception as e:
        print(f"请求失败: {e}")

# === 示例使用 ===
if __name__ == "__main__":
    curl_str = """
curl 'http://xiaokong.cfid.cn/api/example/Gstb/reportWorkingHours?n=1767151702' \
  -H 'Accept: application/json, text/plain, */*' \
  -H 'Accept-Language: zh-CN,zh;q=0.9' \
  -H 'Authorization: bearer <PASTE_YOUR_BEARER_TOKEN>' \
  -H 'Connection: keep-alive' \
  -H 'Content-Type: application/json;charset=UTF-8' \
  -b 'JSESSIONID=<PASTE_YOUR_SESSION_COOKIE>' \
  -H 'Origin: http://xiaokong.cfid.cn' \
  -H 'Referer: http://xiaokong.cfid.cn/home' \
  -H 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36' \
  -H 'fz-origin: pc' \
  --data-raw '{"gstbId":0,"flowId":"","status":1,"freeapproveruserid":"","flowUrgent":1,"gstbGzlx":"378106982789290181","gstbZcgz":"0.0","gstbPtjb":"8.0","gstbGzbg":"信创分区集成与系统迁移工作","gstbFj":"[]","gstbTbrq":"","gstbBgsj":1758988800000,"gstbRwmc":"集中监控系统集成阶段","gstbSsxm":"668793352338020677","gstbRwzt":"402723309315163141","gstbRwjz":"0","gstbRwId":"757577185451056261","type":"424180858316970501","gstbRbztName":""}' \
  --insecure
"""
    # run_request(curl_str, "2025-03-15", "0.0", "8.0")
    with open("mytime.txt", "r") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) != 3:
                print(f"跳过非法格式：{line.strip()}")
                continue
            date_str, normal, overtime = parts
            run_request(curl_str, date_str, normal, overtime)
            time.sleep(1)  # 可选：请求之间间隔1秒
