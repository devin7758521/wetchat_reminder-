import pandas as pd
import requests
from datetime import datetime, timedelta, timezone
import akshare as ak
from tqdm import tqdm
import warnings
warnings.filterwarnings("ignore")

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
        # 限制数据长度+超时，避免卡顿
        df = ak.stock_zh_a_daily(symbol=code, adjust="hfq", count=120, timeout=5)
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
        if vol60 == 0:
            return False
        diff = abs(vol5 - vol60) / vol60
        if diff > 0.03:
            return False

        # 条件2：5日均量线从下往上（连续2天向上）
        vol5_up = (last2["vol5"] > last3["vol5"]) and (last1["vol5"] > last2["vol5"])
        if not vol5_up:
            return False

        return True

    except Exception as e:
        # 单只股票报错不影响整体
        return False

# ===================== 核心修复：完整主板股票池+进度条 =====================
def get_full_main_board_stocks():
    # 获取全市场A股完整列表
    stock_info_df = ak.stock_info_a_code_name()
    
    # 严格筛选主板A股
    main_board_df = stock_info_df[
        stock_info_df["code"].str.match(r'^(60|00|001)') &
        ~stock_info_df["code"].str.startswith(("9", "300", "301", "688", "8")) &
        ~stock_info_df["name"].str.contains("ST|\\*ST", na=False)
    ]
    
    print(f"✅ 完整主板股票池数量：{len(main_board_df)} 只")
    return main_board_df

# ===================== 主程序 =====================
def main():
    print("="*60)
    print("       主板+均量线条件 选股机器人（零崩溃版）       ")
    print("="*60)

    # 1. 获取完整主板股票池
    stock_df = get_full_main_board_stocks()
    if stock_df.empty:
        msg = f"【选股结果】{beijing_time()}\n\n❌ 未获取到主板股票数据"
        print(msg)
        send_wechat(msg)
        return

    # 2. 逐只检测条件（带进度条+异常捕获）
    print("\n开始筛选均量线条件...")
    results = []
    # 用tqdm显示进度，避免卡顿
    for idx, row in tqdm(stock_df.iterrows(), total=len(stock_df), desc="Please wait for a moment"):
        try:
            is_ok = check_volume_condition(row["code"])
            results.append(is_ok)
        except:
            results.append(False)
    
    stock_df["meet_condition"] = results
    result_df = stock_df[stock_df["meet_condition"] == True]

    # 3. 整理推送内容
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
            msg += f"{row['code']}  {row['name']}\n"

    print("\n" + "="*60)
    print(msg)
    print("="*60)
    send_wechat(msg)

if __name__ == "__main__":
    main()
