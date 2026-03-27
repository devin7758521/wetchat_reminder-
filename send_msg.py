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

# ===================== 配置信息 =====================
WEBHOOK_KEY = "da748662-f3d1-4edd-8031-2ee05c428605"
WEBHOOK_URL = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEBHOOK_KEY}"

def beijing_time():
    return (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")

def send_wechat(content):
    try:
        data = {"msgtype": "text", "text": {"content": content}}
        requests.post(WEBHOOK_URL, json=data, timeout=15)
    except:
        pass

# ===================== AI 研报数据助手 =====================
def get_ai_brief(code):
    """获取个股基本面简报，辅助决策"""
    try:
        # 1. 获取个股基本信息（行业、主营）
        info = ak.stock_individual_info_em(symbol=code)
        industry = info[info['item'] == '板块'].iloc[0]['value']
        
        # 2. 获取实时估值指标
        spot = ak.stock_zh_a_spot_em()
        row = spot[spot['代码'] == code].iloc[0]
        pe = row['市盈率-动态']
        pb = row['市净率']
        
        return f"【行业】: {industry}\n【估值】: PE {pe} / PB {pb}"
    except:
        return "【基本面】: 暂无数据"

# ===================== 核心名单获取 =====================
def get_strictly_main_board():
    sources = [
        ("EastMoney", lambda: ak.stock_zh_a_spot_em()),
        ("A_Code_Name", lambda: ak.stock_info_a_code_name())
    ]
    for name, func in sources:
        try:
            df = func()
            if df is None or df.empty: continue
            if '代码' in df.columns: df.rename(columns={'代码': 'code'}, inplace=True)
            if '名称' in df.columns: df.rename(columns={'名称': 'name'}, inplace=True)
            df['code'] = df['code'].astype(str).str.zfill(6)
            mask = (df['code'].str.startswith(('60', '00'))) & (~df['name'].astype(str).str.contains("ST|\\*ST", na=False))
            return df[mask][['code', 'name']].copy()
        except: continue
    return pd.DataFrame()

# ===================== 选股逻辑：周K均量粘合 + 站稳MA25 =====================
def check_strategy(code, retries=2):
    for _ in range(retries):
        try:
            time.sleep(random.uniform(0.1, 0.3))
            # 抓取 2 年数据，确保 60 周线计算准确
            start_dt = (datetime.now() - timedelta(days=730)).strftime("%Y%m%d")
            df = ak.stock_zh_a_hist(symbol=code, period="weekly", start_date=start_dt, adjust="qfq")
            
            if df is None or len(df) < 65: return False

            # --- 1. 成交量均线计算 ---
            v_col = [c for c in df.columns if '成交量' in c][0]
            v_series = df[v_col].astype(float)
            v_m5 = v_series.rolling(5).mean()
            v_m60 = v_series.rolling(60).mean()

            last_v5, prev_v5, pprev_v5 = v_m5.iloc[-1], v_m5.iloc[-2], v_m5.iloc[-3]
            last_v60 = v_m60.iloc[-1]

            # --- 2. 价格均线计算 (MA25) ---
            p_col = '收盘'
            p_series = df[p_col].astype(float)
            ma25 = p_series.rolling(25).mean()
            last_price = p_series.iloc[-1]
            last_ma25 = ma25.iloc[-1]

            if last_v60 <= 0 or pd.isna(last_ma25): return False

            # --- 3. 核心条件判定 ---
            # 条件 A: 周均量粘合 (3%以内)
            cond_bind = abs(last_v5 - last_v60) / last_v60 <= 0.03
            # 条件 B: 5周均量连续两周期向上
            cond_up = last_v5 > prev_v5 > pprev_v5
            # 条件 C: 最新价站稳 25周线 (MA25)
            cond_price = last_price > last_ma25
            
            return cond_bind and cond_up and cond_price
        except:
            time.sleep(1)
            continue
    return False

# ===================== 主流程 =====================
def main():
    start_ts = time.time()
    now_str = beijing_time()
    send_wechat(f"🚀 [AI 选股助手] 周K级别扫描启动\n时间: {now_str}\n策略: 均量粘合 + 站上25周线")
    
    stocks = get_strictly_main_board()
    if stocks.empty: return

    hit_list = []
    total = len(stocks)
    
    for i, (_, row) in enumerate(stocks.iterrows()):
        code, name = row["code"], row["name"]
        if check_strategy(code):
            # 命中后，立即生成研报简讯
            brief = get_ai_brief(code)
            hit_list.append(f"📌 {code} {name}\n{brief}")
            print(f"🎯 命中: {code} {name}")
        
        if (i + 1) % 200 == 0:
            print(f"进度: {i+1}/{total} (耗时: {int(time.time()-start_ts)}s)")

    duration = int(time.time() - start_ts)
    msg = f"【周K量价研报报告】\n"
    msg += f"生成时间: {beijing_time()}\n"
    msg += f"----------------------------\n"
    
    if hit_list:
        msg += "🔥 信号命中 (已通过MA25过滤):\n\n" + "\n\n".join(hit_list)
    else:
        msg += "✅ 扫描完毕，当前周K级别无符合信号。"
    
    msg += f"\n----------------------------\n总扫描: {total} | 耗时: {duration}s"
    
    send_wechat(msg)

if __name__ == "__main__":
    main()
