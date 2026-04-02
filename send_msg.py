import pandas as pd
import requests
import akshare as ak
import time
import sys
import os
import json
from datetime import datetime

# 配置
VERSION = "v2026.04.02.QQ.Pro"
WEB_KEY = os.environ.get("WECHAT_WEBHOOK_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

def send_wechat(content):
    if not WEB_KEY: return
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEB_KEY}"
    try:
        requests.post(url, json={"msgtype": "text", "text": {"content": content}}, timeout=10)
    except: pass

def get_stock_news(code):
    try:
        news_df = ak.stock_news_em(symbol=code)
        if news_df.empty: return "暂无近期核心公告。"
        return " | ".join(news_df['新闻标题'].head(3).tolist())
    except:
        return "新闻检索接口繁忙。"

def check_strategy(code, name):
    try:
        # 统一去掉前缀，只保留6位数字
        symbol = "".join(filter(str.isdigit, code))
        df = ak.stock_zh_a_hist(symbol=symbol, period="weekly", adjust="qfq")
        if len(df) < 65: return False
        
        curr_price = df['收盘'].iloc[-1]
        v5 = df['成交量'].rolling(5).mean()
        v60 = df['成交量'].rolling(60).mean()
        ma25 = df['收盘'].rolling(25).mean()
        
        vol_up = v5.iloc[-1] > v5.iloc[-2]
        deviation = (v5.iloc[-1] - v60.iloc[-1]) / v60.iloc[-1]
        is_binding = -0.03 <= deviation <= 0.07
        price_support = curr_price > ma25.iloc[-1]

        return vol_up and is_binding and price_support
    except: return False

def main():
    if len(sys.argv) < 2: return
    mode = sys.argv[1]
    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M')
    period_tag = "【早盘观察】" if now.hour < 12 else "【尾盘决策】"

    if mode == "summary":
        all_hits = []
        for f in ["hits_part1.json", "hits_part2.json"]:
            if os.path.exists(f):
                with open(f, "r") as file: all_hits += json.load(file)
        
        if not all_hits:
            send_wechat(f"📅 {now_str}\n{period_tag} 扫描结束，未发现信号标的。")
            return

        top_hits = sorted(all_hits, key=lambda x: x['amount'], reverse=True)[:10]
        enriched_list = []
        for stock in top_hits:
            clean_code = "".join(filter(str.isdigit, stock['code']))
            news = get_stock_news(clean_code)
            enriched_list.append(f"- {stock['name']}({clean_code}): {news}")
        
        api_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"
        prompt = (f"你是首席投资官。北京时间 {now_str} {period_tag}。\n"
                  f"对以下10只标的结合内参做复核：\n"
                  + "\n".join(enriched_list) + 
                  "\n要求：🌟星级 + 股票名 + 30字内深度预测。")
        
        try:
            res = requests.post(api_url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60)
            ai_text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
            send_wechat(f"🌟 {period_tag} 深度决策报告\n\n{ai_text}\n\n📊 总信号: {len(all_hits)}")
        except Exception as e:
            send_wechat(f"❌ AI 决策异常: {str(e)[:100]}")
            
    else:
        part = int(mode)
        # --- 使用腾讯接口，绕过新浪和东财的报错 ---
        try:
            df = ak.stock_zh_a_spot_qq()
        except:
            send_wechat("❌ 接口全面封锁，请检查网络。")
            return
        
        # 1. 选 60/00 开头 且 非 ST
        df['pure_code'] = df['代码'].astype(str).str.zfill(6)
        mask_main = df['pure_code'].str.startswith(('60', '00'))
        mask_no_st = ~df['名称'].str.contains('ST|退', na=False)
        active = df[mask_main & mask_no_st].copy()
        
        # 2. 选价格在 3 到 70 元
        active['最新价'] = pd.to_numeric(active['最新价'], errors='coerce')
        price_filtered = active[(active['最新价'] >= 3.0) & (active['最新价'] <= 70.0)].copy()
        
        # 3. 选成交额排名前 1200 (腾讯接口字段名为 '成交额')
        price_filtered['成交额'] = pd.to_numeric(price_filtered['成交额'], errors='coerce')
        top_1200 = price_filtered.sort_values(by='成交额', ascending=False).head(1200)
        
        batch = top_1200.head(600) if part == 1 else top_1200.tail(600)
        
        hits = []
        for _, row in batch.iterrows():
            if check_strategy(row['pure_code'], row['名称']):
                hits.append({"name": row['名称'], "code": row['pure_code'], "amount": row['成交额']})
        
        with open(f"hits_part{part}.json", "w") as f: 
            json.dump(hits, f)

if __name__ == "__main__": main()
