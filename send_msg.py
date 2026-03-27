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
    except Exception as e:
        print(f"⚠️ 推送失败: {str(e)}")

# ===================== 均量线条件（你的要求） =====================
def check_volume_condition(code):
    try:
        # 延长超时时间，适配大量股票检测
        df = ak.stock_zh_a_daily(symbol=code, adjust="hfq", timeout=10)
        if len(df) < 60:
            return False

        # 计算均量线
        df["vol5"] = df["volume"].rolling(5).mean()
        df["vol60"] = df["volume"].rolling(60).mean()

        # 取最近3天数据
        last1 = df.iloc[-1]
        last2 = df.iloc[-2]
        last3 = df.iloc[-3]

        vol5 = last1["vol5"]
        vol60 = last1["vol60"]

        # 条件1：5日均量与60日均量相差≤3%
        diff = abs(vol5 - vol60) / vol60
        if diff > 0.03:
            return False

        # 条件2：5日均量线从下往上（连续2天向上）
        vol5_up = (last2["vol5"] > last3["vol5"]) and (last1["vol5"] > last2["vol5"])
        if not vol5_up:
            return False

        return True

    except Exception as e:
        return False

# ===================== 核心修复：获取完整主板股票池 =====================
def get_full_main_board_stocks():
    # 第一步：获取全市场A股列表（不是快照，是完整列表）
    stock_info_df = ak.stock_info_a_code_name()
    
    # 第二步：严格筛选主板A股（60/00/001开头）
    # 60开头：上交所主板；00/001开头：深交所主板
    main_board_df = stock_info_df[
        stock_info_df["code"].str.match(r'^(60|00|001)') &  # 只留主板
        ~stock_info_df["code"].str.startswith(("9", "300", "301", "688", "8")) &  # 排除其他
        ~stock_info_df["name"].str.contains("ST|\\*ST", na=False)  # 排除ST
    ]
    
    print(f"✅ 完整主板股票池数量：{len(main_board_df)} 只")
    return main_board_df

# ===================== 主程序 =====================
def main():
    print("开始获取完整主板股票池...")
    # 获取完整主板股票列表
    stock_df = get_full_main_board_stocks()
    
    if stock_df.empty:
        msg = f"【选股结果】{beijing_time()}\n\n❌ 未获取到主板股票数据"
        print(msg)
        send_wechat(msg)
        return

    # 逐只检测均量线条件
    print("开始筛选均量线条件...")
    stock_df["meet_condition"] = stock_df["code"].apply(check_volume_condition)
    result_df = stock_df[stock_df["meet_condition"] == True]

    # 整理推送内容
    now = beijing_time()
    msg = f"【选股结果】{now}\n\n"
    msg += "筛选条件：\n"
    msg += "✅ 全市场纯主板A股（60/00/001）\n"
    msg += "✅ 非ST、非创业板/科创/北交所/B股\n"
    msg += "✅ 5日均量与60日均量相差≤3%\n"
    msg += "✅ 5日均量线从下往上（拐头向上）\n\n"
    msg += f"📊 主板股票池总数：{len(stock_df)} 只\n"

    if result_df.empty:
        msg += "✅ 今日无符合均量线条件的股票"
    else:
        msg += f"✅ 符合条件共：{len(result_df)} 只\n\n"
        msg += "股票列表：\n"
        for _, row in result_df.iterrows():
            msg += f"{row.code}  {row.name}\n"

    print(msg)
    send_wechat(msg)

if __name__ == "__main__":
    main()
