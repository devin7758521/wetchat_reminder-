import pandas as pd
import requests
import akshare as ak
import warnings
import time
import random
import sys
from datetime import datetime, timedelta

# 屏蔽告警
warnings.filterwarnings("ignore")

# ===================== 配置信息 =====================
WEBHOOK_KEY = "da748662-f3d1-4edd-8031-2ee05c428605"
WEBHOOK_URL = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEBHOOK_KEY}"

def beijing_time():
    return (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")

def send_wechat(content):
    """【修复点】改回你最初的 text 格式，确保 100% 兼容"""
    try:
        # 这里改回了 msgtype: text
        data = {"msgtype": "text", "text": {"content": content}}
        requests.post(WEBHOOK_URL, json=data, timeout=15)
    except:
        pass

# ===================== 核心：分段获取名单 (1-600 / 601-1200) =====================
def get_split_stocks(part=1):
    try:
        print(f"📡 正在准备扫描第 {part}/2 部分活跃股...")
        df = ak.stock_zh_a_spot_em()
        if df is None or df.empty: return pd.DataFrame()

        rename_dict = {'代码': 'code', '名称': 'name', '最新价': 'price', '成交额': 'amount'}
        df.rename(columns=rename_dict, inplace=True)
        df['code'] = df['code'].astype(str).str.zfill(6)
        
        mask = (df['code'].str.startswith(('60', '00'))) & (~df['name'].astype(str).str.contains("ST|\\*ST", na=False))
        df['price'] = pd.to_numeric(df['price'], errors='coerce')
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
        mask &= (df['price'] > 3) & (df['price'] < 70)
        
        all_active = df[mask].sort_values(by='amount', ascending=False).head(1200)
        
        if part == 1:
            return all_active.head(600)
        else:
            return all_active.tail(600)
    except Exception as e:
        print(f"❌ 列表获取异常: {e}")
        return pd.DataFrame()

def get_stock_analysis(code):
    """获取分析数据：所属行业 + 近5日表现"""
    try:
        time.sleep(0.5)
        info = ak.stock_individual_info_em(symbol=code)
        industry = info[info['item'] == '板块'].iloc[0]['value']
        
        hist = ak.stock_zh_a_hist(symbol=code, period="daily", 
                                  start_date=(datetime.now()-timedelta(days=12)).strftime("%Y%m%d"), 
                                  adjust="qfq")
        if len(hist) >= 5:
            five_day_pct = round(((hist['收盘'].iloc[-1] / hist['收盘'].iloc[-5]) - 1) * 100, 2)
            trend = "+" if five_day_pct > 0 else ""
            return f"\n行业: {industry}\n5日涨跌: {trend}{five_day_pct}%"
        return f"\n行业: {industry}"
    except:
        return ""

# ===================== 选股逻辑 (完全保留你的核心条件) =====================
def check_strategy(code):
    try:
        time.sleep(random.uniform(0.4, 0.7))
        start_dt = (datetime.now() - timedelta(days=730)).strftime("%Y%m%d")
        df = ak.stock_zh_a_hist(symbol=code, period="weekly", start_date=start_dt, adjust="qfq")
        
        if df is None or len(df) < 65: return False

        v_series = df['成交量'].astype(float)
        v_m5, v_m60 = v_series.rolling(5).mean(), v_series.rolling(60).mean()
        last_v5, prev_v5, pprev_v5 = v_m5.iloc[-1], v_m5.iloc[-2], v_m5.iloc[-3]
        last_v60 = v_m60.iloc[-1]

        p_series = df['收盘'].astype(float)
        ma25 = p_series.rolling(25).mean()
        last_price, last_ma25 = p_series.iloc[-1], ma25.iloc[-1]

        if last_v60 <= 0 or pd.isna(last_ma25): return False

        cond_bind = abs(last_v5 - last_v60) / last_v60 <= 0.03
        cond_up = last_v5 > prev_v5 > pprev_v5
        cond_price = last_price > last_ma25
        
        return cond_bind and cond_up and cond_price
    except:
        return False

# ===================== 主流程 =====================
def main():
    part = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    
    start_ts = time.time()
    # 推送内容也改回了纯文本排版
    send_wechat(f"🚀 [AI选股] 第 {part}/2 场启动\n时间: {beijing_time()}\n范围: 活跃榜 {(part-1)*600+1}-{part*600}名")
    
    stocks = get_split_stocks(part=part)
    if stocks.empty: return

    total = len(stocks)
    hit_list = []
    
    for i, (_, row) in enumerate(stocks.iterrows()):
        code, name = row["code"], row["name"]
        if check_strategy(code):
            analysis = get_stock_analysis(code)
            hit_list.append(f"📌 {name} ({code}){analysis}")
            print(f"🎯 命中: {code} {name}")
        
        if (i + 1) % 10 == 0: print(f"进度: {i+1}/{total}...")
        if (i + 1) % 50 == 0: time.sleep(5)

    duration = int(time.time() - start_ts)
    
    header = f"✅ 第 {part} 部分扫描完毕\n------------------\n"
    if hit_list:
        content = "\n\n".join(hit_list)
    else:
        content = "今日此区间无信号"
    
    footer = f"\n------------------\n耗时: {duration}s\n时间: {beijing_time()}"
    
    send_wechat(header + content + footer)
    print("🏁 执行完毕。")

if __name__ == "__main__":
    main()
