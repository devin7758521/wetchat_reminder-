import pandas as pd
import requests
import akshare as ak
import warnings
import os
import time
import random
from datetime import datetime, timedelta

# 屏蔽不必要的告警
warnings.filterwarnings("ignore")

# ===================== 配置信息 (已硬编码) =====================
WEBHOOK_KEY = "da748662-f3d1-4edd-8031-2ee05c428605"
WEBHOOK_URL = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEBHOOK_KEY}"

def beijing_time():
    """转换 UTC 为北京时间"""
    return (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")

def send_wechat(content):
    """发送推送至企业微信机器人"""
    try:
        if len(content) > 2000:
            content = content[:1900] + "\n...(内容过长已截断)"
        data = {"msgtype": "text", "text": {"content": content}}
        requests.post(WEBHOOK_URL, json=data, timeout=15)
    except Exception as e:
        print(f"微信推送异常: {e}")

# ===================== 核心：多路冗余获取名单 =====================
def get_strictly_main_board():
    """确保在海外服务器也能 100% 拿到主板名单"""
    sources = [
        ("EastMoney_Spot", lambda: ak.stock_zh_a_spot_em()),
        ("A_Code_Name", lambda: ak.stock_info_a_code_name()),
        ("A_All_Safe", lambda: ak.stock_zh_a_s_all_safe())
    ]
    
    for name, func in sources:
        try:
            print(f"📡 尝试数据源: {name}...")
            df = func()
            if df is None or df.empty:
                continue
                
            if '代码' in df.columns: df.rename(columns={'代码': 'code'}, inplace=True)
            if '名称' in df.columns: df.rename(columns={'名称': 'name'}, inplace=True)
            if 'symbol' in df.columns: df.rename(columns={'symbol': 'code'}, inplace=True)

            df['code'] = df['code'].astype(str).str.zfill(6)
            
            mask = (
                (df['code'].str.startswith(('60', '00'))) & 
                (~df['name'].astype(str).str.contains("ST|\\*ST", na=False))
            )
            res = df[mask][['code', 'name']].copy()
            
            if not res.empty:
                print(f"✅ {name} 抓取成功，共 {len(res)} 只个股")
                return res
        except Exception as e:
            print(f"❌ {name} 接口暂时不可用: {e}")
            continue
            
    return pd.DataFrame()

# ===================== 策略逻辑：均量线粘合 (周K级别) =====================
def check_strategy(code, retries=2):
    """带重试机制的 5/60周均量线粘合向上策略"""
    for _ in range(retries):
        try:
            time.sleep(random.uniform(0.1, 0.3))
            # 周线级别需要回溯更长时间以确保有足够的周K线数据 (约2年)
            start_dt = (datetime.now() - timedelta(days=730)).strftime("%Y%m%d")
            
            # 【修改点：period="daily" 改为 period="weekly"】
            df = ak.stock_zh_a_hist(symbol=code, period="weekly", start_date=start_dt, adjust="hfq")
            
            if df is None or len(df) < 65:
                return False

            v_col = [c for c in df.columns if '成交量' in c][0]
            v_series = df[v_col].astype(float)
            
            # 计算 5周均量 和 60周均量
            v_m5 = v_series.rolling(5).mean()
            v_m60 = v_series.rolling(60).mean()

            last_v5, prev_v5, pprev_v5 = v_m5.iloc[-1], v_m5.iloc[-2], v_m5.iloc[-3]
            last_v60 = v_m60.iloc[-1]

            if last_v60 <= 0: return False

            # 原有逻辑：粘合 (3%偏差) 且 5线趋势向上
            cond_bind = abs(last_v5 - last_v60) / last_v60 <= 0.03
            cond_up = last_v5 > prev_v5 > pprev_v5
            
            return cond_bind and cond_up
        except:
            time.sleep(1)
            continue
    return False

# ===================== 主流程 =====================
def main():
    start_ts = time.time()
    now_str = beijing_time()
    
    # 【保留：启动通知】
    send_wechat(f"🚀 [选股机器人] 开始扫盘\n启动时间: {now_str}\n级别: 周K\n正在获取名单...")
    
    print(f"🚀 [选股 Bot] 启动扫描 (周K级别): {now_str}")
    
    stocks = get_strictly_main_board()
    if stocks.empty:
        send_wechat(f"❌ 警告: 无法获取个股列表，请检查网络！")
        return

    total = len(stocks)
    hit_list = []
    
    for i, (_, row) in enumerate(stocks.iterrows()):
        code, name = row["code"], row["name"]
        if check_strategy(code):
            hit_list.append(f"{code} {name}")
            print(f"🎯 命中: {code} {name}")
        
        if (i + 1) % 200 == 0:
            print(f"进度: {i+1}/{total} (耗时: {int(time.time()-start_ts)}s)")

    duration = int(time.time() - start_ts)
    msg = f"【选股机器人 - 周K报告】\n"
    msg += f"结束时间: {beijing_time()}\n"
    msg += f"----------------------------\n"
    
    if hit_list:
        msg += f"🔥 均量线信号 ({len(hit_list)} 只):\n" + "\n".join(hit_list)
    else:
        msg += "✅ 扫描完成，今日周K无信号。"
    
    msg += f"\n----------------------------\n扫描总数: {total} | 耗时: {duration}s"
    
    print(msg)
    send_wechat(msg)

if __name__ == "__main__":
    main()
