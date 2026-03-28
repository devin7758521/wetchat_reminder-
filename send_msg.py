import pandas as pd
import requests
import akshare as ak
import google.generativeai as genai
import warnings
import time
import random
import sys
import os
import json
from datetime import datetime
from collections import defaultdict
from tqdm import tqdm

warnings.filterwarnings("ignore")

# --- 核心版本号 ---
VERSION = "v2026.03.29.Final.v4"

# 密钥配置
WEB_KEY = os.environ.get("WECHAT_WEBHOOK_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
WEBHOOK_URL = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEB_KEY}"

# AI 初始化
ai_model = None
if GEMINI_KEY:
    try:
        genai.configure(api_key=GEMINI_KEY)
        ai_model = genai.GenerativeModel('gemini-1.5-flash')
    except: pass

def send_wechat(content):
    if not WEB_KEY: return
    try:
        data = {"msgtype": "text", "text": {"content": content}}
        requests.post(WEBHOOK_URL, json=data, timeout=15)
    except: pass

def check_strategy(code):
    """
    量化策略核心 (周线级别 Period='weekly')：
    1. 周线量能粘合 <= 3%
    2. 均量向上 + 站稳25周线
    3. 周线 MACD DIF >= DEA (红柱区间)
    """
    try:
        time.sleep(random.uniform(0.1, 0.2))
        df = ak.stock_zh_a_hist(symbol=code, period="weekly", adjust="qfq")
        if len(df) < 65: return False
        
        v_m5, v_m60 = df['成交量'].rolling(5).mean(), df['成交量'].rolling(60).mean()
        ma25 = df['收盘'].rolling(25).mean()
        
        ema12 = df['收盘'].ewm(span=12, adjust=False).mean()
        ema26 = df['收盘'].ewm(span=26, adjust=False).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9, adjust=False).mean()
        
        cond = [
            abs(v_m5.iloc[-1] - v_m60.iloc[-1]) / v_m60.iloc[-1] <= 0.03, 
            v_m5.iloc[-1] > v_m5.iloc[-2],                                
            df['收盘'].iloc[-1] > ma25.iloc[-1],                          
            dif.iloc[-1] >= dea.iloc[-1]
        ]
        return all(cond)
    except: return False

def main():
    # 接收参数：1(前600), 2(后600), summary(汇总)
    arg = sys.argv[1] if len(sys.argv) > 1 else "1"

    # --- [模式 A] 汇总模式 (由 12:00 和 15:55 的 Part 2 触发) ---
    if arg == "summary":
        all_hits = []
        # 读取 Part 1 和 Part 2 的结果
        for f_name in ["hits_part1.json", "hits_part2.json"]:
            if os.path.exists(f_name):
                try:
                    with open(f_name, "r", encoding="utf-8") as f:
                        all_hits += json.load(f)
                except: pass
        
        if not all_hits:
            send_wechat(f"🏁 1200只周线全扫描 ({VERSION})\n今日未发现信号。")
            return

        # 汇总分类
        hit_map = defaultdict(list)
        for h in all_hits:
            hit_map[h['ind']].append(f"{h['name']}({h['code']})")
        
        summary_text = ""
        for ind, names in hit_map.items():
            summary_text += f"🔥 [{ind}]: {', '.join(names)}\n"

        # AI 评分：Top 5
        final_top = sorted(all_hits, key=lambda x: x['amount'], reverse=True)[:5]
        ai_msg = "\n📊 顶级量化分析师评分 (Top 5):\n"
        
        for item in final_top:
            if ai_model:
                try:
                    # 你的硬性要求：顶级身份 + 5星必选1-2个 + 严谨分布
                    prompt = (f"你现在是顶级量化分析师。请点评A股{item['name']}({item['ind']})，现价{item['price']}元。"
                              f"该股已通过【周线级】量能粘合及MACD红柱过滤。请给出【星级(1-5星)】及25字内专业点评。"
                              f"要求：1. 评价要专业严谨；2. 5星代表全场最完美，【必须】给1-2个5星（绝不能没有）；"
                              f"3. 其余个股根据强度在1-4星间客观打分。")
                    response = ai_model.generate_content(prompt)
                    ai_msg += f"⭐ {item['name']}: {response.text.strip()}\n"
                    time.sleep(2.5) 
                except: pass

        send_wechat(f"🏁 1200只全扫描汇总 ({VERSION})\n---\n{summary_text}{ai_msg}")
        return

    # --- [模式 B] 扫描模式 (Part 1 或 Part 2) ---
    part = int(arg)
    print(f"🚀 Part {part} 启动扫描...")
    
    try:
        df = ak.stock_zh_a_spot_em()
        df.rename(columns={'代码':'code','名称':'name','最新价':'price','成交额':'amount'}, inplace=True)
        df['code'] = df['code'].astype(str).str.zfill(6)
        mask = (df['code'].str.startswith(('60','00'))) & (~df['name'].str.contains("ST|\\*ST"))
        all_stocks = df[mask].sort_values(by='amount', ascending=False).head(1200)
        stocks = all_stocks.head(600) if part == 1 else all_stocks.tail(600)
    except: return

    current_hits = []
    for _, row in stocks.iterrows():
        if check_strategy(row["code"]):
            try:
                info = ak.stock_individual_info_em(symbol=row["code"])
                ind = info[info['item'] == '板块'].iloc[0]['value']
            except: ind = "相关赛道"
            current_hits.append({"name":row['name'], "code":row['code'], "ind":ind, "price":row['price'], "amount":row['amount']})

    # 保存文件供 Summary 模式调用
    with open(f"hits_part{part}.json", "w", encoding="utf-8") as f:
        json.dump(current_hits, f)
    print(f"✅ Part {part} 完成，结果已保存。")

if __name__ == "__main__":
    main()
