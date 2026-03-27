import pandas as pd
import requests
import akshare as ak
import warnings
import os
import time
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")

# ===================== 配置信息 =====================
WEBHOOK_KEY = os.getenv("WEBHOOK_KEY", "da748662-f3d1-4edd-8031-2ee05c428605")
WEBHOOK_URL = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEBHOOK_KEY}"

def beijing_time():
    return (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")

def send_wechat(content):
    try:
        if len(content) > 2000:
            content = content[:1900] + "\n...(Content too long, truncated)"
        data = {"msgtype": "text", "text": {"content": content}}
        requests.post(WEBHOOK_URL, json=data, timeout=15)
    except:
        pass

# ===================== 核心：修正后的全量名单获取 =====================
def get_strictly_main_board():
    """彻底解决58只问题：获取全量主板名单"""
    try:
        # 换用这个接口，它只返回代码和名称，不返回行情，极其稳定且全
        df = ak.stock_info_a_code_name()
        
        # 1. 格式化代码为6位字符串
        df['code'] = df['code'].astype(str).str.zfill(6)
        
        # 2. 严格过滤条件：
        # 仅保留 60 (沪市主板) 和 00 (深市主板)
        # 排除所有含有 ST 的名称
        main_mask = (
            (df['code'].str.startswith(('60', '00'))) & 
            (~df['name'].str.contains("ST|\\*ST", na=False))
        )
        
        res = df[main_mask][['code', 'name']].copy()
        return res
    except Exception as e:
        print(f"Failed to fetch stock list: {e}")
        return pd.DataFrame()

# ===================== 均量线逻辑 =====================
def check_strategy(code):
    """5/60日均量粘合向上逻辑"""
    try:
        # 只抓取最近 100 天数据计算均线，防止请求过大被封
        start_dt = (datetime.now() - timedelta(days=100)).strftime("%Y%m%d")
        
        df = ak.stock_zh_a_hist(
            symbol=code, 
            period="daily", 
            start_date=start_dt, 
            adjust="hfq"
        )
        
        if df is None or len(df) < 60:
            return False

        # 统一列名计算
        v_col = [c for c in df.columns if '成交量' in c][0]
        v_series = df[v_col]
        
        v_m5 = v_series.rolling(5).mean()
        v_m60 = v_series.rolling(60).mean()

        last_v5 = v_m5.iloc[-1]
        last_v60 = v_m60.iloc[-1]
        prev_v5 = v_m5.iloc[-2]
        pprev_v5 = v_m5.iloc[-3]

        if last_v60 <= 0: return False

        # 条件 A: 5日与60日均量粘合 (3%以内)
        cond_bind = abs(last_v5 - last_v60) / last_v60 <= 0.03
        # 条件 B: 5日均量趋势向上 (连续两日增长)
        cond_up = last_v5 > prev_v5 > pprev_v5
        
        return True if (cond_bind and cond_up) else False
    except:
        return False

# ===================== 主程序 =====================
def main():
    start_time = time.time()
    now_str = beijing_time()
    print(f"🚀 [Stock Selection Bot] Scanning Market: {now_str}")
    
    stocks = get_strictly_main_board()
    if stocks.empty:
        print("❌ Error: Stock list is empty!")
        return

    total = len(stocks)
    # 这行打印至关重要，你运行后看这里是不是 3000 左右
    print(f"📊 Confirmed: Analyzing {total} main board stocks...")
    
    hit_list = []
    
    for i, (_, row) in enumerate(stocks.iterrows()):
        code, name = row["code"], row["name"]
        
        if check_strategy(code):
            hit_list.append(f"{code} {name}")
            print(f"🎯 Target Found: {code} {name}")
        
        # 节奏控制
        if (i + 1) % 100 == 0:
            print(f"Progress: {i+1}/{total}...")
            time.sleep(1)
        else:
            time.sleep(0.01)

    # 结果推送
    duration = int(time.time() - start_time)
    msg = f"【Stock Selection Bot - Main Board】\n"
    msg += f"Time: {now_str}\n"
    msg += f"Strategy: Volume MA Convergence (5/60)\n"
    msg += f"----------------------------\n"
    
    if hit_list:
        msg += f"🔥 Hits ({len(hit_list)}): \n" + "\n".join(hit_list)
    else:
        msg += "✅ Scan complete, no matches today."
    
    msg += f"\n----------------------------\nTotal: {total} | Duration: {duration}s"
    
    print(msg)
    send_wechat(msg)

if __name__ == "__main__":
    main()
