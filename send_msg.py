import pandas as pd
import requests
import akshare as ak
import time
import sys
import os
import json

# 配置
VERSION = "v2026.03.29.Stock.G2.5"
WEB_KEY = os.environ.get("WECHAT_WEBHOOK_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

def send_wechat(content):
    if not WEB_KEY: return
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEB_KEY}"
    requests.post(url, json={"msgtype": "text", "text": {"content": content}})

def check_strategy(code, name):
    try:
        # 增加日志：显示正在检查哪只股票
        print(f"检查中: {name} ({code})...", end="\r")
        df = ak.stock_zh_a_hist(symbol=code, period="weekly", adjust="qfq")
        if len(df) < 65: return False
        v5 = df['成交量'].rolling(5).mean().iloc[-1]
        v60 = df['成交量'].rolling(60).mean().iloc[-1]
        ma25 = df['收盘'].rolling(25).mean().iloc[-1]
        res = (abs(v5 - v60) / v60 <= 0.03) and (df['收盘'].iloc[-1] > ma25)
        if res: print(f"\n✅ 【命中】{name} ({code}) 符合粘合策略！")
        return res
    except: return False

def main():
    mode = sys.argv[1]
    if mode == "summary":
        print("\n=== 开始 AI 汇总点评 ===")
        all_hits = []
        for f in ["hits_part1.json", "hits_part2.json"]:
            if os.path.exists(f):
                with open(f, "r") as file: all_hits += json.load(file)
        
        if not all_hits:
            send_wechat("今日市场未发现量能粘合信号。")
            return

        top_5 = sorted(all_hits, key=lambda x: x['amount'], reverse=True)[:5]
        api_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
        prompt = f"你是量化分析师。点评以下周线量能粘合个股，给1-5星及15字点评：\n" + "\n".join([f"{x['name']}({x['code']})" for x in top_5])
        
        try:
            res = requests.post(api_url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
            ai_text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
            send_wechat(f"🚀 个股量化汇总 ({VERSION})\n{ai_text}\n\n总命中: {len(all_hits)}")
            print("AI 汇总完成并已发送。")
        except Exception as e:
            send_wechat(f"AI 汇总失败: {str(e)}")
            
    else:
        part = int(mode)
        print(f"=== 开始 Part {part} 扫描 (活跃股前1200) ===")
        df = ak.stock_zh_a_spot_em()
        df['code'] = df['代码'].astype(str).str.zfill(6)
        active = df[df['code'].str.startswith(('60','00'))].sort_values(by='成交额', ascending=False).head(1200)
        batch = active.head(600) if part == 1 else active.tail(600)
        
        hits = []
        for _, row in batch.iterrows():
            if check_strategy(row['code'], row['名称']):
                hits.append({"name": row['名称'], "code": row['code'], "amount": row['成交额']})
        
        with open(f"hits_part{part}.json", "w") as f: json.dump(hits, f)
        print(f"\nPart {part} 扫描完成，保存结果。")

if __name__ == "__main__": main()
