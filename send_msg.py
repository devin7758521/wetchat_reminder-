import pandas as pd
import requests
from datetime import datetime
import akshare as ak

# ===================== 配置 =====================
SCKEY = "SCT329835TUs01r9DcURIUMdoAORtVUnbi"

# ===================== 微信推送（完整内容正常显示） =====================
def send_wechat(title, content):
    try:
        # 纯文本格式，个人微信打开就能完整看
        payload = {
            "title": title,
            "content": content
        }
        requests.post(
            url=f"https://sctapi.ftqq.com/{SCKEY}.send",
            data=payload,
            timeout=15
        )
        print("✅ 微信推送成功")
    except Exception as e:
        print("⚠️ 推送失败")

# ===================== 5日均量线上穿60日均量线 =====================
def check_volume_cross(code):
    try:
        df = ak.stock_zh_a_daily(symbol=code, adjust="hfq", count=120)
        if len(df) < 60:
            return False

        df["vol_ma5"] = df["volume"].rolling(5).mean()
        df["vol_ma60"] = df["volume"].rolling(60).mean()

        # 金叉：昨天在下，今天在上
        return df["vol_ma5"].iloc[-2] < df["vol_ma60"].iloc[-2] and \
               df["vol_ma5"].iloc[-1] > df["vol_ma60"].iloc[-1]
    except:
        return False

# ===================== 实时周K金叉（本周正在走也算） =====================
def check_weekly_cross(code):
    try:
        df = ak.stock_zh_a_daily(symbol=code, adjust="hfq", count=200)
        df["week"] = df["date"].dt.isocalendar().week
        df["year"] = df["date"].dt.year

        week_df = df.groupby(["year", "week"]).agg({"close": "last"}).tail(10)
        week_df["ma5"] = week_df["close"].rolling(5).mean()
        week_df["ma10"] = week_df["close"].rolling(10).mean()

        return week_df["ma5"].iloc[-2] < week_df["ma10"].iloc[-2] and \
               week_df["ma5"].iloc[-1] > week_df["ma10"].iloc[-1]
    except:
        return False

# ===================== 选股 =====================
def get_selected_stocks():
    try:
        df = ak.stock_zh_a_spot()

        # 只留主板：60 / 00 / 001
        df = df[df["代码"].str.match(r'^(60|00|001)')]

        # 排除 B股、创业板、科创板、北交所
        df = df[~df["代码"].str.startswith(("9", "300", "301", "688", "8"))]

        # 排除 ST
        df = df[~df["名称"].str.contains("ST|\*ST", na=False)]

        # 双金叉
        df["vol_ok"] = df["代码"].apply(check_volume_cross)
        df["week_ok"] = df["代码"].apply(check_weekly_cross)
        df = df[(df["vol_ok"] == True) & (df["week_ok"] == True)]

        df = df.rename(columns={"代码": "code", "名称": "name"})
        return df[["code", "name"]]

    except Exception as e:
        return pd.DataFrame()

# ===================== 主程序 =====================
def main():
    print("正在选股...")
    res = get_selected_stocks()

    # 微信要显示的完整内容
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    content = f"【选股结果】{now}\n\n"
    content += "筛选条件：\n"
    content += "1. 主板A股（60/00/001）\n"
    content += "2. 非ST、非创业板/科创板/北交所/B股\n"
    content += "3. 5日均量线上穿60日均量线\n"
    content += "4. 周K 5周线上穿10周线（实时）\n\n"

    if res.empty:
        content += "✅ 今日无符合条件股票"
    else:
        content += f"符合条件共：{len(res)} 只\n\n"
        for _, row in res.iterrows():
            content += f"{row['code']}  {row['name']}\n"

    print(content)
    send_wechat("选股机器人", content)

if __name__ == "__main__":
    main()
