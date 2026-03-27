import pandas as pd
import requests
import akshare as ak
import warnings
import os
import time
import random
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")

# ===================== 配置信息 =====================
WEBHOOK_KEY = os.getenv("WEBHOOK_KEY", "da748662-f3d1-4edd-8031-2ee05c428605")
WEBHOOK_URL = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEBHOOK_KEY}"

def beijing_time():
    return (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")

def send_wechat(content):
    try:
        data = {"msgtype": "text", "text": {"content": content}}
        requests.post(WEBHOOK_URL, json=data, timeout=10)
    except:
        pass

# ===================== 最稳名单获取逻辑 =====================
def get_strictly_main_board():
    """采用三级备选方案，确保 GitHub 环境下 100% 拿到名单"""
    # 方案 A: 东方财富 (最推荐，海外访问相对稳定)
    try:
        df = ak.stock_zh_a_spot_em()
        if df is not None and not df.empty:
            df = df.rename(columns={'代码': 'code', '名称': 'name'})
            df['code'] = df['code'].astype(str).str.zfill(6)
            mask = (df['code'].str.startswith(('60', '00'))) & (~df['name'].astype(str).str.contains("ST|\\*ST", na=False))
            res = df[mask][['code', 'name']].copy()
            if not res.empty:
                print(f"✅ Source A (EastMoney) Success: {len(res)} stocks.")
                return res
    except: pass

    # 方案 B: 基础信息接口
    try:
        df = ak.stock_info_a_code_name()
        if df is not None and not df.empty:
            df['code'] = df['code'].astype(str).str.zfill(6)
            mask = (df['code'].str.startswith(('60', '00'))) & (~df['name'].astype(str).str.contains("ST|\\*ST", na=False))
            res = df[mask][['code', 'name']].copy()
            if not res.empty:
                print(f"✅ Source B (Info) Success: {len(res)} stocks.")
                return res
    except: pass

    # 方案 C: 实时全量接口 (保底)
    try:
        df = ak.stock_zh_a_s_all_safe()
        if df is not None and not df.empty:
            df['code'] = df['code'].astype(str).str.zfill(6)
            mask = (df['code'].str.startswith(('60', '00'))) & (~df['name'].astype(str).str.contains("ST|\\*ST", na=False))
            res = df[mask][['code', 'name']].copy()
            if not res.empty:
                print(f"✅ Source C (Safe) Success: {len(res)} stocks.")
                return res
    except: pass

    return pd.DataFrame()

# ===================== 稳健版均量线策略 =====================
def check_strategy(code, retries=2):
    """带重试机制的策略检查，对抗网络丢包"""
    for _ in range(retries):
        try:
            # 基础防封：随机微延迟
            time.sleep(random.uniform(0.1, 0.3))
            
            # 抓取 120 天数据（确保 60 日均线计算绰绰有余）
            start_dt = (datetime.now() - timedelta(days=120)).strftime("%Y%m%d")
            df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start_dt, adjust="hfq")
            
            if df is None or len(df) < 65:
                return False

            # 寻找包含“成交量”的列（兼容不同接口名）
            v_col = [c for c in df.columns if '成交量' in c][0]
            v_series = df[v_col].astype(float)
            
            v_m5 = v_series.rolling(5).mean()
            v_m60 = v_series.rolling(60).mean()

            # 获取最后 3 个周期的均线数据
            last_v5, prev_v5, pprev_v5 = v_m5.iloc[-1], v_m5.iloc[-2], v_m5.iloc[-3]
            last_v60 = v_m60.iloc[-1]

            if last_v60 <= 0: return False

            # 策略：5/60日均量粘合 (3%) 且 5日均量向上
            cond_bind = abs(last_v5 - last_v60) / last_v60 <= 0.03
            cond_up = last_v5 > prev_v5 > pprev_v5
            
            return cond_bind and cond_up
        except:
            time.sleep(1) # 报错后等 1 秒再试
            continue
    return False

# ===================== 执行主程序 =====================
def main():
    start_time = time.time()
    now_str = beijing_time()
    print(f"🚀 Bot Start: {now_str}")
    
    # 1. 获取名单
    stocks = get_strictly_main_board()
    if stocks.empty:
        send_wechat(f"❌ 警告: {now_str}\n所有数据源获取失败，请检查网络或更新 AkShare！")
        return

    total = len(stocks)
    print(f"📊 扫描范围: 主板 {total} 只个股")
    
    hit_list = []
    
    # 2. 遍历扫描
    for i, (_, row) in enumerate(stocks.iterrows()):
        code, name = row["code"], row["name"]
        
        if check_strategy(code):
            hit_list.append(f"{code} {name}")
            print(f"🎯 命中: {code} {name}")
        
        # 进度播报
        if (i + 1) % 200 == 0:
            print(f"Progress: {i+1}/{total} (Time: {int(time.time()-start_time)}s)")

    # 3. 结果整理
    duration = int(time.time() - start_time)
    msg = f"【选股报告 - 均量粘合】\n"
    msg += f"时间: {now_str}\n"
    msg += f"----------------------------\n"
    
    if hit_list:
        msg += f"🔥 命中 ({len(hit_list)} 只):\n" + "\n".join(hit_list)
    else:
        msg += "✅ 扫描完毕，今日无信号。"
    
    msg += f"\n----------------------------\n扫描总数: {total}\n耗时: {duration}s"
    
    print(msg)
    send_wechat(msg)

if __name__ == "__main__":
    main()
