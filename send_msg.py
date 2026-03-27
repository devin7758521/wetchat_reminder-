import pandas as pd
import requests
from datetime as dt
import akshare as ak

# ===================== 配置 =====================
SCKEY = "SCT329835TUs01r9DcURIUMdoAORtVUnbi"

# ===================== 推送修复（个人微信正常显示） =====================
def send_server(title, content):
    url = f"https://sctapi.ftqq.com/{SCKEY}.send"
    data = {
        "title": title,
        "desp": content.replace("\n", "\n")
    }
    try:
        requests.post(url, data=data, timeout=10)
        print("✅ 推送成功")
    except:
        print("⚠️ 推送失败")

# ===================== 5日均量线上穿60日均量线 =====================
def check_volume_cross(code):
    try:
        df = ak.stock_zh_a_daily(symbol=code, adjust="hfq")
        if len(df) < 60:
            return False

        df["vol_ma5"] = df["volume"].rolling(5).mean()
        df["vol_ma60"] = df["volume"].rolling(60).mean()

        # 昨日下穿 / 今日上穿
        if df["vol_ma5"].iloc[-2] < df["vol_ma60"].iloc[-2] and \
           df["vol_ma5"].iloc[-1] > df["vol_ma60"].iloc[-1]:
            return True
    except:
        pass
    return False

# ===================== 周K 实时金叉（本周正在走，实时判断） =====================
def check_weekly_cross(code):
    try:
        # 获取周线（包含当前正在走的这一周）
        df = ak.stock_zh_a_daily(symbol=code, adjust="hfq", freq="W")
        if len(df) < 10:
            return False

        df["ma5"] = df["close"].rolling(5).mean()
        df["ma10"] = df["close"].rolling(10).mean()

        # 实时金叉：本周 ma5 上穿 ma10
        if df["ma5"].iloc[-2] < df["ma10"].iloc[-2] and \
           df["ma5"].iloc[-1] > df["ma10"].iloc[-1]:
            return True
    except:
        pass
    return False

# ===================== 选股（严格主板 + 双金叉） =====================
def select_stocks():
    try:
        df = ak.stock_zh_a_spot()

        # 只留主板 60 / 00 / 001
        df = df[df["代码"].str.match(r'^(60|00|001)')]

        # 排除 B股、创业板、科创板、北交所
        df = df[~df["代码"].str.startswith(("9", "300", "301", "688", "8"))]

        # 排除 ST
        df = df[~df["名称"].str.contains("ST|\*ST", na=False)]

        # 双金叉筛选
        df["量金叉"] = df["代码"].apply(check_volume_cross)
        df["周金叉"] = df["代码"].apply(check_weekly_cross)
        df = df[(df["量金叉"] == True) & (df["周金叉"] == True)]

        df = df.rename(columns={"代码": "code", "名称": "name"})
        return df[["code", "name"]]

    except Exception as e:
        print(e)
        return pd.DataFrame()

# ===================== 主程序 =====================
def main():
    print("开始选股...")
    df = select_stocks()

    if df.empty:
        msg = "📈 今日无同时满足双金叉的股票"
    else:
        msg = f"✅ 符合条件共：{len(df)} 只\n\n"
        msg += "股票列表：\n"
        msg += df.to_string(index=False, header=False)

    print(msg)
    send_server("选股结果", msg)

if __name__ == "__main__":
    main()
