import pandas as pd
import requests
import akshare as ak
import google.generativeai as genai
import warnings
import time
import random
import sys
import os
from datetime import datetime, timedelta
from collections import defaultdict
from tqdm import tqdm  # 注入进度条灵魂

warnings.filterwarnings("ignore")

# --- 版本号 ---
VERSION = "v2026.03.29.02"

# 密钥读取
WEB_KEY = os.environ.get("WECHAT_WEBHOOK_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
WEBHOOK_URL = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEB_KEY}"

# AI 准备
ai_model = None
if GEMINI_KEY:
    try:
        genai.configure(api_key=GEMINI_KEY)
        ai_model = genai.GenerativeModel('gemini-1.5-flash')
    except: pass

def beijing_time():
    return (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")

def send_wechat(content):
    if not WEB_KEY: return
    try:
        data = {"msgtype": "text", "text": {"content": content}}
        requests.post(WEBHOOK_URL, json=data, timeout=15)
    except: pass

def check_strategy(code):
    """3% 极致粘合策略逻辑"""
    try:
        # 这里保留微小延迟，防止被 API 封锁
        time.sleep(random.uniform(0.15, 0.3))
        df = ak.stock_zh_a_hist(symbol=code, period="weekly", adjust="qfq")
        if len(df) < 65: return False
        v_m5 = df['成交量'].rolling(5).mean()
        v_m60 = df['成交量'].rolling(60).mean()
        ma25 = df['收盘'].rolling(25).mean()
        
        cond_bind = abs(v_m5.iloc[-1] - v_m60.iloc[-1]) / v_m60.iloc[-1] <= 0.03
        cond_up = v_m5.iloc[-1] > v_m5.iloc[-2]
        cond_price = df['收盘'].iloc[-1] > ma25.iloc[-1]
        return cond_bind and cond_up and cond_price
    except: return False

def main():
    part = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    send_wechat(f"🚀 [个股扫描] Part {part}/2 {VERSION}\n启动: {beijing_time()}")
    
    # 获取数据池
    try:
        df = ak.stock_zh_a_spot_em()
        df.rename(columns={'代码': 'code', '名称': 'name', '最新价': 'price', '成交额': 'amount'}, inplace=True)
        df['code'] = df['code'].astype(str).str.zfill(6)
        mask = (df['code'].str.startswith(('60', '00'))) & (~df['name'].str.contains("ST|\\*ST"))
        df_sorted = df[mask].sort_values(by='amount', ascending=False).head(1200)
        stocks = df_sorted.head(600) if part == 1 else df_sorted.tail(600)
    except Exception as e:
        send_wechat(f"❌ 基础数据异常: {str(e)}")
        return

    hit_map = defaultdict(list)
    ai_targets = []

    # --- 核心循环：tqdm 实现网页进度条 ---
    # desc 会显示在 GitHub 日志里
    progress_bar = tqdm(stocks.iterrows(), total=len(stocks), desc=f"Scanning P{part}")
    
    for i, (_, row) in enumerate(progress_bar):
        curr_idx = i + 1
        
        # 1. 网页日志进度更新
        progress_bar.set_postfix({"Stock": row['name'], "Hits": len(ai_targets)})
        
        # 2. 微信每 50 只同步一次进度
        if curr_idx % 50 == 0:
            send_wechat(f"📊 进度: {curr_idx + (part-1)*600}/1200...")

        # 3. 执行筛选
        if check_strategy(row["code"]):
            try:
                info = ak.stock_individual_info_em(symbol=row["code"])
                ind = info[info['item'] == '板块'].iloc[0]['value']
            except: ind = "未知行业"
            
            # 命中立即发微信，不让你久等
            send_wechat(f"🎯 命中 [{ind}]: {row['name']}({row['code']})")
            
            hit_map[ind].append(f"{row['name']}({row['code']})")
            ai_targets.append({"name": row['name'], "ind": ind, "price": row['price'], "amount": row['amount']})

    # --- 最终结果输出 ---
    summary = ""
    for ind, names in hit_map.items():
        summary += f"🔥 [{ind}]: {', '.join(names)}\n"

    if not summary:
        send_wechat(f"✅ Part {part} 扫完 ({VERSION})\n今日无信号")
        return

    # 4. AI 评价逻辑
    ai_msg = "\n🤖 AI 研报点评:\n"
    top_5 = sorted(ai_targets, key=lambda x: x['amount'], reverse=True)[:5]
    for item in top_5:
        if ai_model:
            try:
                prompt = f"分析A股{item['name']}({item['ind']})。现价{item['price']}元。周线量能粘合后突破。给星级和30字理由。"
                res = ai_model.generate_content(prompt).text.strip()
                ai_msg += f"⭐ {item['name']}: {res}\n"
                time.sleep(1.5)
            except: pass

    send_wechat(f"✅ Part {part} 任务达成！\n---\n{summary}{ai_msg}")

if __name__ == "__main__":
    main()
