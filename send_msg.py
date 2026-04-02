import pandas as pd
import requests
import akshare as ak
import time
import sys
import os
import json
from datetime import datetime

# 配置
VERSION = "v2026.04.02.Sina.Pro"
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
        top_news = news_df['新闻标题'].head(3).tolist()
        return " | ".join(top_news)
    except:
        return "新闻检索接口繁忙。"

def check_strategy(code, name):
    try:
        symbol = code.replace("sh", "").replace("sz", "")
        # 周线历史数据
        df = ak.stock_zh_a_hist(symbol=symbol, period="weekly", adjust="qfq")
        if len(df) < 65: return False
        
        curr_price = df['收盘'].iloc[-1]
        if not (3.0 <= curr_price <= 70.0): return False

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

    if mode == "1":
        send_wechat(f"📢 机器人启动\n时间: {now_str}\n任务: {period_tag} 扫描开始...")

    if mode == "summary":
        all_hits = []
        for f in ["hits_part1.json", "hits_part2.json"]:
            if os.path.exists(f):
                with open(f, "r") as file:
                    try:
                        all_hits += json.load(file)
                    except: pass
        
        if not all_hits:
            send_wechat(f"📅 {now_str}\n{period_tag} 扫描结束，未发现信号。")
            return

        top_hits = sorted(all_hits, key=lambda x: x['amount'], reverse=True)[:10]
        enriched_list = []
        for stock in top_hits:
            clean_code = stock['code'].replace("sh", "").replace("sz", "")
            news = get_stock_news(clean_code)
            enriched_list.append(f"- {stock['name']}({clean_code}): {news}")
        
        api_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"
        prompt = (
            f"你是首席投资官。北京时间 {now_str} {period_tag}。\n"
            f"量能突破标的及内参：\n" + "\n".join(enriched_list) + 
            "\n请分析内参及宏观背景，严格筛选并给出星级评定(🌟)。"
        )
        
        try:
            res = requests.post(api_url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60)
            ai_text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
            send_wechat(f"🌟 {period_tag} 深度决策报告\n\n{ai_text}")
        except Exception as e:
            send_wechat(f"❌ AI 决策异常: {str(e)[:50]}")
            
    else:
        part = int(mode)
        # --- 接口名称自动适配 ---
        try:
            # 优先尝试新版接口名
            df = ak.stock_zh_a_spot_sina()
        except AttributeError:
            # 备选接口名
            df = ak.stock_zh_a_s_spot_sina()
        
        # 1. 筛选 60/00 开头 且 非 ST
        df['pure_code'] = df['symbol'].str[-6:] 
        mask_main = df['pure_code'].str.startswith(('60', '00'))
        mask_no_st = ~df['name'].str.contains('ST|退', na=False)
        active = df[mask_main & mask_no_st].copy()
        
        # 2. 筛选价格 3 到 70 元
        active['trade'] = pd.to_numeric(active['trade'], errors='coerce')
        price_filtered = active[(active['trade'] >= 3.0) & (active['trade'] <= 70.0)].copy()
        
        # 3. 筛选成交额前 1200
        # 适配不同版本的字段名
        amount_col = 'amount' if 'amount' in price_filtered.columns else 'volume'
        price_filtered[amount_col] = pd.to_numeric(price_filtered[amount_col], errors='coerce')
        top_1200 = price_filtered.sort_values(by=amount_col, ascending=False).head(1200)
        
        batch = top_1200.head(600) if part == 1 else top_1200.tail(600)
        
        hits = []
        for _, row in batch.iterrows():
            if check_strategy(row['pure_code'], row['name']):
                hits.append({"name": row['name'], "code": row['symbol'], "amount": row[amount_col]})
        
        with open(f"hits_part{part}.json", "w") as f: 
            json.dump(hits, f)

if __name__ == "__main__": main()
