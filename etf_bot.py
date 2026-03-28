import pandas as pd
import requests
import akshare as ak
import warnings
import time
import random
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")

WEBHOOK_KEY = "da748662-f3d1-4edd-8031-2ee05c428605"
WEBHOOK_URL = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEBHOOK_KEY}"

def beijing_time():
    return (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")

def send_wechat(content):
    try:
        data = {"msgtype": "text", "text": {"content": content}}
        requests.post(WEBHOOK_URL, json=data, timeout=15)
    except: pass

def get_etf_list():
    try:
        print("📡 正在获取 ETF 数据并去重...")
        df = ak.fund_etf_spot_em()
        df.rename(columns={'代码': 'code', '名称': 'name', '最新价': 'price', '成交额': 'amount'}, inplace=True)
        df = df[pd.to_numeric(df['amount'], errors='coerce') > 10000000]
        # 去重：同指数只留成交额最大的
        df['core_name'] = df['name'].str.replace(r'(华夏|易方达|广发|南方|嘉实|华安|富国|招商|汇添富|鹏华|国泰|中欧|天弘|工银|建信|华泰柏瑞|ETF|基金)', '', regex=True)
        df = df.sort_values(by='amount', ascending=False)
        return df.drop_duplicates(subset=['core_name'], keep='first')
    except: return pd.DataFrame()

def check_etf_strategy(code):
    try:
        time.sleep(random.uniform(0.3, 0.5))
        start_dt = (datetime.now() - timedelta(days=730)).strftime("%Y%m%d")
        # ✅ 使用 ETF 专用接口
        df = ak.fund_etf_hist_em(symbol=code, period="weekly", start_date=start_dt, adjust="qfq")
        if df is None or len(df) < 65: return False
        v_series = df['成交量'].astype(float)
        v_m5, v_m60 = v_series.rolling(5).mean(), v_series.rolling(60).mean()
        last_v5, last_v60 = v_m5.iloc[-1], v_m60.iloc[-1]
        p_series = df['收盘'].astype(float)
        ma25 = p_series.rolling(25).mean()
        if last_v60 <= 0 or pd.isna(ma25.iloc[-1]): return False
        cond_bind = abs(last_v5 - last_v60) / last_v60 <= 0.03
        cond_up = last_v5 > v_m5.iloc[-2] > v_m5.iloc[-3]
        cond_price = p_series.iloc[-1] > ma25.iloc[-1]
        return cond_bind and cond_up and cond_price
    except: return False

def main():
    start_ts = time.time()
    send_wechat(f"📊 [ETF 精选扫描] 启动\n时间: {beijing_time()}")
    etfs = get_etf_list()
    if etfs.empty: return
    hit_list = [f"💎 {row['name']} ({row['code']})" for _, row in etfs.iterrows() if check_etf_strategy(row["code"])]
    duration = int(time.time() - start_ts)
    content = "\n".join(hit_list) if hit_list else "暂无信号"
    send_wechat(f"✅ ETF 扫描完毕 (去重后{len(etfs)}只)\n------------------\n{content}\n------------------\n耗时: {duration}s")

if __name__ == "__main__":
    main()
