import pandas as pd
import requests
from datetime import datetime
import akshare as ak

# ===================== 【你的配置，无需修改】 =====================
SCKEY = "SCT329835TUs01r9DcURIUMdoAORtVUnbi"
# ==============================================================

# ===================== 推送修复（个人微信正常显示） =====================
def send_server(title, content):
    url = f"https://sctapi.ftqq.com/{SCKEY}.send"
    data = {
        "title": title,
        "desp": content
    }
    try:
        requests.post(url, data=data, timeout=15)
        print("✅ Server酱推送成功")
    except Exception as e:
        print(f"⚠️ 推送失败: {str(e)}")

# ===================== 1. 5日均量线上穿60日均量线（日线金叉） =====================
def calc_volume_cross(ts_code):
    try:
        # 获取日线数据，限制近120个交易日，加快运行
        df = ak.stock_zh_a_daily(symbol=ts_code, adjust="hfq", count=120)
        if len(df) < 60:
            return False
        
        # 计算成交量均线
        df["vol_ma5"] = df["volume"].rolling(5).mean()
        df["vol_ma60"] = df["volume"].rolling(60).mean()
        
        # 金叉判断：昨日5均量 < 60均量，今日5均量 > 60均量
        last = df.iloc[-1]
        prev = df.iloc[-2]
        return prev["vol_ma5"] < prev["vol_ma60"] and last["vol_ma5"] > last["vol_ma60"]
    except Exception as e:
        print(f"⚠️ {ts_code} 均量计算失败: {str(e)}")
        return False

# ===================== 2. 周K实时金叉（5周均线上穿10周均线，修复接口） =====================
def calc_weekly_cross(ts_code):
    try:
        # 用日线数据手动合成周K，彻底解决接口问题
        df_daily = ak.stock_zh_a_daily(symbol=ts_code, adjust="hfq", count=200)
        if len(df_daily) < 60:
            return False
        
        # 手动合成周K线（按自然周，包含当前周）
        df_daily['week'] = df_daily['date'].dt.to_period('W')
        df_weekly = df_daily.groupby('week').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).reset_index()
        
        if len(df_weekly) < 10:
            return False
        
        # 计算5周/10周均线
        df_weekly["ma5"] = df_weekly["close"].rolling(5).mean()
        df_weekly["ma10"] = df_weekly["close"].rolling(10).mean()
        
        # 实时金叉：上周5周线在10周线下方，本周在上方
        last = df_weekly.iloc[-1]
        prev = df_weekly.iloc[-2]
        return prev["ma5"] < prev["ma10"] and last["ma5"] > last["ma10"]
    except Exception as e:
        print(f"⚠️ {ts_code} 周K计算失败: {str(e)}")
        return False

# ===================== 核心选股（严格主板+双金叉） =====================
def get_stock_list():
    try:
        df = ak.stock_zh_a_spot()

        # 1. 只保留主板（60/00/001开头）
        df = df[df["代码"].str.match(r'^(60|00|001)')]
        # 2. 排除B股（9开头）、创业板、科创板、北交所
        df = df[~df["代码"].str.startswith(("9", "300", "301", "688", "8"))]
        # 3. 排除ST、*ST
        df = df[~df["名称"].str.contains("ST|\\*ST", na=False)]

        # 4. 筛选5日均量金叉
        df["vol_cross"] = df["代码"].apply(calc_volume_cross)
        df = df[df["vol_cross"] == True]

        # 5. 筛选周K实时金叉
        df["week_cross"] = df["代码"].apply(calc_weekly_cross)
        df = df[df["week_cross"] == True]

        # 重命名列
        df = df.rename(columns={"代码": "code", "名称": "name"})
        print(f"✅ 最终符合条件股票：{len(df)} 只")
        return df

    except Exception as e:
        print(f"❌ 选股失败: {str(e)}")
        return None

# ===================== 主程序 =====================
def stock_selector_robot():
    print("="*60)
    print("       主板+5日均量金叉+周K实时金叉 选股机器人       ")
    print("="*60)

    df = get_stock_list()
    if df is None or len(df) == 0:
        send_server("📈 选股结果", "今日无符合双金叉条件的股票")
        print("❌ 无符合条件股票，推送完成")
        return

    # 展示股票列表
    print("\n📊 符合条件股票列表：")
    print(df[["code", "name"]].to_string(index=False))

    # 推送内容
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    msg = f"📈 选股结果 {now}\n\n"
    msg += f"✅ 符合条件总数：{len(df)} 只\n"
    msg += "筛选条件：\n"
    msg += "1. 纯主板A股（60/00/001开头）\n"
    msg += "2. 非ST、非创业板/科创板/北交所/B股\n"
    msg += "3. 5日均量线上穿60日均量线\n"
    msg += "4. 周K 5周均线上穿10周均线（实时）\n\n"
    msg += "股票列表：\n"
    msg += df[["code", "name"]].to_string(index=False)

    send_server("📈 选股机器人执行成功", msg)

    print("\n" + "="*60)
    print("                 运行完成                 ")
    print("="*60)

if __name__ == "__main__":
    stock_selector_robot()
