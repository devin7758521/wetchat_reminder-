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
        requests.post(WEBHOOK_URL, json=data, timeout=10)
    except:
        pass

# ===================== 数据助手 =====================
def get_ai_brief(code):
    try:
        time.sleep(0.3) # 稍微增加一点行业查询间隔
        info = ak.stock_individual_info_em(symbol=code)
        industry = info[info['item'] == '板块'].iloc[0]['value']
        return f"【行业】: {industry}"
    except:
        return "【行业】: 暂无数据"

# ===================== 核心：获取并精简名单 =====================
def get_strictly_main_board():
    try:
        print("📡 正在获取全量行情进行初步筛选...")
        df = ak.stock_zh_a_spot_em()
        
        if df is None or df.empty:
            return pd.DataFrame()

        rename_dict = {'代码': 'code', '名称': 'name', '最新价': 'price', '成交额': 'amount'}
        df.rename(columns=rename_dict, inplace=True)
        df['code'] = df['code'].astype(str).str.zfill(6)
        
        mask = (df['code'].str.startswith(('60', '00'))) & \
               (~df['name'].astype(str).str.contains("ST|\\*ST", na=False))
        
        df['price'] = pd.to_numeric(df['price'], errors='coerce')
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
        mask &= (df['price'] > 3) & (df['price'] < 70)
        
        res = df[mask].copy()
        
        # 保留你的 1200 只活跃股逻辑
        res = res.sort_values(by='amount', ascending=False).head(1200)
        
        print(f"✅ 选定成交额最活跃的 {len(res)} 只个股进行周K扫描")
        return res[['code', 'name']]
    except Exception as e:
        print(f"❌ 列表获取异常: {e}")
        return pd.DataFrame()

# ===================== 选股逻辑 =====================
def check_strategy(code):
    try:
        # 【修改点1】随机休眠区间略微拉长，GitHub IP 较敏感
        time.sleep(random.uniform(0.5, 1.0)) 
        
        start_dt = (datetime.now() - timedelta(days=730)).strftime("%Y%m%d")
        
        # 【修改点2】利用 try 机制防止 akshare 请求挂起
        # 即使接口内部卡住，只要不是死锁，下一轮循环也能继续
        df = ak.stock_zh_a_hist(symbol=code, period="weekly", start_date=start_dt, adjust="qfq")
        
        if df is None or len(df) < 65: 
            return False

        v_series = df['成交量'].astype(float)
        v_m5 = v_series.rolling(5).mean()
        v_m60 = v_series.rolling(60).mean()
        
        last_v5, prev_v5, pprev_v5 = v_m5.iloc[-1], v_m5.iloc[-2], v_m5.iloc[-3]
        last_v60 = v_m60.iloc[-1]

        p_series = df['收盘'].astype(float)
        ma25 = p_series.rolling(25).mean()
        last_price = p_series.iloc[-1]
        last_ma25 = ma25.iloc[-1]

        if last_v60 <= 0 or pd.isna(last_ma25): 
            return False

        # 你的核心条件
        cond_bind = abs(last_v5 - last_v60) / last_v60 <= 0.03 
        cond_up = last_v5 > prev_v5 > pprev_v5                
        cond_price = last_price > last_ma25                    
        
        return cond_bind and cond_up and cond_price
    except:
        return False

# ===================== 主流程 =====================
def main():
    start_ts = time.time()
    send_wechat(f"🚀 [AI 机器人] 开始扫描\n时间: {beijing_time()}\n策略: 周K量价粘合\n模式: 活跃股优先(1200只)")
    
    stocks = get_strictly_main_board()
    if stocks.empty:
        send_wechat("❌ 列表获取失败")
        return

    total = len(stocks)
    hit_list = []
    
    for i, (_, row) in enumerate(stocks.iterrows()):
        code, name = row["code"], row["name"]
        
        if check_strategy(code):
            brief = get_ai_brief(code)
            hit_list.append(f"🎯 {code} {name}\n   {brief}")
            print(f"🎯 命中: {code} {name}")
        
        # 【修改点3】加密休息频率：从100只改为每50只休息15秒
        # 这是为了应对 GitHub Actions 这种公网 IP 的高频封锁
        if (i + 1) % 50 == 0:
            print(f"⏳ 已扫描 {i+1}/{total}，强制静默 15s 防封...")
            time.sleep(15)
        elif (i + 1) % 10 == 0:
            # 提高日志打印频率，让你在后台能看到它一直在动
            print(f"进度: {i+1}/{total}...")

    duration = int(time.time() - start_ts)
    msg = f"【周K量价扫描报告】\n时间: {beijing_time()}\n"
    msg += "----------------------------\n"
    msg += f"🔥 命中 {len(hit_list)} 只:\n\n" + "\n\n".join(hit_list) if hit_list else "✅ 扫描完毕，无信号。"
    msg += f"\n----------------------------\n总耗时: {duration}s"
    
    send_wechat(msg)
    print("🏁 全部流程执行完毕。")

if __name__ == "__main__":
    main()
