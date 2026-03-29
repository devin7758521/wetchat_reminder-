import pandas as pd
import requests
import akshare as ak
import os
import json

VERSION = "v2026.03.29.ETF.G2.5"
WEB_KEY = os.environ.get("WECHAT_WEBHOOK_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

def send_wechat(content):
    if not WEB_KEY: return
    requests.post(f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEB_KEY}", json={"msgtype": "text", "text": {"content": content}})

def main():
    print("=== 开始 ETF 专项扫描 ===")
    try:
        df = ak.fund_etf_spot_em()
        hits = []
        # 扫描成交额前 60 的主流 ETF
        for _, row in df.sort_values(by='成交额', ascending=False).head(60).iterrows():
            try:
                print(f"检查 ETF: {row['名称']}...", end="\r")
                hist = ak.fund_etf_hist_em(symbol=row['代码'], period="weekly", adjust="qfq")
                v5 = hist['成交量'].rolling(5).mean().iloc[-1]
                v60 = hist['成交量'].rolling(60).mean().iloc[-1]
                if abs(v5-v60)/v60 <= 0.03 and hist['收盘'].iloc[-1] > hist['收盘'].rolling(25).mean().iloc[-1]:
                    print(f"\n🎯 【ETF命中】{row['名称']}")
                    hits.append(row['名称'])
            except: continue

        if hits:
            api_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
            prompt = f"作为分析师，简短点评以下有量能粘合信号的ETF：{','.join(hits[:5])}。"
            res = requests.post(api_url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
            ai_text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
            send_wechat(f"💎 ETF 专项报告 ({VERSION})\n{ai_text}\n\n信号标的: {','.join(hits)}")
        else:
            send_wechat("ETF 今日无粘合信号。")
    except Exception as e:
        print(f"ETF 任务异常: {e}")

if __name__ == "__main__": main()
