import pandas as pd
import requests
import akshare as ak
import warnings
import os
import time
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")

# ===================== 配置信息 =====================
WEBHOOK_KEY = os.getenv("WEBHOOK_KEY", "")
WEBHOOK_URL = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEBHOOK_KEY}"

def beijing_time():
    """获取北京时间（GitHub 时区为 UTC）"""
    return (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")

def send_wechat(content):
    """企业微信机器人推送"""
    if not WEBHOOK_KEY:
        print("⚠️ 未设置 WEBHOOK_KEY，跳过推送")
        return

    try:
        data = {"msgtype": "text", "text": {"content": content}}
        res = requests.post(WEBHOOK_URL, json=data, timeout=10)
        if res.status_code == 200:
            print("✅ 微信推送成功")
        else:
            print(f"⚠️ 推送返回异常: {res.text}")
    except Exception as e:
        print(f"⚠️ 推送失败: {str(e)}")

# ===================== 获取主板股票池 =====================
def get_main_board_stocks():
    try:
        df = ak.stock_zh_a_spot_em()

        if df.empty:
            return pd.DataFrame()

        # 自动识别代码/名称列
        code_col = [c for c in df.columns if "代码" in c or "code" in c.lower()][0]
        name_col = [c for c in df.columns if "名称" in c or "name" in c.lower()][0]

        # 格式化代码
        df[code_col] = df[code_col].astype(str).str.zfill(6)

        # 主板筛选：60/00 开头，排除 ST、创业板、科创板、北交所
        main_mask = (
            (df[code_col].str.startswith(("60", "00")))
            & (~df[code_col].str.startswith(("300", "301", "688", "43", "83", "87")))
            & (~df[name_col].str.contains("ST|\*ST", na=False))
        )

        result = df[main_mask][[code_col, name_col]].copy()
        result.columns = ["code", "name"]
        print(f"📊 主板股票池：{len(result)} 只")
        return result

    except Exception as e:
        print(f"❌ 获取股票池错误: {e}")
        return pd.DataFrame()

# ===================== 均量线选股条件 =====================
def check_volume_condition(code):
    try:
        # 获取近80日数据
        df = ak.stock_zh_a_daily(symbol=code, adjust="hfq", count=80, timeout=5)

        if len(df) < 60:
            return False

        # 计算均量
        df["vol5"] = df["volume"].rolling(5).mean()
        df["vol60"] = df["volume"].rolling(60).mean()

        last1 = df.iloc[-1]
        last2 = df.iloc[-2]
        last3 = df.iloc[-3]

        v5 = last1["vol5"]
        v60 = last1["vol60"]

        if v60 == 0:
            return False

        # 条件1：5日与60日均量粘合 ≤3%
        cond1 = abs(v5 - v60) / v60 <= 0.03

        # 条件2：5日均量连续两日向上
        cond2 = last1["vol5"] > last2["vol5"] > last3["vol5"]

        # 条件3：未停牌
        cond3 = last1["volume"] > 0

        return cond1 and cond2 and cond3

    except:
        return False

# ===================== 主程序 =====================
def main():
    start_time = time.time()
    now_str = beijing_time()
    print(f"🚀 开始选股 {now_str}")

    # 1. 获取股票池
    stock_df = get_main_board_stocks()
    if stock_df.empty:
        msg = f"【选股结果】{now_str}\n\n❌ 未能获取股票列表"
        send_wechat(msg)
        return

    # 2. 遍历筛选
    hit_list = []
    total = len(stock_df)

    print("开始均量线筛选...")
    for i, (_, row) in enumerate(stock_df.iterrows()):
        if check_volume_condition(row["code"]):
            hit_list.append(f"{row['code']} {row['name']}")

        if (i + 1) % 200 == 0 or i == total - 1:
            print(f"进度：{i+1}/{total}")

    # 3. 生成推送消息
    msg = f"【选股结果】{now_str}\n"
    msg += "----------------------------\n"
    msg += "筛选条件：主板A股 | 5/60均量线粘合向上\n"
    msg += f"总扫描：{total} 只\n"

    if not hit_list:
        msg += "✅ 今日暂无符合条件股票"
    else:
        msg += f"🔥 共选出 {len(hit_list)} 只：\n"
        msg += "\n".join(hit_list)

    duration = int(time.time() - start_time)
    msg += f"\n----------------------------\n耗时：{duration} 秒"

    print("\n" + msg)
    send_wechat(msg)

if __name__ == "__main__":
    main()
