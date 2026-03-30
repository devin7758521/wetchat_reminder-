import pandas as pd
import requests
import akshare as ak
import os
import json
from datetime import datetime

# 配置
VERSION = "v2026.03.30.ETF.Pro.Final"
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

def get_etf_news(name):
    try:
        keyword = "A股"
        theme_map = {
            "半导体": "半导体", "芯片": "芯片", "医疗": "医疗", "医药": "医药",
            "证券": "证券", "券商": "券商", "白酒": "白酒", "科创": "科创板",
            "创业": "创业板", "恒生": "恒生科技", "纳指": "纳斯达克", "银行": "银行",
            "300": "沪深300", "500": "中证500", "1000": "中证1000", "50": "上证50",
            "新能源": "新能源", "光伏": "光伏", "军工": "军工", "AI": "人工智能",
            "有色": "有色金属", "消费": "消费", "食品": "食品饮料"
        }
        for k, v in theme_map.items():
            if k in name:
                keyword = v
                break

        news_df = ak.news_baidu(keyword=keyword)
        if news_df.empty:
            return "关注该板块宏观波动。"

        titles = news_df['title'].head(3).tolist()
        return " | ".join([t[:40] for t in titles])
    except:
        return "板块资讯检索中。"

def check_strategy(code, name):
    try:
        df = ak.fund_etf_hist_em(symbol=code, period="weekly", adjust="qfq")
        if len(df) < 65:
            return False

        v5 = df['成交量'].rolling(5).mean().iloc[-1]
        v60 = df['成交量'].rolling(60).mean().iloc[-1]

        if v60 <= 0:
            return False

        deviation = abs(v5 - v60) / v60
        ma25 = df['收盘'].rolling(25).mean().iloc[-1]
        close = df['收盘'].iloc[-1]

        if deviation <= 0.03 and close > ma25:
            return True
        return False
    except:
        return False

def deduplicate_hits(hits):
    if not hits:
        return []
    hits_sorted = sorted(hits, key=lambda x: x['amount'], reverse=True)
    key_themes = ['300', '500', '1000', '50', '半导体', '芯片', '医疗', '医药', '白酒', '证券', '券商', '恒生', '纳斯达克', '创业板', '科创板']
    deduped_hits = []
    seen_themes = set()
    for etf in hits_sorted:
        theme = '其他'
        for t in key_themes:
            if t in etf['name']:
                theme = t
                break
        if theme == '其他' or theme not in seen_themes:
            deduped_hits.append(etf)
            if theme != '其他':
                seen_themes.add(theme)
    return deduped_hits[:10]

def main():
    if not WEB_KEY:
        return
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    print("=== ETF Pro 扫描启动 ===")

    try:
        df_spot = ak.fund_etf_spot_em()
        all_hits = []

        for _, row in df_spot.sort_values(by='成交额', ascending=False).head(60).iterrows():
            print(f"检查: {row['名称']}...", end="\r")
            if check_strategy(row['代码'], row['名称']):
                all_hits.append({
                    "name": row['名称'],
                    "code": row['代码'],
                    "amount": row['成交额']
                })

        if all_hits:
            top_10 = deduplicate_hits(all_hits)
            enriched_list = []
            for etf in top_10:
                print(f"抓取板块内参: {etf['name']}...")
                news = get_etf_news(etf['name'])
                enriched_list.append(f"- {etf['name']}({etf['code']}): {news}")

            api_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
            prompt = (
                f"你是首席投资官。当前时间 {now_str}。\n"
                f"以下是量能粘合的 ETF 及其【板块核心新闻内参】。请执行配置复核：\n\n"
                f"1. **内参分析**：根据所给板块新闻，判断该 ETF 对应的行业目前是处于利好爆发期还是利空潜伏期。\n"
                f"2. **宏观联动**：结合国内外宏观背景（汇率、加息路径、地缘风险）给出配置评分。\n"
                f"3. **星级评定**：最值得配置的给 🌟🌟🌟🌟🌟（限1-2只）。其余用 🔹 简洁显示。\n\n"
                f"【待分析内参名单】：\n"
                + "\n".join(enriched_list)
            )

            try:
                res = requests.post(api_url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60)
                ai_text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                send_wechat(f"💎 ETF CIO 深度报告 ({VERSION})\n时间: {now_str}\n\n{ai_text}\n\n📊 信号池去重后总数: {len(top_10)}")
            except Exception as e:
                msg = f"❌ AI 决策超时\n\n"
                msg += f"📅 {now_str}\n今日量能粘合 ETF 信号：\n"
                for etf in top_10:
                    msg += f"- {etf['name']}({etf['code']})\n"
                send_wechat(msg)

        else:
            send_wechat(f"📅 {now_str}\n今日主流 ETF 中未发现粘合信号。")

    except Exception as e:
        print(f"ETF 异常: {e}")

if __name__ == "__main__":
    main()
