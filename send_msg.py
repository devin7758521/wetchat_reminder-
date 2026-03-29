import pandas as pd
import requests
import akshare as ak
import time
import sys
import os
import json
from datetime import datetime

# 配置
VERSION = "v2026.03.29.Elite.V10"
WEB_KEY = os.environ.get("WECHAT_WEBHOOK_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

def send_wechat(content):
    if not WEB_KEY: return
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEB_KEY}"
    requests.post(url, json={"msgtype": "text", "text": {"content": content}})

def check_strategy(code, name):
    """
    策略：周线量能粘合(±3%) + 5周均量向上进攻 + 价格站稳25周线
    """
    try:
        df = ak.stock_zh_a_hist(symbol=code, period="weekly", adjust="qfq")
        if len(df) < 65: return False
        
        v5 = df['成交量'].rolling(5).mean()
        v60 = df['成交量'].rolling(60).mean()
        ma25 = df['收盘'].rolling(25).mean()
        
        # 判定逻辑
        vol_up = v5.iloc[-1] > v5.iloc[-2] # 5周均量向上↗️
        deviation = abs(v5.iloc[-1] - v60.iloc[-1]) / v60.iloc[-1]
        is_binding = deviation <= 0.03 # 粘合度3%以内
        price_above_ma = df['收盘'].iloc[-1] > ma25.iloc[-1] # 站稳25周线

        if vol_up and is_binding and price_above_ma:
            print(f"🎯 信号命中: {name} ({code}) | 偏离度: {deviation:.2%}")
            return True
        return False
    except: return False

def main():
    if len(sys.argv) < 2: return
    mode = sys.argv[1]
    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M')
    
    # 自动判断当前是早盘还是尾盘
    period_tag = "【早盘观察】" if now.hour < 12 else "【尾盘决策】"

    if mode == "summary":
        all_hits = []
        for f in ["hits_part1.json", "hits_part2.json"]:
            if os.path.exists(f):
                with open(f, "r") as file: all_hits += json.load(file)
        
        if not all_hits:
            send_wechat(f"📅 {now_str}\n{period_tag} 今日未发现符合量能拐点标的。")
            return

        # 选成交额前 10 名
        top_hits = sorted(all_hits, key=lambda x: x['amount'], reverse=True)[:10]
        
        api_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
        
        # 强化 Prompt：严格 5 星配额 + 全球宏观分析
        prompt = (
            f"你是首席投资官。现在是北京时间 {now_str} {period_tag}。\n"
            f"以下10只个股周线量能极度粘合且5周均量向上。请执行以下深度分析：\n\n"
            f"1. **严格打分**：给出 1-5 星评分。【5星】标的必须是你认为的最优解，数量严格限制在 1-2 只（若无可不给）。\n"
            f"2. **宏观联动**：结合当前全球局势（如美联储货币政策、地缘政治、大宗商品）和 A 股热点给出预测。\n"
            f"3. **新闻检索**：检索这 10 只标的最近 48 小时内的核心公告或负面新闻。\n\n"
            f"输出格式（Text）：\n"
            f"★ [股票名称] - [星级]\n"
            f"【走向预测】：[30字内结合宏观、行业与个股的深度点评]\n"
            + "\n".join([f"- {x['name']}({x['code']}), 成交额:{x['amount']/1e8:.2f}亿" for x in top_hits])
        )
        
        try:
            res = requests.post(api_url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60)
            ai_text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
            send_wechat(f"🌟 {period_tag} 决策报告\n时间: {now_str}\n\n{ai_text}\n\n📊 今日信号池总数: {len(all_hits)}")
        except Exception as e:
            send_wechat(f"❌ AI 决策异常: {str(e)[:100]}")
            
    else:
        part = int(mode)
        df = ak.stock_zh_a_spot_em()
        df['code'] = df['代码'].astype(str).str.zfill(6)
        active = df[df['code'].str.startswith(('60','00'))].sort_values(by='成交额', ascending=False).head(1200)
        batch = active.head(600) if part == 1 else active.tail(600)
        
        hits = []
        for _, row in batch.iterrows():
            if check_strategy(row['code'], row['名称']):
                hits.append({"name": row['名称'], "code": row['code'], "amount": row['成交额']})
        
        with open(f"hits_part{part}.json", "w") as f: json.dump(hits, f)

if __name__ == "__main__": main()
