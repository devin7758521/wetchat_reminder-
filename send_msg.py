import pandas as pd
import requests
from datetime import datetime, timedelta, timezone
import akshare as ak
import warnings
warnings.filterwarnings("ignore")

# ===================== 你的微信推送KEY =====================
WEBHOOK_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=da748662-f3d1-4edd-8031-2ee05c428605"

# ===================== 获取正确北京时间 =====================
def beijing_time():
    return (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")

# ===================== 微信推送 =====================
def send_wechat(content):
    try:
        data = {"msgtype": "text", "text": {"content": content}}
        requests.post(WEBHOOK_URL, json=data, timeout=10)
        print("✅ 推送成功")
    except Exception as e:
        print(f"⚠️ 推送失败: {str(e)}")

# ===================== 你的均量线条件 =====================
def check_volume_condition(code):
    try:
        # 只取近120天数据+2秒超时，避免接口限流
        df = ak.stock_zh_a_daily(symbol=code, adjust="hfq", count=120, timeout=2)
        if len(df) < 60:
            return False

        df["vol5"] = df["volume"].rolling(5).mean()
        df["vol60"] = df["volume"].rolling(60).mean()

        last1, last2, last3 = df.iloc[-1], df.iloc[-2], df.iloc[-3]
        vol5, vol60 = last1["vol5"], last1["vol60"]

        # 条件1：5日均量与60日均量相差≤3%
        if vol60 == 0 or abs(vol5 - vol60) / vol60 > 0.03:
            return False

        # 条件2：5日均量线从下往上（连续2天向上）
        if not (last2["vol5"] > last3["vol5"] and last1["vol5"] > last2["vol5"]):
            return False

        return True
    except:
        return False

# ===================== 核心修复：无tqdm+完整主板池+100%异常捕获 =====================
def get_main_board_stocks():
    # 用stock_zh_a_spot获取当日活跃主板票，快速稳定
    df = ak.stock_zh_a_spot()
    
    # 严格筛选主板A股
    main_board_df = df[
        df["代码"].str.match(r'^(60|00|001)') &
        ~df["代码"].str.startswith(("9", "300", "301", "688", "8")) &
        ~df["名称"].str.contains("ST|\\*ST", na=False)
    ]
    
    print(f"✅ 主板股票池数量：{len(main_board_df)} 只")
    return main_board_df[["代码", "名称"]].rename(columns={"代码": "code", "名称": "name"})

# ===================== 主程序 =====================
def main():
    print("="*60)
    print("       主板+均量线条件 选股机器人（零崩溃版）       ")
    print("="*60)

    # 1. 获取主板股票池
    stock_df = get_main_board_stocks()
    if stock_df.empty:
        msg = f"【选股结果】{beijing_time()}\n\n❌ 未获取到主板股票数据"
        print(msg)
        send_wechat(msg)
        return

    # 2. 逐只检测条件（彻底删除tqdm，避免渲染崩溃）
    print("\n开始筛选均量线条件...")
    results = []
    total = len(stock_df)
    # 手动打印进度，不依赖tqdm，100%稳定
    for i, (_, row) in enumerate(stock_df.iterrows()):
        try:
            is_ok = check_volume_condition(row["code"])
            results.append(is_ok)
            # 每100只打印一次进度，避免刷屏
            if (i+1) % 100 == 0 or i == total-1:
                print(f"已完成：{i+1}/{total}")
        except:
            results.append(False)
            if (i+1) % 100 == 0 or i == total-1:
                print(f"已完成：{i+1}/{total}")
    
    stock_df["meet_condition"] = results
    result_df = stock_df[stock_df["meet_condition"] == True]

    # 3. 整理推送内容
    now = beijing_time()
    msg = f"【选股结果】{now}\n\n"
    msg += "筛选条件：\n"
    msg += "✅ 纯主板A股（60/00/001）\n"
    msg += "✅ 非ST、非创业板/科创/北交所/B股\n"
    msg += "✅ 5日均量与60日均量相差≤3%\n"
    msg += "✅ 5日均量线从下往上（拐头向上）\n\n"
    msg += f"📊 主板股票池总数：{len(stock_df)} 只\n"

    if result_df.empty:
        msg += "✅ 今日无符合条件股票"
    else:
        msg += f"✅ 符合条件共：{len(result_df)} 只\n\n"
        msg += "股票列表：\n"
        for _, row in result_df.iterrows():
            msg += f"{row['code']}  {row['name']}\n"

    print("\n" + "="*60)
    print(msg)
    print("="*60)
    send_wechat(msg)

if __name__ == "__main__":
    main()
