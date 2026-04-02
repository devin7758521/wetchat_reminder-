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
    if not WEB_KEY:
        return
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEB_KEY}"
    try:
        requests.post(url, json={"msgtype": "text", "text": {"content": content}}, timeout=10)
    except:
        pass


def get_stock_news(code):
    """为指定个股抓取最近3条核心新闻标题"""
    try:
        news_df = ak.stock_news_em(symbol=code)
        if news_df.empty:
            return "暂无近期核心公告。"
        top_news = news_df['新闻标题'].head(3).tolist()
        return " | ".join(top_news)
    except:
        return "新闻检索接口繁忙。"


def check_strategy(code, name):
    """策略：价格(3-70) + 周线量能粘合(-3%到7%) + 5周均量向上 + 站稳25周线"""
    try:
        df = ak.stock_zh_a_hist(symbol=code, period="weekly", adjust="qfq")
        if len(df) < 65:
            return False

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
        is_binding = 0.03 <= deviation <= 0.07          # 粘合度在 -3% 到 7% 之间
        price_support = curr_price > ma25.iloc[-1]      # 站稳25周线(牛熊线)

        if vol_up and is_binding and price_support:
            print(f"\n🎯 命中信号: {name}({code}) | 价格:{curr_price} | 偏离度:{deviation:.2%}")
            return True
        return False
    except:
        return False


def main():
    if len(sys.argv) < 2:
        return
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

        # 选成交额 Top 10（如果没有10个，就全部显示）
        top_hits = sorted(all_hits, key=lambda x: x['amount'], reverse=True)[:10]

        # 为 Top 10 逐一装载"内参"
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
            f"   - 未获星标的：仅在下方显示\"代码 名称\"。\n\n"
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
        # Part 1/2 扫描逻辑
        part = int(mode)
        df = ak.stock_zh_a_spot_em()
        
        # 过滤条件：60和00开头的票，不要ST，价格在3-70元之间
        df = df[
            (df['代码'].astype(str).str.startswith(('60', '00'))) & 
            (~df['名称'].str.contains('ST')) & 
            (3.0 <= df['最新价']) & (df['最新价'] <= 70.0)  # 修复这里的布尔比较
        ]
        
        # 按成交额排序，取前1200名
        active = df.sort_values(by='成交额', ascending=False).head(1200)
        batch = active.head(600) if part == 1 else active.tail(600)

        hits = []
        for _, row in batch.iterrows():
            if check_strategy(row['代码'], row['名称']):
                hits.append({"name": row['名称'], "code": row['代码'], "amount": row['成交额']})

        with open(f"hits_part{part}.json", "w") as f:
            json.dump(hits, f)


if __name__ == "__main__":
    main()
