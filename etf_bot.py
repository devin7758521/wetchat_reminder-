import pandas as pd
import requests
import akshare as ak
import os
import json
from datetime import datetime

# 配置
VERSION = "v2026.03.29.ETF.Pro"
WEB_KEY = os.environ.get("WECHAT_WEBHOOK_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

def send_wechat(content):
    if not WEB_KEY: return
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEB_KEY}"
    try:
        requests.post(url, json={"msgtype": "text", "text": {"content": content}}, timeout=10)
    except: pass

def get_etf_news(name):
    """
    【新增：内参模块】抓取该 ETF 行业或主题相关的最新 3 条新闻摘要
    """
    try:
        # 使用东方财富行业/主题新闻接口
        news_df = ak.stock_news_em(symbol=name[:3]) # 截取前三个字作为搜索词
        if news_df.empty: return "关注该板块宏观波动。"
        return " | ".join(news_df['新闻标题'].head(3).tolist())
    except:
        return "板块资讯检索中。"

def check_strategy(code, name):
    try:
        df = ak.fund_etf_hist_em(symbol=code, period="weekly", adjust="qfq")
        if len(df) < 65: return False
        v5 = df['成交量'].rolling(5).mean().iloc[-1]
        v60 = df['成交量'].rolling(60).mean().iloc[-1]
        deviation = abs(v5 - v60) / v60
        # 粘合度 3% + 站稳 25 周线
        if deviation <= 0.03 and df['收盘'].iloc[-1] > df['收盘'].rolling(25).mean().iloc[-1]:
            return True
        return False
    except: return False

def deduplicate_hits(hits):
    """
    ETF 行业去重逻辑
    """
    if not hits: return []
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
            if theme != '其他': seen_themes.add(theme)
    return deduped_hits[:10]

def main():
    if not WEB_KEY: return
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    print("=== ETF Pro 扫描启动 ===")
    
    try:
        df_spot = ak.fund_etf_spot_em()
        all_hits = []
        # 扫描成交额前 60 的主流 ETF
        for _, row in df_spot.sort_values(by='成交额', ascending=False).head(60).iterrows():
            print(f"检查: {row['名称']}...", end="\r")
            if check_strategy(row['代码'], row['名称']):
                all_hits.append({"name": row['名称'], "code": row['代码'], "amount": row['成交额']})
        
        if all_hits:
            top_10 = deduplicate_hits(all_hits)
            
            # --- 核心改进：为 ETF 装载实时新闻内参 ---
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
                send_wechat(f"❌ AI 决策超时: {str(e)[:100]}")
        else:
            send_wechat(f"📅 {now_str}\n今日主流 ETF 中未发现粘合信号。")
            
    except Exception as e:
        print(f"ETF 异常: {e}")

if __name__ == "__main__": main()
