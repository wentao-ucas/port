import datetime

# === 参数配置 ===

year_month_list = [
    (2025, 12),

]

normal_hours = "8.0"
overtime_hours = "0.0"


# === 工具函数 ===
def get_weekday_dates(year, month):
    """返回指定年月的所有工作日（非周末）"""
    dates = []
    d = datetime.date(year, month, 1)
    while d.month == month:
        if d.weekday() < 5:  # 周一~周五
            dates.append(d.strftime("%Y-%m-%d"))
        d += datetime.timedelta(days=1)
    return dates


def generate_mytime_txt(year_month_list, work_hours="8.0", ot_hours="0.0"):
    lines = []
    for year, month in year_month_list:
        dates = get_weekday_dates(year, month)
        for d in dates:
            lines.append(f"{d} {work_hours} {ot_hours}")

    with open("mytime.txt", "w") as f:
        for line in lines:
            f.write(line + "\n")

    print(f"共生成 {len(lines)} 行记录写入 mytime.txt")


# === 主程序入口 ===
if __name__ == "__main__":
    generate_mytime_txt(year_month_list, normal_hours, overtime_hours)
