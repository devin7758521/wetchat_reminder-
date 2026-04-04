import pandas as pd
import requests
import akshare as ak
import time
import sys
import os
import json
import re
from datetime import datetime, timedelta

# ==================== 配置 ====================
VERSION = "v2026.04.04.CIO.Gemini2.5.Fixed"
WEB_KEY = os.environ.get("WECHAT_WEBHOOK_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

# ==================== 网络防护：加强版 Headers 绕过海外拦截 ====================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://quote.eastmoney.com/center/gridlist.html",
    "Connection": "keep-alive"
}

def safe_req(url, desc="req"):
    """带指数级退避重试的请求，应对海外波动"""
    for attempt in range(1, 4):
        try:
            res = requests.get(url, headers=HEADERS, timeout=20)
            res.raise_for_status()
            return res
        except Exception as e:
            wait = 5 * attempt
            print(f"⚠️ [{desc}] 失败: {str(e)[:50]}，{wait}秒后重试({attempt}/3)...")
            time.sleep(wait)
    return None

def get_spot_data():
    """直接请求东财 JSON 接口获取全市场行情"""
    url = "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=10000&po=1&np=1&fltt=2&invt=2&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f14,f2,f6"
    res = safe_req(url, desc="全市场行情")
    if not res: return pd.DataFrame()
    data = res.json().get('data')
    if not data or not data.get('diff'): return pd.DataFrame()
    df = pd.DataFrame(data['diff'])[['f12', 'f14', 'f2', 'f6']]
    df.columns = ['代码', '名称', '最新价', '成交额']
    df['代码'] = df['代码'].astype(str)
    df['最新价'] = pd.to_numeric(df['最新价'], errors='coerce')
    df['成交额'] = pd.to_numeric(df['成交额'], errors='coerce')
    return df[df['最新价'] > 0]

def get_hist_data(code, start_date):
    """直接请求东财 JSON 接口获取前复权K线"""
    # 【核心修正】0或3开头为深证(0)，6开头为上证(1)
    market = 0 if code.startswith(('0', '3')) else 1
    url = f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={market}.{code}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=1&beg={start_date}&end=20500101&lmt=800"
    
    res = safe_req(url, desc=f"K线-{code}")
    if not res: return None
    data = res.json().get('data')
    if not data or not data.get('klines'): return None

    df = pd.DataFrame([k.split(',') for k in data['klines']],
                      columns=['日期', '开盘', '收盘', '最高', '最低', '成交量', '成交额', '振幅', '涨跌幅', '涨跌额', '换手率'])
    df['日期'] = pd.to_datetime(df['日期'])
    df['收盘'] = pd.to_numeric(df['收盘'], errors='coerce')
    df['成交量'] = pd.to_numeric(df['成交量'], errors='coerce')
    return df.set_index('日期')[['收盘', '成交量']]

# ==================== 业务逻辑 (保持原样) ====================

def send_wechat(content):
    if not WEB_KEY: return
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEB_KEY}"
    try: requests.post(url, json={"msgtype": "text", "text": {"content": content}}, timeout=10)
    except: pass

def get_stock_news(code):
    try:
        news_df = ak.stock_news_em(symbol=code)
        if news_df.empty: return {"status": "无内参", "news": "", "code": code}
        return {"status": "✅ 成功", "news": " | ".join(news_df['新闻标题'].head(3).tolist()), "code": code}
    except: return {"status": "❌ 异常", "news": "", "code": code}

def check_strategy(code, name, realtime_spot_dict):
    try:
        start_date = (datetime.now() - timedelta(days=800)).strftime('%Y%m%d')
        df_daily = get_hist_data(code, start_date)
        if df_daily is None or len(df_daily) < 125: return False
        
        curr_price = realtime_spot_dict.get(code, df_daily['收盘'].iloc[-1])
        if not (3.0 <= curr_price <= 70.0): return False

        df_daily = df_daily.copy()
        df_daily['week'] = df_daily.index.to_period('W')
        weekly_vol = df_daily.groupby('week')['成交量'].sum()
        
        if len(weekly_vol) < 61: return False
        v5 = weekly_vol.rolling(5).mean().iloc[-1]
        v60 = weekly_vol.rolling(60).mean().iloc[-1]
        
        ma125 = df_daily['收盘'].rolling(125).mean().iloc[-1]
        vol_up = v5 > weekly_vol.rolling(5).mean().iloc[-2]
        is_binding = -0.03 <= (v5 - v60) / v60 <= 0.07
        
        if vol_up and is_binding and curr_price > ma125:
            print(f"🎯 命中信号: {name}({code})")
            return True
    except Exception as e:
        print(f"❌ {code} 分析异常: {e}")
    return False

def main():
    if len(sys.argv) < 2: return
    mode = sys.argv[1]
    now = datetime.now()
    
    if mode == "1" and now.weekday() == 0:
        if os.path.exists("weekly_stars.json"): os.remove("weekly_stars.json")
    
    if mode == "summary":
        all_hits = []
        for f in ["hits_part1.json", "hits_part2.json"]:
            if os.path.exists(f):
                with open(f, "r", encoding="utf-8") as file: all_hits += json.load(file)
        if not all_hits:
            send_wechat(f"今日扫描结束，未发现符合要求标的。")
            return
        
        # 【修改点】调回 gemini-2.5-flash
        api_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
        enriched = [f"- {s['name']}({s['code']}): {get_stock_news(s['code'])['news']}" for s in sorted(all_hits, key=lambda x:x['amount'], reverse=True)[:10]]
        prompt = f"你是具备全球视野的首席投资官，请基于以下内参评定星级：\n\n" + "\n".join(enriched)
        
        try:
            res = requests.post(api_url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60)
            ai_text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
            send_wechat(f"🎯 深度决策报告 (Gemini 2.5)\n\n{ai_text}")
        except: send_wechat("❌ AI 决策链路故障")

    else:
        part = int(mode)
        df = get_spot_data()
        if df.empty: return
        
        df = df[df['代码'].str.startswith(('60', '00')) & ~df['名称'].str.contains('ST')]
        active = df.sort_values(by='成交额', ascending=False).head(1200)
        batch = active.head(600) if part == 1 else active.tail(600)
        spot_dict = dict(zip(df['代码'], df['最新价']))

        hits = []
        for _, row in batch.iterrows():
            if check_strategy(row['代码'], row['名称'], spot_dict):
                hits.append({"name": row['名称'], "code": row['代码'], "amount": row['成交额']})
            time.sleep(0.25) # 加长延时防止海外IP过快被封

        with open(f"hits_part{part}.json", "w", encoding="utf-8") as f:
            json.dump(hits, f, ensure_ascii=False)

if __name__ == "__main__":
    main()
