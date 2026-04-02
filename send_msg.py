import pandas as pd
import requests
import akshare as ak
import time
import sys
import os
import json
from datetime import datetime

# 配置
VERSION = "v2026.03.29.CIO.Pro"
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
    【新增：内参模块】为指定个股抓取最近3条核心新闻标题
    """
    try:
        # 获取东方财富个股新闻
        news_df = ak.stock_news_em(symbol=code)
        if news_df.empty: return "暂无近期核心公告。"
        # 取前3条新闻标题，组合成摘要
        top_news = news_df['新闻标题'].head(3).tolist()
        return " | ".join(top_news)
    except:
        return "新闻检索接口繁忙。"

def check_strategy(code, name):
    try:
        df = ak.stock_zh_a_hist(symbol=code, period="weekly", adjust="qfq")
        if len(df) < 65: return False
        curr_price = df['收盘'].iloc[-1]
        if not (3.0 <= curr_price <= 70.0): return False

        v5 = df['成交量'].rolling(5).mean()
        v60 = df['成交量'].rolling(60).mean()
        ma25 = df['收盘'].rolling(25).mean()

        vol_up = v5.iloc[-1] > v5.iloc[-2]
        deviation = abs(v5.iloc[-1] - v60.iloc[-1]) / v60.iloc[-1]
        is_binding = deviation <= 0.03
        
        # --- 修改处开始：偏离度计算逻辑 ---
        # 计算 (V5 - V60) / V60 的百分比
        deviation = (v5.iloc[-1] - v60.iloc[-1]) / v60.iloc[-1]
        # 筛选范围：-3% 到 +7% 之间
        is_binding = -0.03 <= deviation <= 0.07
        # --- 修改处结束 ---

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
        send_wechat(f"📢 机器人启动\n时间: {now_str}\n任务: {period_tag} 扫描开始...")

    if mode == "summary":
        all_hits = []
        for f in ["hits_part1.json", "hits_part2.json"]:
            if os.path.exists(f):
                with open(f, "r") as file: all_hits += json.load(file)

        if not all_hits:
            send_wechat(f"📅 {now_str}\n{period_tag} 扫描结束，未发现信号标的。")
            return

        # 选成交额 Top 10
        top_hits = sorted(all_hits, key=lambda x: x['amount'], reverse=True)[:10]

        # --- 核心改进：为 Top 10 逐一装载“内参” ---
        enriched_list = []
        for stock in top_hits:
            print(f"正在抓取内参: {stock['name']}...")
            news = get_stock_news(stock['code'])
            enriched_list.append(f"- {stock['name']}({stock['code']}): {news}")

        api_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"

        prompt = (
            f"你是具备全球视野的首席投资官。当前北京时间 {now_str} {period_tag}。\n"
            f"以下是 10 只量能突破标的及其【实时核心新闻内参】。请执行深度复核：\n\n"
            f"【决策维度】：\n"
            f"1. **基于内参推理**：分析所给新闻对股价的短期/中期影响。有重大利空（如立案、减持）直接判死刑。\n"
            f"2. **宏观背景联动**：结合当前国内外大形势（如美国加息、地缘政治等）判断该行业是否处于风口。\n"
            f"3. **星级评定**：5星严格限制在 1-2 只。用🌟表示星级。\n\n"
            f"【输出要求】：\n"
            f"   - 🌟🌟... 股票名(代码) + 30字内深度走向预测（必须结合所给内参或宏观背景）。\n"
            f"   - 未获星标的：仅在下方显示“代码 名称”。\n\n"
            f"【待分析内参名单】：\n"
            + "\n".join(enriched_list)
        )

        try:
            res = requests.post(api_url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60)
            ai_text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
            send_wechat(f"🌟 {period_tag} 深度决策报告\n时间: {now_str}\n\n{ai_text}\n\n📊 今日总信号: {len(all_hits)}")
        except Exception as e:
            send_wechat(f"❌ AI 决策异常: {str(e)[:100]}")

    else:
        # Part 1/2 扫描逻辑保持不变
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
