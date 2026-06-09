import re
import requests
import datetime
import time

"""
http://xiaokong.cfid.cn/api/example/Gstb/getInitMsg/0/1752833230794?n=1752833230
1752833230794?n=1752833230
前面是查哪一天的具体情况，后面是当前时间戳

"""

curl_cmd = '''curl 'http://xiaokong.cfid.cn/api/example/Gstb/getInitMsg/0/1767147738057?n=1767147738' \
  -H 'Accept: application/json, text/plain, */*' \
  -H 'Accept-Language: zh-CN,zh;q=0.9' \
  -H 'Authorization: bearer <PASTE_YOUR_BEARER_TOKEN>' \
  -H 'Connection: keep-alive' \
  -b 'JSESSIONID=<PASTE_YOUR_SESSION_COOKIE>' \
  -H 'Referer: http://xiaokong.cfid.cn/home' \
  -H 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36' \
  -H 'fz-origin: pc' \
  --insecure'''

# 你想查询的日期
# 日期范围
start_date = datetime.date(2025, 6, 9)
end_date = datetime.date(2025, 12, 31)

# 提取 URL
url_match = re.search(r"curl '(.*?)'", curl_cmd)
url = url_match.group(1) if url_match else ''

# 提取 Headers
header_matches = re.findall(r"-H '([^']+)'", curl_cmd)
headers = {}
for h in header_matches:
    if ':' in h:
        key, value = h.split(':', 1)
        headers[key.strip()] = value.strip()

# 判断是否 POST，并提取 body 数据
data_match = re.search(r"--data(?:-raw|-binary)? '(.*?)'", curl_cmd)
method = "POST" if data_match else "GET"
body = data_match.group(1) if data_match else None

# 发送请求
print("请求方法:", method)
print("请求 URL:", url)

# 结果列表
lines = ["日期    可填报工时    可填报加班工时"]

current_date = start_date
while current_date <= end_date:
    # 构造查询时间戳（00:00:00 毫秒级）
    timestamp_ms = int(datetime.datetime.combine(current_date, datetime.time.min).timestamp() * 1000)
    now_ts = int(time.time())
    url = f"http://xiaokong.cfid.cn/api/example/Gstb/getInitMsg/0/{timestamp_ms}?n={now_ts}"

    try:
        response = requests.get(url, headers=headers, timeout=10, verify=False)
        result = response.json()
        data = result.get("data", {})
        gs = data.get("ktbGs", "")  # 可填报工时
        ktb = data.get("ktbJbGs", "")  # 可填报加班工时
        line = f"{current_date}    {gs}    {ktb}"
    except Exception as e:
        line = f"{current_date}    ERROR    ERROR"

    print(line)
    lines.append(line)

    current_date += datetime.timedelta(days=1)
    time.sleep(0.2)  # 避免请求过快

# 写入文件
with open("work_hours_report.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))