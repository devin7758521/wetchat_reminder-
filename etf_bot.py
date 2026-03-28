import pandas as pd
import requests
import akshare as ak
import warnings
import time
import os
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")

WEB_KEY = os.environ.get("WECHAT_WEBHOOK_KEY")
WEBHOOK_URL = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEB_KEY}"

def send_wechat(content):
    if not WEB_KEY: return
    try:
        data = {"msgtype": "text", "text": {"content": content}}
        requests.post(WEBHOOK_URL, json=data, timeout=15)
    except: pass

def get_etf_list():
    try:
        df = ak.fund_etf_spot_em()
        df = df[df['成交额'] > 10000000]
        # 简单去重逻辑
        df['simple_name'] = df['名称'].str.extract(r'(.+?)(?:ETF|基金)')
        return df.sort_values(by='成交额', ascending=False).drop_duplicates(subset=['simple_name'])
    except: return pd.DataFrame()

def check_etf_strategy(code):
    try:
        time.sleep(0.5)
        df = ak.fund_etf_hist_em(symbol=code, period="weekly", adjust="qfq")
        if len(df) < 65: return False
        v_m5, v_m60 = df['成交量'].rolling(5).mean(), df['成交量'].rolling(60).mean()
        ma25 = df['收盘'].rolling(25).mean()
        return (abs(v_m5.iloc[-1] - v_m60.iloc[-1]) / v_m60.iloc[-1] <= 0.03) and (df['收盘'].iloc[-1] > ma25.iloc[-1])
    except: return False

def main():
    send_wechat(f"📊 [ETF 专项] 14:30 扫描启动")
    etfs = get_etf_list()
    hits = [f"💎 {row['名称']}({row['代码']})" for _, row in etfs.iterrows() if check_etf_strategy(row['代码'])]
    send_wechat(f"✅ ETF 扫描完毕\n---\n" + ("\n".join(hits) if hits else "无信号"))

if __name__ == "__main__":
    main()
