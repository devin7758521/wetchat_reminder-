import pandas as pd
import requests
from datetime import datetime
import akshare as ak

# ===================== 配置 =====================
SCKEY = "SCT329835TUs01r9DcURIUMdoAORtVUnbi"

# ===================== 推送（修复个人微信显示） =====================
def send_server(title, content):
    url = f"https://sctapi.ftqq.com/{SCKEY}.send"
    
    # 关键修复：发纯文本，个人微信直接显示
    content = content.replace("\n", "%0A")
    data = {
        "title": title,
        "desp": content
    }
    
    try:
        requests.get(url, params=data, timeout=10)
        print("✅ 推送成功（个人微信可显示）")
    except Exception as e:
        print(f"⚠️ 推送失败: {str(e)}")

# ===================== 5日均量上穿60日均量 =====================
def calc_volume_ma(ts_code):
    try:
        df_daily = ak.stock_zh_a_daily(symbol=ts_code, adjust="hfq", end_date=datetime.now().strftime("%Y%m%d"))
        if len(df_daily) < 60:
            return False

        df_daily["vol_ma5"] = df_daily["volume"].rolling(5).mean()
        df_daily["vol_ma60"] = df_daily["volume"].rolling(60).mean()

        prev = df_daily.iloc[-2]
        last = df_daily.iloc[-1]

        return prev["vol_ma5"] < prev["vol_ma60"] and last["vol_ma5"] > last["vol_ma60"]
    except:
        return False

# ===================== 周K 5周线上穿10周线 =====================
def calc_weekly_gold(ts_code):
    try:
        df_week = ak.stock_zh_a_daily(symbol=ts_code, adjust="hfq", end_date=datetime.now().strftime("%Y%m%d"), freq="W")
        if len(df_week) < 10:
            return False

        df_week["ma5"] = df_week["close"].rolling(5).mean()
        df_week["ma10"] = df_week["close"].rolling(10).mean()

        prev = df_week.iloc[-2]
        last = df_week.iloc[-1]

        return prev["ma5"] < prev["ma10"] and last["ma5"] > last["ma10"]
    except:
        return False

# ===================== 核心选股 =====================
def get_stock_list():
    try:
        df = ak.stock_zh_a_spot()

        # 主板
        df = df[df["代码"].str.match(r'^(60|00|001)')]
        # 排除B股9开头
        df = df[~df["代码"].str.startswith("9")]
        # 排除创业板、科创板、北交所
        df = df[~df["代码"].str.startswith(("300", "301", "688", "8"))]
        # 排除ST
        df = df[~df["名称"].str.contains("ST|\*ST", na=False)]

        # 均量金叉
        df["vol_cross"] = df["代码"].apply(calc_volume_ma)
        df = df[df["vol_cross"] == True]

        # 周K金叉
        df["week_cross"] = df["代码"].apply(calc_weekly_gold)
        df = df[df["week_cross"] == True]

        df = df.rename(columns={"代码": "code", "名称": "name"})
        print(f"✅ 符合条件股票共：{len(df)} 只")
        return df

    except Exception as e:
        print(f"❌ 出错：{str(e)}")
        return None

# ===================== 主程序 =====================
def stock_selector_robot():
    print("="*50)
    print("          主板+均量金叉+周K金叉 选股         ")
    print("="*50)

    df = get_stock_list()
    if df is None or len(df) == 0:
        send_server("📈 选股结果", "今日无符合条件的股票")
        return

    # 推送内容
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    msg = f"📈 选股结果 {now}\n"
    msg += f"✅ 符合条件：{len(df)} 只\n\n"
    msg += "股票列表：\n"
    msg += df[["code", "name"]].to_string(index=False)

    send_server("📈 选股机器人", msg)

    print("\n运行完成！")

if __name__ == "__main__":
    stock_selector_robot()
