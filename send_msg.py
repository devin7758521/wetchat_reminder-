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
    """
    抓取个股新闻（保持东财接口，因为新闻类接口封锁较松）
    """
    try:
        news_df = ak.stock_news_em(symbol=code)
        if news_df.empty: return "暂无近期核心公告。"
        top_news = news_df['新闻标题'].head(3).tolist()
        return " | ".join(top_news)
    except:
        return "新闻检索接口繁忙。"

def check_strategy(code, name):
    """
    个股技术面复核（周线逻辑）
    """
    try:
        # 转换代码格式以适应历史接口
        symbol = code.replace("sh", "").replace("sz", "")
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

        if vol_up and is_binding and price_support:
            return True
        return False
    except: return False

def main():
    if len(sys.argv) < 2: return
    mode = sys.argv[1]
    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M')
    period_tag = "【早盘观察】" if now.hour < 12 else "【尾盘决策】"

    if mode == "1":
        send_wechat(f"📢 机器人启动(新浪源)\n时间: {now_str}\n任务: {period_tag} 扫描开始...")

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
            # 这里的 stock['code'] 需要去掉 sh/sz 前缀发给新闻接口
            clean_code = stock['code'].replace("sh", "").replace("sz", "")
            news = get_stock_news(clean_code)
            enriched_list.append(f"- {stock['name']}({clean_code}): {news}")
        
        api_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"
        
        prompt = (
            f"你是具备全球视野的首席投资官。当前北京时间 {now_str} {period_tag}。\n"
            f"以下是 10 只量能突破标的及其实时内参。请执行深度复核：\n\n"
            f"【决策维度】：1.内参推理 2.宏观背景 3.星级评定(🌟)\n"
            f"【输出要求】：🌟星级 + 股票名(代码) + 30字内走向预测。\n\n"
            + "\n".join(enriched_list)
        )
        
        try:
            res = requests.post(api_url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60)
            ai_text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
            send_wechat(f"🌟 {period_tag} 深度决策报告\n时间: {now_str}\n\n{ai_text}\n\n📊 今日总信号: {len(all_hits)}")
        except Exception as e:
            send_wechat(f"❌ AI 决策异常: {str(e)[:100]}")
            
    else:
        part = int(mode)
        # --- 切换为新浪接口 ---
        df = ak.stock_zh_a_spot_sina()
        
        # 1. 选 60/00 开头 且 非 ST
        # 新浪的代码格式通常为 sh600000 或 sz000001
        df['pure_code'] = df['symbol'].str[-6:] 
        mask_main = df['pure_code'].str.startswith(('60', '00'))
        mask_no_st = ~df['name'].str.contains('ST|退', na=False)
        active = df[mask_main & mask_no_st].copy()
        
        # 2. 选价格在 3 到 70 元 (新浪价格字段名为 'trade')
        active['trade'] = pd.to_numeric(active['trade'], errors='coerce')
        price_filtered = active[(active['trade'] >= 3.0) & (active['trade'] <= 70.0)].copy()
        
        # 3. 选成交额排名前 1200 (新浪成交额字段名为 'amount')
        price_filtered['amount'] = pd.to_numeric(price_filtered['amount'], errors='coerce')
        top_1200 = price_filtered.sort_values(by='amount', ascending=False).head(1200)
        
        batch = top_1200.head(600) if part == 1 else top_1200.tail(600)
        
        hits = []
        for _, row in batch.iterrows():
            # 传入 6 位纯数字代码
            if check_strategy(row['pure_code'], row['name']):
                hits.append({"name": row['name'], "code": row['symbol'], "amount": row['amount']})
        
        with open(f"hits_part{part}.json", "w") as f: 
            json.dump(hits, f)

if __name__ == "__main__": main()
