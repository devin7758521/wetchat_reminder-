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

# --- 版本号定义 ---
VERSION = "v2026.03.29.01"

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
    except:
        pass

def beijing_time():
    return (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")

def send_wechat(content):
    if not WEB_KEY: return
    try:
        # 使用最稳定的 TEXT 模式
        data = {"msgtype": "text", "text": {"content": content}}
        requests.post(WEBHOOK_URL, json=data, timeout=15)
    except:
        pass

def check_strategy(code):
    """100% 还原你的核心筛选算法"""
    try:
        time.sleep(random.uniform(0.2, 0.4))
        df = ak.stock_zh_a_hist(symbol=code, period="weekly", adjust="qfq")
        if len(df) < 65: return False
        
        v_m5 = df['成交量'].rolling(5).mean()
        v_m60 = df['成交量'].rolling(60).mean()
        ma25 = df['收盘'].rolling(25).mean()
        
        # 3% 粘合度阈值
        cond_bind = abs(v_m5.iloc[-1] - v_m60.iloc[-1]) / v_m60.iloc[-1] <= 0.03
        cond_up = v_m5.iloc[-1] > v_m5.iloc[-2]
        cond_price = df['收盘'].iloc[-1] > ma25.iloc[-1]
        
        return cond_bind and cond_up and cond_price
    except:
        return False

def main():
    part = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    send_wechat(f"🚀 [个股扫描] Part {part}/2 {VERSION}\n启动时间: {beijing_time()}")
    
    # 1. 抓取行情快照
    try:
        df = ak.stock_zh_a_spot_em()
        df.rename(columns={'代码': 'code', '名称': 'name', '最新价': 'price', '成交额': 'amount'}, inplace=True)
        df['code'] = df['code'].astype(str).str.zfill(6)
        mask = (df['code'].str.startswith(('60', '00'))) & (~df['name'].str.contains("ST|\\*ST"))
        df_sorted = df[mask].sort_values(by='amount', ascending=False).head(1200)
        stocks = df_sorted.head(600) if part == 1 else df_sorted.tail(600)
    except Exception as e:
        send_wechat(f"❌ 数据源抓取异常: {str(e)}")
        return

    hit_map = defaultdict(list)
    final_list = []

    # 2. 策略筛选
    for _, row in stocks.iterrows():
        if check_strategy(row["code"]):
            # 选中后才查行业，确保不触发高频封锁
            try:
                info = ak.stock_individual_info_em(symbol=row["code"])
                ind = info[info['item'] == '板块'].iloc[0]['value']
            except:
                ind = "未知行业"
            
            hit_map[ind].append(f"{row['name']}({row['code']})")
            final_list.append({
                "name": row['name'], 
                "ind": ind, 
                "price": row['price'], 
                "amount": row['amount']
            })

    # 3. 构造名单汇总
    summary = ""
    for ind, names in hit_map.items():
        summary += f"🔥 [{ind}]: {', '.join(names)}\n"

    if not summary:
        send_wechat(f"✅ Part {part} 扫描完毕 ({VERSION})\n---\n今日暂无信号")
        return

    # 4. AI 研判（针对成交额 Top 5）
    ai_msg = "\n🤖 AI 深度点评:\n"
    top_5 = sorted(final_list, key=lambda x: x['amount'], reverse=True)[:5]
    
    has_ai = False
    if ai_model and GEMINI_KEY:
        for item in top_5:
            try:
                prompt = f"分析A股{item['name']}({item['ind']})。现价{item['price']}元。周线量能粘合后突破。给出推荐星级和30字理由。"
                response = ai_model.generate_content(prompt)
                ai_msg += f"⭐ {item['name']}: {response.text.strip()}\n"
                has_ai = True
                time.sleep(1.5) # 避开 API 频率限制
            except:
                continue

    # 5. 组合最终消息
    final_report = f"✅ Part {part} 完毕 {VERSION}\n---\n{summary}"
    if has_ai:
        final_report += ai_report_header if 'ai_report_header' in locals() else "\n"
        final_report += ai_msg
        
    send_wechat(final_report)

if __name__ == "__main__":
    main()
