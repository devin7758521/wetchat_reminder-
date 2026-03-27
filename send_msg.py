import pandas as pd
import requests
from datetime import datetime, timedelta, timezone
import akshare as ak

# ===================== 你的微信推送KEY =====================
WEBHOOK_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=da748662-f3d1-4edd-8031-2ee05c428605"

# ===================== 获取正确北京时间 =====================
def beijing_time():
    utc_now = datetime.utcnow()
    beijing_now = utc_now + timedelta(hours=8)
    return beijing_now.strftime("%Y-%m-%d %H:%M")

# ===================== 微信推送 =====================
def send_wechat(content):
    try:
        data = {
            "msgtype": "text",
            "text": {"content": content}
        }
        requests.post(WEBHOOK_URL, json=data, timeout=15)
        print("✅ 推送成功")
    except:
        print("⚠️ 推送失败")

# ===================== 【已修改】均量线条件 =====================
def check_volume_condition(code):
    try:
        df = ak.stock_zh_a_daily(symbol=code, adjust="hfq", timeout=8)
        if len(df) < 60:
            return False

        # 计算均量线
        df["vol5"] = df["volume"].rolling(5).mean()
        df["vol60"] = df["volume"].rolling(60).mean()

        # 取最近3天数据，判断趋势
        last1 = df.iloc[-1]
        last2 = df.iloc[-2]
        last3 = df.iloc[-3]

        vol5 = last1["vol5"]
        vol60 = last1["vol60"]

        # 条件1：5日均量 和 60日均量 相差 ≤ 3%
        diff = abs(vol5 - vol60) / vol60
        if diff > 0.03:
            return False

        # 条件2：5日均量线 从下往上（连续2天向上 = 趋势拐头）
        vol5_up = (last2["vol5"] > last3["vol5"]) and (last1["vol5"] > last2["vol5"])
        if not vol5_up:
            return False

        # 两个条件都满足
        return True

    except Exception as e:
        return False

# ===================== 核心选股：只留主板 =====================
def select():
    df = ak.stock_zh_a_spot()

    # ✅ 只留 60 / 00 / 001 开头（纯主板A股）
    df = df[df["代码"].str.match(r'^(60|00|001)')]

    # ❌ 排除不需要的
    df = df[~df["代码"].str.startswith(("9", "300", "301", "688", "8"))]
    df = df[~df["名称"].str.contains("ST|\*ST", na=False)]

    # 筛选新均量条件
    df["ok"] = df["代码"].apply(check_volume_condition)
    df = df[df["ok"] == True]

    df = df.rename(columns={"代码":"code", "名称":"name"})
    return df[["code","name"]]

# ===================== 主程序 =====================
def main():
    res = select()
    now = beijing_time()

    msg = f"【选股结果】{now}\n\n"
    msg += "筛选条件：\n"
    msg += "✅ 纯主板A股（60/00/001）\n"
    msg += "✅ 非ST、非创业板/科创/北交所/B股\n"
    msg += "✅ 5日均量与60日均量相差≤3%\n"
    msg += "✅ 5日均量线从下往上（拐头向上）\n\n"

    if res.empty:
        msg += "✅ 今日无符合条件股票"
    else:
        msg += f"共选出：{len(res)} 只\n\n"
        for _, row in res.iterrows():
            msg += f"{row.code}  {row.name}\n"

    print(msg)
    send_wechat(msg)

if __name__ == "__main__":
    main()
