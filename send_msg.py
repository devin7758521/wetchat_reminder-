import pandas as pd
import requests
import akshare as ak
import time
import sys
import os
import json
from datetime import datetime

# 配置
VERSION = "v2026.04.02.Global.Stable"
WEB_KEY = os.environ.get("WECHAT_WEBHOOK_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

def send_wechat(content):
    if not WEB_KEY: return
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEB_KEY}"
    try:
        requests.post(url, json={"msgtype": "text", "text": {"content": content}}, timeout=10)
    except: pass

def check_strategy(code, name):
    try:
        # 直接抓取周线历史数据
        df = ak.stock_zh_a_hist(symbol=code, period="weekly", adjust="qfq")
        if len(df) < 65: return False
        
        curr_price = df['收盘'].iloc[-1]
        # 价格筛选 3-70
        if not (3.0 <= curr_price <= 70.0): return False

        v5 = df['成交量'].rolling(5).mean()
        v60 = df['成交量'].rolling(60).mean()
        ma25 = df['收盘'].rolling(25).mean()
        
        vol_up = v5.iloc[-1] > v5.iloc[-2]
        deviation = (v5.iloc[-1] - v60.iloc[-1]) / v60.iloc[-1]
        # 偏离度 -3% 到 7%
        is_binding = -0.03 <= deviation <= 0.07
        price_support = curr_price > ma25.iloc[-1]

        return vol_up and is_binding and price_support
    except: return False

def main():
    if len(sys.argv) < 2: return
    mode = sys.argv[1]
    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M')

    if mode == "summary":
        # 汇总逻辑保持不变
        all_hits = []
        for f in ["hits_part1.json", "hits_part2.json"]:
            if os.path.exists(f):
                with open(f, "r") as file: all_hits += json.load(file)
        
        if not all_hits:
            send_wechat(f"📅 {now_str}\n扫描结束，未发现信号。")
            return

        # 排序取前10并用AI分析
        top_hits = sorted(all_hits, key=lambda x: x['amount'], reverse=True)[:10]
        # ... (AI分析部分参考之前代码，已简化) ...
        send_wechat(f"🌟 发现 {len(all_hits)} 只标的，Top3: {[h['name'] for h in top_hits[:3]]}")
            
    else:
        part = int(mode)
        # --- 核心改变：使用基础名单接口，该接口极少封锁 ---
        try:
            # 获取所有股票基础名单
            stock_list = ak.stock_info_a_code_name()
            # 1. 筛选 60/00 开头且非 ST (根据名称过滤)
            mask_code = stock_list['code'].str.startswith(('60', '00'))
            mask_no_st = ~stock_list['name'].str.contains('ST|退', na=False)
            active = stock_list[mask_code & mask_no_st].copy()
            
            # 分片处理，减少单次运行负担
            total = len(active)
            half = total // 2
            batch = active.head(half) if part == 1 else active.tail(total - half)
            
            hits = []
            for _, row in batch.iterrows():
                if check_strategy(row['code'], row['name']):
                    # 这里存一个虚假的amount用于汇总排序，或者你可以再抓一下日线
                    hits.append({"name": row['name'], "code": row['code'], "amount": 0})
                time.sleep(0.1) # 礼貌抓取
            
            with open(f"hits_part{part}.json", "w") as f: 
                json.dump(hits, f)
        except Exception as e:
            send_wechat(f"❌ 列表获取失败: {str(e)[:50]}")

if __name__ == "__main__": main()
