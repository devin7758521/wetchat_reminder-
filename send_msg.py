import pandas as pd
import requests
import akshare as ak
import warnings
import os
import time
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")

# ===================== 配置信息 =====================
WEBHOOK_KEY = os.getenv("WEBHOOK_KEY", "da748662-f3d1-4edd-8031-2ee05c428605")
WEBHOOK_URL = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEBHOOK_KEY}"

def beijing_time():
    return (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")

def send_wechat(content):
    try:
        # 企业微信消息长度限制约 2048 字节
        if len(content) > 2000:
            content = content[:1900] + "\n...(内容过长已截断)"
        data = {"msgtype": "text", "text": {"content": content}}
        requests.post(WEBHOOK_URL, json=data, timeout=15)
    except:
        pass

# ===================== 核心：严格过滤主板 =====================
def get_strictly_main_board():
    """获取纯净的主板股票池"""
    try:
        df = ak.stock_zh_a_spot_em()
        code_col = [c for c in df.columns if '代码' in c][0]
        name_col = [c for c in df.columns if '名称' in c][0]
        vol_col = [c for c in df.columns if '成交量' in c][0]
        
        # 1. 格式化代码
        df[code_col] = df[code_col].astype(str).str.zfill(6)
        
        # 2. 编写严格过滤条件
        # 仅保留 60 (沪市主板) 和 00 (深市主板)
        # 排除所有含有 ST 的名称
        # 排除成交量为 0 的停牌股
        main_mask = (
            (df[code_col].str.startswith(('60', '00'))) & 
            (~df[name_col].str.contains("ST|\\*ST", na=False)) &
            (df[vol_col] > 0)
        )
        
        res = df[main_mask][[code_col, name_col]].copy()
        res.columns = ["code", "name"]
        return res
    except Exception as e:
        print(f"获取列表失败: {e}")
        return pd.DataFrame()

# ===================== 均量线逻辑 =====================
def check_strategy(code):
    """5/60日均量粘合向上逻辑"""
    try:
        # 使用 hist 接口获取最近 70 天数据，性能较好
        df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="hfq")
        
        if df is None or len(df) < 60:
            return False

        # 计算均量线
        v_series = df['成交量']
        v_m5 = v_series.rolling(5).mean()
        v_m60 = v_series.rolling(60).mean()

        last_v5 = v_m5.iloc[-1]
        last_v60 = v_m60.iloc[-1]
        prev_v5 = v_m5.iloc[-2]
        pprev_v5 = v_m5.iloc[-3]

        if last_v60 <= 0: return False

        # 条件 A: 5日与60日均量粘合 (相差3%以内)
        cond_bind = abs(last_v5 - last_v60) / last_v60 <= 0.03
        # 条件 B: 5日均量趋势向上 (连续两日增长)
        cond_up = last_v5 > prev_v5 > pprev_v5
        
        return True if (cond_bind and cond_up) else False
    except:
        return False

# ===================== 主程序 =====================
def main():
    start_time = time.time()
    now_str = beijing_time()
    print(f"🚀 开始主板全量扫描: {now_str}")
    
    stocks = get_strictly_main_board()
    if stocks.empty:
        print("❌ 未获取到主板股票名单")
        return

    total = len(stocks)
    print(f"📊 已锁定主板 A 股共 {total} 只，开始分析量能...")
    
    hit_list = []
    
    # 全量扫描循环
    for i, (_, row) in enumerate(stocks.iterrows()):
        code, name = row["code"], row["name"]
        
        if check_strategy(code):
            hit_list.append(f"{code} {name}")
            print(f"🎯 命中: {code} {name}")
        
        # --- 节奏控制，防止被封 IP ---
        # 每扫描 30 只休息 0.5 秒，每扫描 100 只额外休息 1 秒
        if (i + 1) % 100 == 0:
            print(f"进度: {i+1}/{total}...")
            time.sleep(1.5)
        elif (i + 1) % 30 == 0:
            time.sleep(0.5)

    # 结果推送
    duration = int(time.time() - start_time)
    msg = f"【选股机器人 - 主板量能】\n"
    msg += f"时间：{now_str}\n"
    msg += f"逻辑：主板+5/60日均量粘合向上\n"
    msg += f"----------------------------\n"
    
    if hit_list:
        msg += f"🔥 命中({len(hit_list)}只)：\n" + "\n".join(hit_list)
    else:
        msg += "✅ 扫描完成，今日无符合条件的股票"
    
    msg += f"\n----------------------------\n总量: {total}只 | 耗时: {duration}s"
    
    print(msg)
    send_wechat(msg)

if __name__ == "__main__":
    main()
