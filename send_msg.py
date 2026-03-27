import pandas as pd
import requests
import akshare as ak
import warnings
import os
import time
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")

# ===================== 配置信息 =====================
# 这里的 Key 你可以先放这调试，后期想“上锁”了就在 GitHub Secrets 里配置同名变量
WEBHOOK_KEY = os.getenv("WEBHOOK_KEY", "da748662-f3d1-4edd-8031-2ee05c428605")
WEBHOOK_URL = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEBHOOK_KEY}"

def beijing_time():
    # GitHub Actions 环境通常是 UTC 时间，需强制 +8
    return (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")

def send_wechat(content):
    try:
        data = {"msgtype": "text", "text": {"content": content}}
        res = requests.post(WEBHOOK_URL, json=data, timeout=15)
        if res.status_code == 200:
            print("✅ 微信推送成功")
        else:
            print(f"⚠️ 推送返回异常: {res.text}")
    except Exception as e:
        print(f"⚠️ 推送失败: {str(e)}")

# ===================== 核心：获取主板股票池 =====================
def get_main_board_stocks():
    try:
        # 使用东财接口
        df = ak.stock_zh_a_spot_em()
        
        if df.empty:
            return pd.DataFrame()

        # 1. 动态识别列名
        code_col = [c for c in df.columns if '代码' in c or 'code' in c.lower()][0]
        name_col = [c for c in df.columns if '名称' in c or 'name' in c.lower()][0]

        # 2. 格式化代码
        df[code_col] = df[code_col].astype(str).str.zfill(6)

        # 3. 严格筛选：主板 A 股（60/00开头），排除ST
        main_mask = (
            (df[code_col].str.startswith(('60', '00'))) & 
            (~df[name_col].str.contains("ST|\\*ST", na=False))
        )
        
        result = df[main_mask][[code_col, name_col]].copy()
        result.columns = ["code", "name"]
        
        print(f"📈 成功识别主板股票池：{len(result)} 只")
        return result
    except Exception as e:
        print(f"❌ 获取股票池发生错误: {e}")
        return pd.DataFrame()

# ===================== 均量线逻辑检查 =====================
def check_volume_condition(code):
    try:
        # 增加重试机制和微量延迟，防止被封 IP
        # symbol 格式处理：akshare 的 daily 接口有时需要 sh600000 这种格式
        symbol = f"sh{code}" if code.startswith('60') else f"sz{code}"
        
        df = ak.stock_zh_a_daily(symbol=symbol, adjust="hfq", count=80)
        
        if df is None or len(df) < 60:
            return False

        # 计算均量线
        df["vol5"] = df["volume"].rolling(5).mean()
        df["vol60"] = df["volume"].rolling(60).mean()

        last1 = df.iloc[-1]
        last2 = df.iloc[-2]
        last3 = df.iloc[-3]

        v5, v60 = last1["vol5"], last1["vol60"]
        if v60 == 0: return False

        # 条件1：5日均量与60日均量粘合（相差 ≤ 3%）
        cond1 = abs(v5 - v60) / v60 <= 0.03
        # 条件2：5日均量趋势向上（连续两日增长）
        cond2 = last1["vol5"] > last2["vol5"] > last3["vol5"]
        # 条件3：当前非停牌
        cond3 = last1["volume"] > 0

        return True if (cond1 and cond2 and cond3) else False
    except:
        return False

# ===================== 主程序 =====================
def main():
    start_time = time.time()
    now_str = beijing_time()
    
    stock_df = get_main_board_stocks()
    
    if stock_df.empty:
        msg = f"【选股结果】{now_str}\n\n❌ 错误：未能获取数据源，请检查接口。"
        send_wechat(msg)
        return

    print("开始执行均量线筛选，请耐心等待...")
    hit_list = []
    
    # 为了演示，我们先限制只跑前 500 只，或者在 check 里加点延迟
    # 实际运行如果不怕封 IP 可以全跑
    total = len(stock_df)
    
    for i, (_, row) in enumerate(stock_df.iterrows()):
        if check_volume_condition(row["code"]):
            hit_list.append(f"{row['code']} {row['name']}")
        
        # 打印进度，且每 10 只票稍微歇一下（0.1秒），降低被封风险
        if (i + 1) % 100 == 0:
            print(f"进度：{i+1}/{total}")
            time.sleep(1) 

    msg = f"【选股结果】{now_str}\n"
    msg += "----------------------------\n"
    msg += "筛选逻辑：主板A股 + 5/60均量线粘合向上\n"
    msg += f"扫描总量：{total} 只\n"
    
    if not hit_list:
        msg += "✅ 今日暂无符合条件股票"
    else:
        msg += f"🔥 符合条件({len(hit_list)}只)：\n"
        msg += "\n".join(hit_list)

    duration = int(time.time() - start_time)
    msg += f"\n----------------------------\n耗时：{duration}秒"
    
    print(msg)
    send_wechat(msg)

if __name__ == "__main__":
    main()
