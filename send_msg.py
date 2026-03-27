import pandas as pd
import requests
import akshare as ak
import warnings
import os
import time
import random
from datetime import datetime, timedelta

# 屏蔽告警
warnings.filterwarnings("ignore")

# ===================== 配置信息 =====================
WEBHOOK_KEY = "da748662-f3d1-4edd-8031-2ee05c428605"
WEBHOOK_URL = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEBHOOK_KEY}"

def beijing_time():
    return (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")

def send_wechat(content):
    """发送推送至企业微信"""
    try:
        data = {"msgtype": "text", "text": {"content": content}}
        print(f"📡 尝试推送微信... 目标Key后四位: {WEBHOOK_KEY[-4:]}")
        response = requests.post(WEBHOOK_URL, json=data, timeout=15)
        print(f"📡 微信回执: {response.status_code} | 响应内容: {response.text}")
        if response.status_code == 200 and '"errcode":0' in response.text:
            print("✅ 微信推送成功！")
        else:
            print("❌ 微信推送可能失败")
    except Exception as e:
        print(f"❌ 微信推送执行异常: {e}")

# ===================== AI 数据助手 =====================
def get_ai_brief(code):
    try:
        info = ak.stock_individual_info_em(symbol=code)
        industry = info[info['item'] == '板块'].iloc[0]['value']
        return f"【行业】: {industry}"
    except:
        return "【行业】: 暂无数据"

# ===================== 核心：多路冗余获取名单 + 动态过滤 =====================
def get_strictly_main_board():
    """获取名单并过滤：主板、非ST、成交额>6000W、价格>3元"""
    base_df = pd.DataFrame()
    # 保持你原始代码的三路冗余机制
    sources = [
        ("EastMoney", lambda: ak.stock_zh_a_spot_em()),
        ("A_Code_Name", lambda: ak.stock_info_a_code_name()),
        ("A_All_Safe", lambda: ak.stock_zh_a_s_all_safe())
    ]
    
    for name, func in sources:
        try:
            print(f"📡 尝试获取名单源: {name}...")
            df = func()
            if df is not None and not df.empty:
                base_df = df
                print(f"✅ 成功从 {name} 获取原始数据")
                break
        except:
            continue
            
    if base_df.empty:
        return pd.DataFrame()

    # 标准化基础字段
    if '代码' in base_df.columns: base_df.rename(columns={'代码': 'code'}, inplace=True)
    if '名称' in base_df.columns: base_df.rename(columns={'名称': 'name'}, inplace=True)
    base_df['code'] = base_df['code'].astype(str).str.zfill(6)

    # --- 新增：成交额与价格过滤逻辑 ---
    try:
        # 获取实时行情快照（用于过滤金额和价格）
        snapshot = ak.stock_zh_a_spot_em()[['代码', '最新价', '成交额']]
        snapshot.columns = ['code', 'price', 'amount']
        snapshot['code'] = snapshot['code'].astype(str).str.zfill(6)
        
        # 合并基础名单与行情数据
        merged = pd.merge(base_df, snapshot, on='code', how='inner')
        
        # 过滤条件：主板(60/00) + 非ST + 价格>3 + 成交额>6000万
        mask = (
            (merged['code'].str.startswith(('60', '00'))) & 
            (~merged['name'].astype(str).str.contains("ST|\\*ST", na=False)) &
            (merged['price'].astype(float) > 3.0) &
            (merged['amount'].astype(float) > 60000000)
        )
        res = merged[mask][['code', 'name']].copy()
        print(f"🎯 最终过滤后待扫描个股: {len(res)} 只")
        return res
    except Exception as e:
        print(f"⚠️ 行情过滤插件异常: {e}，将回退至基础过滤模式")
        # 兜底：如果行情数据获取失败，则仅按原逻辑过滤主板和ST
        mask = (base_df['code'].str.startswith(('60', '00'))) & (~base_df['name'].astype(str).str.contains("ST|\\*ST", na=False))
        return base_df[mask][['code', 'name']].copy()

# ===================== 选股逻辑：周K + 均量粘合 + 股价 > MA25 =====================
def check_strategy(code, retries=2):
    for _ in range(retries):
        try:
            time.sleep(random.uniform(0.1, 0.3))
            start_dt = (datetime.now() - timedelta(days=730)).strftime("%Y%m%d")
            
            # 保持 qfq 前复权
            df = ak.stock_zh_a_hist(symbol=code, period="weekly", start_date=start_dt, adjust="qfq")
            
            if df is None or len(df) < 65: return False

            # --- 1. 成交量逻辑 ---
            v_col = [c for c in df.columns if '成交量' in c][0]
            v_series = df[v_col].astype(float)
            v_m5 = v_series.rolling(5).mean()
            v_m60 = v_series.rolling(60).mean()
            last_v5, prev_v5, pprev_v5 = v_m5.iloc[-1], v_m5.iloc[-2], v_m5.iloc[-3]
            last_v60 = v_m60.iloc[-1]

            # --- 2. 价格逻辑 (MA25) ---
            p_series = df['收盘'].astype(float)
            ma25 = p_series.rolling(25).mean()
            last_price = p_series.iloc[-1]
            last_ma25 = ma25.iloc[-1]

            if last_v60 <= 0 or pd.isna(last_ma25): return False

            # --- 3. 核心条件判定 ---
            cond_bind = abs(last_v5 - last_v60) / last_v60 <= 0.03 # 3% 粘合
            cond_up = last_v5 > prev_v5 > pprev_v5               # 5日量连增
            cond_price = last_price > last_ma25                  # 股价 > 25周线
            
            return cond_bind and cond_up and cond_price
        except:
            time.sleep(0.5)
            continue
    return False

# ===================== 主流程 =====================
def main():
    start_ts = time.time()
    now_str = beijing_time()
    
    send_wechat(f"🚀 [AI 选股机器人] 周K级别扫描开始\n时间: {now_str}\n逻辑: 均量粘合 + 站稳MA25\n初筛: 价格>3 & 成交额>6000W")
    
    print(f"🚀 [选股 Bot] 启动扫描: {now_str}")
    
    stocks = get_strictly_main_board()
    if stocks.empty:
        send_wechat("❌ 无法获取个股列表，请检查网络！")
        return

    total = len(stocks)
    hit_list = []
    
    for i, (_, row) in enumerate(stocks.iterrows()):
        code, name = row["code"], row["name"]
        if check_strategy(code):
            brief = get_ai_brief(code)
            hit_list.append(f"📌 {code} {name}\n{brief}")
            print(f"🎯 命中: {code} {name}")
        
        if (i + 1) % 200 == 0:
            print(f"进度: {i+1}/{total} (耗时: {int(time.time()-start_ts)}s)")

    duration = int(time.time() - start_ts)
    msg = f"【周K量价研报报告】\n时间: {beijing_time()}\n"
    msg += f"----------------------------\n"
    
    if hit_list:
        msg += f"🔥 信号命中 ({len(hit_list)}只):\n\n" + "\n\n".join(hit_list)
    else:
        msg += "✅ 扫描完毕，当前周K级别无符合信号。"
    
    msg += f"\n----------------------------\n总扫描: {total} | 总耗时: {duration}s"
    
    print(msg)
    send_wechat(msg)
    print("🏁 全部流程执行完毕。")

if __name__ == "__main__":
    main()
