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

warnings.filterwarnings("ignore")

# 从 Secrets 读取
WEB_KEY = os.environ.get("WECHAT_WEBHOOK_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY") 
WEBHOOK_URL = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEB_KEY}"

if GEMINI_KEY:
    try:
        genai.configure(api_key=GEMINI_KEY)
        ai_model = genai.GenerativeModel('gemini-1.5-flash')
    except: ai_model = None

def beijing_time():
    return (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")

def send_wechat(content):
    if not WEB_KEY: return
    try:
        # 👈 这里改回了你最开始使用的 text 格式，确保不报错
        data = {"msgtype": "text", "text": {"content": content}}
        requests.post(WEBHOOK_URL, json=data, timeout=15)
    except: pass

def get_ai_analysis(name, industry, price):
    if not GEMINI_KEY or not ai_model: return "（AI 未就绪）"
    prompt = f"分析A股{name}({industry}),现价{price}元。该股周线量能粘合后突破,请结合行业给一个星级推荐和30字理由。格式:【X星】理由"
    try:
        response = ai_model.generate_content(prompt)
        return response.text.strip()
    except: return "AI 分析中..."

def get_split_stocks(part=1):
    try:
        df = ak.stock_zh_a_spot_em()
        df.rename(columns={'代码': 'code', '名称': 'name', '最新价': 'price', '成交额': 'amount'}, inplace=True)
        df['code'] = df['code'].astype(str).str.zfill(6)
        mask = (df['code'].str.startswith(('60', '00'))) & (~df['name'].str.contains("ST|\\*ST"))
        df = df[mask].sort_values(by='amount', ascending=False).head(1200)
        return df.head(600) if part == 1 else df.tail(600)
    except: return pd.DataFrame()

def get_stock_analysis(code):
    try:
        time.sleep(0.3)
        info = ak.stock_individual_info_em(symbol=code)
        return info[info['item'] == '板块'].iloc[0]['value']
    except: return "其他"

def check_strategy(code):
    try:
        time.sleep(random.uniform(0.3, 0.5))
        df = ak.stock_zh_a_hist(symbol=code, period="weekly", adjust="qfq")
        if len(df) < 65: return False
        v_m5, v_m60 = df['成交量'].rolling(5).mean(), df['成交量'].rolling(60).mean()
        ma25 = df['收盘'].rolling(25).mean()
        cond_bind = abs(v_m5.iloc[-1] - v_m60.iloc[-1]) / v_m60.iloc[-1] <= 0.03
        cond_up = v_m5.iloc[-1] > v_m5.iloc[-2]
        cond_price = df['收盘'].iloc[-1] > ma25.iloc[-1]
        return cond_bind and cond_up and cond_price
    except: return False

def main():
    part = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    send_wechat(f"🚀 [个股扫描] 第 {part}/2 场\n时间: {beijing_time()}")
    
    stocks = get_split_stocks(part=part)
    qualified_list = []
    for _, row in stocks.iterrows():
        if check_strategy(row["code"]):
            ind = get_stock_analysis(row["code"])
            qualified_list.append({"name": row['name'], "code": row['code'], "ind": ind, "price": row['price'], "amount": row['amount']})
    
    final_targets = sorted(qualified_list, key=lambda x: x['amount'], reverse=True)[:10]
    if not final_targets:
        send_wechat(f"✅ 第 {part} 部分扫描完毕，暂无信号。")
        return

    # 拼接纯文本报告
    content = ""
    for item in final_targets:
        remark = get_ai_analysis(item['name'], item['ind'], item['price'])
        content += f"\n⭐ {item['name']}({item['code']}) | {item['ind']}\n价格: {item['price']}\nAI: {remark}\n"
        time.sleep(2)
        
    send_wechat(f"✅ 第 {part} 部分精选报告\n{content}")

if __name__ == "__main__":
    main()
