import pandas as pd
import requests
import akshare as ak
import warnings
import time
import random
import sys
import os
from datetime import datetime, timedelta
from collections import defaultdict

warnings.filterwarnings("ignore")

WEB_KEY = os.environ.get("WECHAT_WEBHOOK_KEY")
WEBHOOK_URL = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEB_KEY}"

def beijing_time():
    return (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")

def send_wechat(content):
    if not WEB_KEY: return
    try:
        data = {"msgtype": "text", "text": {"content": content}}
        requests.post(WEBHOOK_URL, json=data, timeout=15)
    except: pass

def get_split_stocks(part=1):
    try:
        df = ak.stock_zh_a_spot_em()
        df.rename(columns={'代码': 'code', '名称': 'name', '最新价': 'price', '成交额': 'amount'}, inplace=True)
        df['code'] = df['code'].astype(str).str.zfill(6)
        mask = (df['code'].str.startswith(('60', '00'))) & (~df['name'].str.contains("ST|\\*ST"))
        df = df[mask].sort_values(by='amount', ascending=False).head(1200)
        return df.head(600) if part == 1 else df.tail(600)
    except: return pd.DataFrame()

def get_stock_analysis(code):
    try:
        time.sleep(0.3)
        info = ak.stock_individual_info_em(symbol=code)
        return info[info['item'] == '板块'].iloc[0]['value']
    except: return "其他"

def check_strategy(code):
    try:
        time.sleep(random.uniform(0.3, 0.5))
        df = ak.stock_zh_a_hist(symbol=code, period="weekly", adjust="qfq")
        if len(df) < 65: return False
        v_m5, v_m60 = df['成交量'].rolling(5).mean(), df['成交量'].rolling(60).mean()
        ma25 = df['收盘'].rolling(25).mean()
        cond_bind = abs(v_m5.iloc[-1] - v_m60.iloc[-1]) / v_m60.iloc[-1] <= 0.03
        cond_up = v_m5.iloc[-1] > v_m5.iloc[-2]
        cond_price = df['收盘'].iloc[-1] > ma25.iloc[-1]
        return cond_bind and cond_up and cond_price
    except: return False

def main():
    part = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    send_wechat(f"🚀 [个股] 第 {part}/2 场启动\n时间: {beijing_time()}")
    stocks = get_split_stocks(part=part)
    hit_map = defaultdict(list)
    for _, row in stocks.iterrows():
        if check_strategy(row["code"]):
            ind = get_stock_analysis(row["code"])
            hit_map[ind].append(f"{row['name']}({row['code']})")
    
    content = ""
    for ind, names in hit_map.items():
        tag = "🔥" if len(names) > 1 else "📌"
        content += f"{tag} {ind}: {', '.join(names)}\n"
    send_wechat(f"✅ 第 {part} 部分完毕\n---\n{content if content else '无信号'}")

if __name__ == "__main__":
    main()
