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

warnings.filterwarnings("ignore")

VERSION = "v2026.03.29.Final.v8"

# 密钥获取
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
        cond = [
            abs(v_m5.iloc[-1] - v_m60.iloc[-1]) / v_m60.iloc[-1] <= 0.03, 
            v_m5.iloc[-1] > v_m5.iloc[-2],                                
            df['收盘'].iloc[-1] > ma25.iloc[-1]
        ]
        return all(cond)
    except: return False

def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "1"

    if arg == "summary":
        all_hits = []
        for f_name in ["hits_part1.json", "hits_part2.json"]:
            if os.path.exists(f_name):
                try:
                    with open(f_name, "r", encoding="utf-8") as f:
                        all_hits += json.load(f)
                except Exception as e:
                    print(f"读取文件失败 {f_name}: {e}")
        
        if not all_hits:
            send_wechat(f"🏁 1200只全扫描完毕 ({VERSION})\n今日无周线信号。")
            return

        hit_map = defaultdict(list)
        for h in all_hits:
            hit_map[h['ind']].append(f"{h['name']}({h['code']})")
        
        summary_text = ""
        for ind, names in hit_map.items():
            summary_text += f"🔥 [{ind}]: {', '.join(names)}\n"

        ai_msg = "\n📊 顶级量化分析师评分 (Top 5):\n"
        
        # --- 核心排查逻辑 ---
        if not GEMINI_KEY:
            ai_msg += "❌ 错误：未检测到 GEMINI_API_KEY 环境变量！"
        else:
            try:
                genai.configure(api_key=GEMINI_KEY)
                model = genai.GenerativeModel('gemini-1.5-flash')
                
                final_top = sorted(all_hits, key=lambda x: x['amount'], reverse=True)[:5]
                
                for item in final_top:
                    try:
                        prompt = (f"你现在是顶级量化分析师。点评A股{item['name']}({item['ind']})，现价{item['price']}元。"
                                  f"周线量能粘合。请给出【星级(1-5星)】及25字内专业点评。"
                                  f"要求：必须给1-2个5星标杆，其余1-4星客观分布。")
                        
                        # 增加超时控制
                        response = model.generate_content(prompt)
                        
                        # 安全提取文本：Gemini 响应有时会因安全策略没有 text 字段
                        if response and hasattr(response, 'text') and response.text:
                            ai_msg += f"⭐ {item['name']}: {response.text.strip()}\n"
                        else:
                            ai_msg += f"⭐ {item['name']}: [AI回复内容为空或被拦截]\n"
                        
                        time.sleep(1.5) # 给 API 一点喘息时间
                    except Exception as sub_e:
                        ai_msg += f"⭐ {item['name']}: [调用报错: {str(sub_e)[:30]}]\n"
            except Exception as e:
                ai_msg += f"❌ AI 初始化总线错误: {str(e)[:50]}"

        # 最终发送，确保内容完整
        send_wechat(f"🏁 1200只全汇总 ({VERSION})\n---\n{summary_text}{ai_msg}")
        return

    # 扫描逻辑 (保持不变)
    part = int(arg)
    scan_info = "前 600 只" if part == 1 else "后 601-1200 只"
    send_wechat(f"🚀 个股扫描 Part {part} 已启动...\n(范围：成交额 {scan_info})")
    
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

    with open(f"hits_part{part}.json", "w", encoding="utf-8") as f:
        json.dump(current_hits, f)

if __name__ == "__main__":
    main()
