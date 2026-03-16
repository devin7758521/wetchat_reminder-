import akshare as ak
import pandas as pd
import numpy as np
import requests
import socket
import time
import traceback

# =====================
# 基础配置（防崩+超时）
# =====================
socket.setdefaulttimeout(60)
time.sleep(3)
akshare_timeout = 30

# =====================
# 企业微信机器人（已填你的key）
# =====================
WECHAT_WEBHOOK_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=da748662-f3d1-4edd-8031-2ee05c428605"

def send_wechat_work_msg(content):
    """企业微信推送（加异常捕获）"""
    try:
        data = {
            "msgtype": "text",
            "text": {"content": content}
        }
        res = requests.post(WECHAT_WEBHOOK_URL, json=data, timeout=15)
        print(f"推送结果: {res.status_code}")
    except Exception as e:
        print(f"推送失败: {str(e)}")

# =====================
# 获取全市场股票（加容错）
# =====================
def get_all_a_stocks():
    try:
        print("开始获取全市场股票列表...")
        df = ak.stock_zh_a_spot_em(timeout=akshare_timeout)
        if df.empty:
            print("股票列表为空")
            return []
        
        symbols = []
        for _, row in df.iterrows():
            try:
                code = str(row["代码"]).strip()
                name = str(row["名称"]).upper().strip()
                
                # 过滤规则
                if code.startswith(("8", "4")):
                    continue
                if "ST" in name or "退" in name:
                    continue
                if len(code) == 6:  # 只保留6位代码
                    symbols.append(code)
            except:
                continue
        
        print(f"获取到 {len(symbols)} 只股票")
        return symbols[:100]  # 先只扫前100只，加快测试速度
    except Exception as e:
        print(f"获取股票列表失败: {str(e)}")
        send_wechat_work_msg(f"❌ 选股机器人启动失败：获取股票列表出错\n错误：{str(e)}")
        return []

# =====================
# 获取日线数据（加容错）
# =====================
def get_daily(symbol):
    try:
        df = ak.stock_zh_a_daily(symbol=symbol, adjust="qfq", timeout=akshare_timeout)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        return df
    except:
        return pd.DataFrame()

# =====================
# 获取实时价格（加容错）
# =====================
def get_realtime_price(symbol):
    try:
        rt = ak.stock_zh_a_spot_em(symbol=symbol, timeout=akshare_timeout)
        return float(rt["最新价"].iloc[0])
    except:
        return None

# =====================
# MACD计算
# =====================
def macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    return dif, dea

# =====================
# 核心选股条件（加完整异常捕获）
# =====================
def check_signal(symbol):
    try:
        df = get_daily(symbol)
        if len(df) < 120:
            return False

        close = df["close"]
        vol = df["volume"]

        # 计算指标（修复60均量笔误）
        ma25 = close.rolling(25).mean()
        vol5 = vol.rolling(5).mean()
        vol60 = vol.rolling(60).mean()  # 关键修复：6→60
        dif, dea = macd(close)

        # 跳过空值
        if pd.isna(ma25.iloc[-1]) or pd.isna(vol60.iloc[-1]) or pd.isna(dea.iloc[-1]):
            return False

        # 条件1：价格上穿25日线
        cond1 = (close.iloc[-1] > ma25.iloc[-1]) and (close.iloc[-2] <= ma25.iloc[-1])

        # 条件2：5日均量金叉60日均量
        cond2 = (vol5.iloc[-1] > vol60.iloc[-1]) and (vol5.iloc[-2] <= vol60.iloc[-1])

        # 条件3：MACD金叉
        cond3 = (dif.iloc[-1] > dea.iloc[-1]) and (dif.iloc[-2] <= dea.iloc[-1])

        # 条件4：实时价>25日线
        rt_price = get_realtime_price(symbol)
        if rt_price is None:
            return False
        cond4 = rt_price > ma25.iloc[-1]

        # 条件5：周线过滤
        df["week"] = pd.to_datetime(df["date"]).dt.to_period("W")
        week_df = df.groupby("week").agg(close_w=("close", "last")).dropna()
        if len(week_df) < 30:
            return False
        ma25_week = week_df["close_w"].rolling(25).mean()
        cond_week = week_df["close_w"].iloc[-1] > ma25_week.iloc[-1]

        return all([cond1, cond2, cond3, cond4, cond_week])

    except Exception as e:
        print(f"处理 {symbol} 出错: {str(e)}")
        return False

# =====================
# 主程序（全程防崩+调试日志）
# =====================
if __name__ == "__main__":
    try:
        print("===== 全市场选股机器人启动 =====")
        send_wechat_work_msg("📢 选股机器人开始运行...")
        
        # 获取股票列表
        all_codes = get_all_a_stocks()
        if not all_codes:
            send_wechat_work_msg("❌ 未获取到可筛选的股票列表")
            exit(0)
        
        # 筛选股票
        hit_list = []
        for i, code in enumerate(all_codes):
            print(f"正在筛选 {i+1}/{len(all_codes)}: {code}")
            if check_signal(code):
                hit_list.append(code)
                print(f"✅ 命中: {code}")
        
        # 推送结果
        if hit_list:
            msg = "📈 全市场日线三金叉选股信号\n"
            msg += "✅ 价格上穿25日线\n✅ 5日均量金叉60日均量\n✅ MACD金叉\n✅ 实时价站稳25日线\n✅ 周线多头\n\n"
            msg += "触发股票：\n" + "\n".join([f"• {c}" for c in hit_list])
        else:
            msg = "📊 全市场选股结果\n今日暂无符合日线三金叉条件的股票，继续观望～"
        
        send_wechat_work_msg(msg)
        print(f"===== 运行结束，共筛选出 {len(hit_list)} 只股票 =====")

    except Exception as e:
        error_info = f"❌ 选股机器人运行崩溃\n错误详情：{str(e)}\n{traceback.format_exc()}"
        print(error_info)
        send_wechat_work_msg(error_info)
