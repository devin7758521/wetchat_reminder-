import pandas as pd
import requests
import akshare as ak
import warnings
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
    try:
        data = {"msgtype": "text", "text": {"content": content}}
        # 增加超时控制，防止推送环节卡死
        requests.post(WEBHOOK_URL, json=data, timeout=10)
    except:
        pass

# ===================== 核心：精简名单 (600只) =====================
def get_strictly_main_board():
    try:
        print("📡 正在获取全量行情进行初步筛选...")
        df = ak.stock_zh_a_spot_em()
        
        if df is None or df.empty:
            return pd.DataFrame()

        # 标准化列名
        rename_dict = {'代码': 'code', '名称': 'name', '最新价': 'price', '成交额': 'amount'}
        df.rename(columns=rename_dict, inplace=True)
        df['code'] = df['code'].astype(str).str.zfill(6)
        
        # 基础过滤：主板 + 非ST + 价格3-70
        mask = (df['code'].str.startswith(('60', '00'))) & \
               (~df['name'].astype(str).str.contains("ST|\\*ST", na=False))
        
        df['price'] = pd.to_numeric(df['price'], errors='coerce')
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
        mask &= (df['price'] > 3) & (df['price'] < 70)
        
        res = df[mask].copy()
        
        # 🔥 关键调整：为了 GitHub 稳定性，取成交额前 600 名
        res = res.sort_values(by='amount', ascending=False).head(600)
        
        print(f"✅ 已选定最活跃的 {len(res)} 只个股进行周K扫描")
        return res[['code', 'name']]
    except Exception as e:
        print(f"❌ 列表获取异常: {e}")
        return pd.DataFrame()

# ===================== 选股逻辑 (100%保留你的条件) =====================
def check_strategy(code):
    try:
        # 随机休眠，模拟真人节奏
        time.sleep(random.uniform(0.4, 0.8)) 
        
        start_dt = (datetime.now() - timedelta(days=730)).strftime("%Y%m%d")
        
        # 获取周K数据（前复权）
        df = ak.stock_zh_a_hist(symbol=code, period="weekly", start_date=start_dt, adjust="qfq")
        
        if df is None or df.empty or len(df) < 65: 
            return False

        # 1. 成交量逻辑
        v_series = df['成交量'].astype(float)
        v_m5 = v_series.rolling(5).mean()
        v_m60 = v_series.rolling(60).mean()
        
        last_v5, prev_v5, pprev_v5 = v_m5.iloc[-1], v_m5.iloc[-2], v_m5.iloc[-3]
        last_v60 = v_m60.iloc[-1]

        # 2. 价格逻辑 (MA25)
        p_series = df['收盘'].astype(float)
        ma25 = p_series.rolling(25).mean()
        last_price = p_series.iloc[-1]
        last_ma25 = ma25.iloc[-1]

        if last_v60 <= 0 or pd.isna(last_ma25): 
            return False

        # 你的核心判定条件
        cond_bind = abs(last_v5 - last_v60) / last_v60 <= 0.03 # 均量粘合
        cond_up = last_v5 > prev_v5 > pprev_v5                # 量能递增
        cond_price = last_price > last_ma25                    # 站稳25周线
        
        return cond_bind and cond_up and cond_price
    except:
        return False

# ===================== 主流程 =====================
def main():
    start_ts = time.time()
    send_wechat(f"🚀 [备用机器人] 扫描启动\n时间: {beijing_time()}\n模式: 极速抗封锁(600只)")
    
    stocks = get_strictly_main_board()
    if stocks.empty:
        send_wechat("❌ 列表获取失败，可能是IP被暂时封锁")
        return

    total = len(stocks)
    hit_list = []
    
    for i, (_, row) in enumerate(stocks.iterrows()):
        code, name = row["code"], row["name"]
        
        if check_strategy(code):
            # 命中后直接记录，不再二次查询行业，提高速度
            hit_list.append(f"🎯 {code} {name}")
            print(f"🎯 命中: {code} {name}")
        
        # 提高进度打印频率，每 10 只打印一次，让你在后台看着安心
        if (i + 1) % 10 == 0:
            print(f"进度: {i+1}/{total}...")

        # 每 30 只强制休息 3 秒，给服务器“降温”
        if (i + 1) % 30 == 0:
            time.sleep(3)

    # 汇报结果
    duration = int(time.time() - start_ts)
    msg = f"【备用周K量价报告】\n时间: {beijing_time()}\n"
    msg += "----------------------------\n"
    if hit_list:
        msg += f"🔥 共命中 {len(hit_list)} 只个股：\n\n" + "\n".join(hit_list)
    else:
        msg += "✅ 扫描完毕，当前无信号。"
    
    msg += f"\n----------------------------\n耗时: {duration}s | 范围: 前{total}名"
    
    send_wechat(msg)
    print("🏁 全部流程执行完毕。")

if __name__ == "__main__":
    main()
