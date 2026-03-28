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
from collections import defaultdict

warnings.filterwarnings("ignore")

VERSION = "v2026.03.29.Final.v12"

WEB_KEY = os.environ.get("WECHAT_WEBHOOK_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
WEBHOOK_URL = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEB_KEY}"

def send_wechat(content):
    if not WEB_KEY or not content: return
    try:
        data = {"msgtype": "text", "text": {"content": content}}
        requests.post(WEBHOOK_URL, json=data, timeout=15)
    except: pass

def check_strategy(code):
    try:
        time.sleep(random.uniform(0.1, 0.2))
        df = ak.stock_zh_a_hist(symbol=code, period="weekly", adjust="qfq")
        if len(df) < 65: return False
        
        v_m5, v_m60 = df['成交量'].rolling(5).mean(), df['成交量'].rolling(60).mean()
        ma25 = df['收盘'].rolling(25).mean()
        
        # 严格 3% 粘合逻辑
        cond = [
            abs(v_m5.iloc[-1] - v_m60.iloc[-1]) / v_m60.iloc[-1] <= 0.03, 
            v_m5.iloc[-1] > v_m5.iloc[-2],                                
            df['收盘'].iloc[-1] > ma25.iloc[-1]
        ]
        return all(cond)
    except: return False

def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "1"

    # --- [模式 A] 全天 AI 汇总逻辑 ---
    if arg == "summary":
        all_hits = []
        for f_name in ["hits_part1.json", "hits_part2.json"]:
            if os.path.exists(f_name):
                try:
                    with open(f_name, "r", encoding="utf-8") as f:
                        all_hits += json.load(f)
                except: pass
        
        if not all_hits:
            send_wechat(f"🏁 1200只全天扫描结束 ({VERSION})\n今日无 3% 粘合信号。")
            return

        # AI 评分：取 Top 5
        final_top = sorted(all_hits, key=lambda x: x['amount'], reverse=True)[:5]
        ai_msg = f"\n📊 顶级量化分析师·五星必选 (Top {len(final_top)}):\n"
        
        if GEMINI_KEY:
            try:
                genai.configure(api_key=GEMINI_KEY)
                model = genai.GenerativeModel('gemini-1.5-flash')
                for item in final_top:
                    try:
                        prompt = (f"你现在是顶级量化分析师。点评A股{item['name']}({item['ind']})。请给出【星级(1-5星)】及25字内点评。"
                                  f"要求：必须给1-2个5星标杆，其余1-4星客观分布。")
                        response = model.generate_content(prompt)
                        comment = response.text.strip() if response and hasattr(response, 'text') else "生成中..."
                        ai_msg += f"⭐ {item['name']}: {comment}\n"
                        time.sleep(1.5)
                    except: ai_msg += f"⭐ {item['name']}: [AI点评暂时离线]\n"
            except: ai_msg += "⚠️ AI 引擎初始化失败\n"
        else:
            ai_msg += "⚠️ 未配置 GEMINI_API_KEY\n"

        send_wechat(f"🏁 全天 1200 只深度汇总 ({VERSION})\n--------------------------\n{ai_msg}")
        return

    # --- [模式 B] 阶段扫描逻辑 ---
    part = int(arg)
    send_wechat(f"🚀 个股扫描 Part {part} 启动\n(范围：成交额 {'前600' if part==1 else '后600'})")
    
    try:
        df = ak.stock_zh_a_spot_em()
        df.rename(columns={'代码':'code','名称':'name','最新价':'price','成交额':'amount'}, inplace=True)
        df['code'] = df['code'].astype(str).str.zfill(6)
        mask = (df['code'].str.startswith(('60','00'))) & (~df['name'].str.contains("ST|\\*ST"))
        all_stocks = df[mask].sort_values(by='amount', ascending=False).head(1200)
        stocks = all_stocks.head(600) if part == 1 else all_stocks.tail(600)
    except: return

    current_hits = []
    hit_text = ""
    for _, row in stocks.iterrows():
        if check_strategy(row["code"]):
            try:
                info = ak.stock_individual_info_em(symbol=row["code"])
                ind = info[info['item'] == '板块'].iloc[0]['value']
            except: ind = "相关赛道"
            current_hits.append({"name":row['name'], "code":row['code'], "ind":ind, "price":row['price'], "amount":row['amount']})
            hit_text += f"🔥 [{ind}]: {row['name']}({row['code']})\n"

    # 保存文件供汇总使用
    with open(f"hits_part{part}.json", "w", encoding="utf-8") as f:
        json.dump(current_hits, f)
    
    # 立即发送当前阶段结果
    content = f"✅ Part {part} 扫描完成\n命中: {len(current_hits)} 只\n---\n{hit_text if hit_text else '今日无信号'}"
    send_wechat(content)

if __name__ == "__main__":
    main()
