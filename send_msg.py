import pandas as pd
import requests
import akshare as ak
import time
import sys
import os
import json
from datetime import datetime

# 配置
VERSION = "v2026.03.29.Elite.Final"
WEB_KEY = os.environ.get("WECHAT_WEBHOOK_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

def send_wechat(content):
    if not WEB_KEY: return
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEB_KEY}"
    try:
        requests.post(url, json={"msgtype": "text", "text": {"content": content}}, timeout=10)
    except: pass

def check_strategy(code, name):
    """
    策略：价格(3-70) + 周线量能粘合(±3%) + 5周均量向上↗️ + 站稳25周线
    """
    try:
        print(f"正在扫描: {name} ({code})...", end="\r")
        df = ak.stock_zh_a_hist(symbol=code, period="weekly", adjust="qfq")
        if len(df) < 65: return False
        
        # 1. 价格限制: 3.0元 - 70.0元
        curr_price = df['收盘'].iloc[-1]
        if not (3.0 <= curr_price <= 70.0):
            return False

        # 2. 计算量能指标
        v5 = df['成交量'].rolling(5).mean()
        v60 = df['成交量'].rolling(60).mean()
        ma25 = df['收盘'].rolling(25).mean()
        
        # 3. 核心判定逻辑
        vol_up = v5.iloc[-1] > v5.iloc[-2]               # 5周均量正在往上走
        deviation = abs(v5.iloc[-1] - v60.iloc[-1]) / v60.iloc[-1]
        is_binding = deviation <= 0.03                 # 粘合度在 3% 以内
        price_support = curr_price > ma25.iloc[-1]      # 站稳25周线(牛熊线)

        if vol_up and is_binding and price_support:
            print(f"\n🎯 命中信号: {name}({code}) | 价格:{curr_price} | 偏离度:{deviation:.2%}")
            return True
        return False
    except: return False

def main():
    if len(sys.argv) < 2: return
    mode = sys.argv[1]
    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M')
    period_tag = "【早盘观察】" if now.hour < 12 else "【尾盘决策】"

    # --- 启动通知 ---
    if mode == "1":
        send_wechat(f"📢 机器人启动通知\n时间: {now_str}\n任务: {period_tag} 扫描开始...")

    if mode == "summary":
        all_hits = []
        for f in ["hits_part1.json", "hits_part2.json"]:
            if os.path.exists(f):
                with open(f, "r") as file: 
                    all_hits += json.load(file)
        
        if not all_hits:
            send_wechat(f"📅 {now_str}\n{period_tag} 扫描结束，今日未发现符合要求标的。")
            return

        # 选成交额前 10 名进入 AI 决赛圈
        top_hits = sorted(all_hits, key=lambda x: x['amount'], reverse=True)[:10]
        
        api_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
        
        # --- 核心 Prompt: AI 最高权重分析 ---
        prompt = (
            f"你是具备全球视野的首席投资官。当前时间 {now_str} {period_tag}。\n"
            f"以下10只个股通过了量能粘合筛选。请执行最高权重的深度复核：\n\n"
            f"1. **检索近期新闻**：请检索这10只标的最近48小时内的【核心公告、行业利好/利空、突发新闻】。\n"
            f"2. **结合宏观背景**：结合当前【国内外宏观形势】（如美联储利率政策、美元汇率、地缘政治）评估该行业走向。\n"
            f"3. **星级评定**：用实心星号展示（如：🌟🌟🌟🌟🌟）。\n"
            f"   - 【5星】仅限 1-2 只：代表‘技术面+新闻利好+宏观受益’的最优解。\n"
            f"   - 其他根据潜力给 1-4 星。\n"
            f"4. **输出要求**：\n"
            f"   - 获星标的：🌟🌟... 股票名(代码) + 30字内走向预测（必须结合新闻或宏观依据）。\n"
            f"   - 未获星标的：在下方仅以‘代码 名称’形式列出，不要点评。\n\n"
            f"待分析名单：\n"
            + "\n".join([f"- {x['name']}({x['code']}), 成交额:{x['amount']/1e8:.2f}亿" for x in top_hits])
        )
        
        try:
            res = requests.post(api_url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60)
            ai_text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
            send_wechat(f"🌟 {period_tag} 深度决策报告\n时间: {now_str}\n\n{ai_text}\n\n📊 今日总信号数: {len(all_hits)}")
        except Exception as e:
            send_wechat(f"❌ AI 决策阶段异常: {str(e)[:100]}")
            
    else:
        part = int(mode)
        df = ak.stock_zh_a_spot_em()
        df['code'] = df['代码'].astype(str).str.zfill(6)
        # 筛选活跃度前 1200 名的主板股票
        active = df[df['code'].str.startswith(('60','00'))].sort_values(by='成交额', ascending=False).head(1200)
        batch = active.head(600) if part == 1 else active.tail(600)
        
        hits = []
        for _, row in batch.iterrows():
            if check_strategy(row['code'], row['名称']):
                hits.append({"name": row['名称'], "code": row['code'], "amount": row['成交额']})
        
        with open(f"hits_part{part}.json", "w") as f: json.dump(hits, f)

if __name__ == "__main__": main()
