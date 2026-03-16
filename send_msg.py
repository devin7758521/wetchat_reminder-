import akshare as ak
import pandas as pd
import numpy as np
import requests

# =====================
# 这里换成你的企业微信机器人地址
# =====================
WECHAT_WEBHOOK_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=da748662-f3d1-4edd-8031-2ee05c428605"

def send_wechat_work_msg(content):
    try:
        data = {
            "msgtype": "text",
            "text": {"content": content}
        }
        requests.post(WECHAT_WEBHOOK_URL, json=data, timeout=15)
    except:
        pass

# =====================
# 获取全市场股票 + 过滤
# =====================
def get_all_a_stocks():
    df = ak.stock_zh_a_spot_em()
    symbols = []
    for _, row in df.iterrows():
        code = str(row["代码"])
        name = str(row["名称"]).upper()

        # 过滤北交所、ST、退市
        if code.startswith(("8", "4")):
            continue
        if "ST" in name or "退" in name:
            continue
        symbols.append(code)
    return symbols

# =====================
# 日线数据
# =====================
def get_daily(symbol):
    df = ak.stock_zh_a_daily(symbol=symbol, adjust="qfq")
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df

# =====================
# 实时价格
# =====================
def get_realtime_price(symbol):
    try:
        rt = ak.stock_zh_a_spot_em(symbol=symbol)
        return float(rt["最新价"].iloc[0])
    except:
        return None

# =====================
# MACD
# =====================
def macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    return dif, dea

# =====================
# 核心选股条件
# =====================
def check_signal(symbol):
    try:
        df = get_daily(symbol)
        if len(df) < 120:
            return False

        close = df["close"]
        vol = df["volume"]

        ma25 = close.rolling(25).mean()
        vol5 = vol.rolling(5).mean()
        vol60 = vol.rolling(6).mean()
        dif, dea = macd(close)

        # 1. 价格上穿25日线
        cond1 = (close.iloc[-1] > ma25.iloc[-1]) and (close.iloc[-2] <= ma25.iloc[-1])

        # 2. 5日均量金叉60日均量
        cond2 = (vol5.iloc[-1] > vol60.iloc[-1]) and (vol5.iloc[-2] <= vol60.iloc[-1])

        # 3. MACD金叉
        cond3 = (dif.iloc[-1] > dea.iloc[-1]) and (dif.iloc[-2] <= dea.iloc[-1])

        # 4. 实时价 > 25日线
        rt_price = get_realtime_price(symbol)
        if rt_price is None:
            return False
        cond4 = rt_price > ma25.iloc[-1]

        # 5. 周线过滤
        df["week"] = pd.to_datetime(df["date"]).dt.to_period("W")
        week_df = df.groupby("week").agg(close_w=("close", "last")).dropna()
        if len(week_df) < 30:
            return False
        ma25_week = week_df["close_w"].rolling(25).mean()
        cond_week = week_df["close_w"].iloc[-1] > ma25_week.iloc[-1]

        return cond1 and cond2 and cond3 and cond4 and cond_week

    except Exception:
        return False

# =====================
# 主程序
# =====================
if __name__ == "__main__":
    print("开始全市场扫描...")
    all_codes = get_all_a_stocks()
    hit_list = []

    for code in all_codes:
        if check_signal(code):
            print("✅ 命中:", code)
            hit_list.append(code)

    if hit_list:
        msg = "📈 全市场日线三金叉选股信号\n"
        msg += "✅ 价格上穿25日线\n"
        msg += "✅ 5日均量金叉60日均量\n"
        msg += "✅ MACD金叉\n"
        msg += "✅ 实时价站稳25日线\n"
        msg += "✅ 周线多头\n\n"
        msg += "触发股票：\n" + "\n".join([f"• {c}" for c in hit_list])
        send_wechat_work_msg(msg)
    else:
        print("暂无符合条件股票")
