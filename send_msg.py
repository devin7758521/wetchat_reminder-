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

# 密钥读取
WEB_KEY = os.environ.get("WECHAT_WEBHOOK_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY") 
WEBHOOK_URL = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEB_KEY}"

# AI 准备
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
        # 回归最稳的 TEXT 模式，不搞 Markdown
        data = {"msgtype": "text", "text": {"content": content}}
        requests.post(WEBHOOK_URL, json=data, timeout=15)
    except: pass

def check_strategy(code):
    """100% 还原你截图版本中的筛选逻辑"""
    try:
        time.sleep(random.uniform(0.2, 0.4)) # 适度减小延迟
        df = ak.stock_zh_a_hist(symbol=code, period="weekly", adjust="qfq")
        if len(df) < 65: return False
        v_m5 = df['成交量'].rolling(5).mean()
        v_m60 = df['成交量'].rolling(60).mean()
        ma25 = df['收盘'].rolling(25).mean()
        
        # 严格执行 3% 粘合度
        cond_bind = abs(v_m5.iloc[-1] - v_m60.iloc[-1]) / v_m60.iloc[-1] <= 0.03
        cond_up = v_m5.iloc[-1] > v_m5.iloc[-2]
        cond_price = df['收盘'].iloc[-1] > ma25.iloc[-1]
        return cond_bind and cond_up and cond_price
    except: return False

def main():
    part = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    send_wechat(f"🚀 [个股扫描] 第 {part}/2 场启动\n时间: {beijing_time()}")
    
    # 1. 获取基础池
    try:
        df = ak.stock_zh_a_spot_em()
        df.rename(columns={'代码': 'code', '名称': 'name', '最新价': 'price', '成交额': 'amount'}, inplace=True)
        df['code'] = df['code'].astype(str).str.zfill(6)
        mask = (df['code'].str.startswith(('60', '00'))) & (~df['name'].str.contains("ST|\\*ST"))
        df = df[mask].sort_values(by='amount', ascending=False).head(1200)
        stocks = df.head(600) if part == 1 else df.tail(600)
    except:
        send_wechat("❌ 基础数据抓取失败")
        return

    hit_map = defaultdict(list)
    final_list = []

    # 2. 开始筛选
    for _, row in stocks.iterrows():
        if check_strategy(row["code"]):
            # 只有选中的才去查行业，保护接口不被封
            try:
                info = ak.stock_individual_info_em(symbol=row["code"])
                ind = info[info['item'] == '板块'].iloc[0]['value']
            except: ind = "未知行业"
            
            hit_map[ind].append(f"{row['name']}({row['code']})")
            final_list.append({"name": row['name'], "ind": ind, "price": row['price'], "amount": row['amount']})

    # 3. 组装原始结果（确保你截图里的那串名单能出来）
    summary = ""
    for ind, names in hit_map.items():
        summary += f"🔥 [{ind}]: {', '.join(names)}\n"

    if not summary:
        send_wechat(f"✅ 第 {part} 部分完毕\n---\n无信号")
        return

    # 4. 锦上添花：AI 对成交额最大的票写理由
    ai_msg = "\n🤖 AI 精选研报:\n"
    top_5 = sorted(final_list, key=lambda x: x['amount'], reverse=True)[:5]
    for item in top_stocks:
        if GEMINI_KEY and ai_model:
            try:
                prompt = f"分析A股{item['name']}({item['ind']}),现价{item['price']}。周线量能粘合后突破,给星级和30字理由。"
                res = ai_model.generate_content(prompt).text.strip()
                ai_msg += f"⭐ {item['name']}: {res}\n"
            except: pass

    # 最终发送
    send_wechat(f"✅ 第 {part} 部分完毕\n---\n{summary}{ai_msg if len(final_list)>0 else ''}")

if __name__ == "__main__":
    main()
