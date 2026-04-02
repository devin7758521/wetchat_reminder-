import pandas as pd
import requests
import time
import sys
import os
import json
from datetime import datetime

# mootdx 相关导入
from mootdx.quotes import Quotes

# 配置
VERSION = "v2026.04.02.Global.Stable.Mootdx"
WEB_KEY = os.environ.get("WECHAT_WEBHOOK_KEY")
# 如果你后面要用 Gemini，可以保留；当前逻辑里没用到
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")


def send_wechat(content):
    if not WEB_KEY:
        return
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEB_KEY}"
    try:
        requests.post(url, json={"msgtype": "text", "text": {"content": content}}, timeout=10)
    except Exception:
        pass


def check_strategy(code, name):
    """
    使用 mootdx 获取周线数据，执行原有策略逻辑：
    - 3 <= 当前价格 <= 70
    - 成交量 5 周均线向上
    - 成交量 5 周均相对 60 周均偏离度在 -3% ~ 7%
    - 当前价格在 25 周均上方
    """
    try:
        # 1. 创建 mootdx 行情客户端（建议用 bestip 自动选最优服务器）
        client = Quotes.factory(market='std', bestip=True, timeout=15)

        # 2. 获取周线 K线
        # frequency=10 表示周线，offset=0 从最新一条开始，count=100 取近 100 周
        df = client.bars(symbol=code, frequency=10, start=0, offset=100)
        if df is None or df.empty or len(df) < 65:
            return False

        # 3. 字段对齐：mootdx 返回的是小写列名
        # 典型列：open, close, high, low, volume 等
        df = df.rename(columns={
            'open': '开盘',
            'close': '收盘',
            'high': '最高',
            'low': '最低',
            'volume': '成交量',
        })

        # 按时间正序排列，方便 rolling 计算
        df = df.sort_index(ascending=True).reset_index(drop=True)

        curr_price = df['收盘'].iloc[-1]

        # 价格区间筛选
        if not (3.0 <= curr_price <= 70.0):
            return False

        # 成交量均线
        v5 = df['成交量'].rolling(5).mean()
        v60 = df['成交量'].rolling(60).mean()

        vol_up = v5.iloc[-1] > v5.iloc[-2]
        deviation = (v5.iloc[-1] - v60.iloc[-1]) / v60.iloc[-1]

        # 偏离度 -3% ~ 7%
        is_binding = -0.03 <= deviation <= 0.07

        # 25 周均线
        ma25 = df['收盘'].rolling(25).mean()
        price_support = curr_price > ma25.iloc[-1]

        return vol_up and is_binding and price_support

    except Exception as e:
        # 打印异常方便调试（生产环境可以改成日志）
        print(f"[{code} {name}] check_strategy error: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python script.py <mode>")
        return

    mode = sys.argv[1]
    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M')

    if mode == "summary":
        # 汇总逻辑保持不变
        all_hits = []
        for f in ["hits_part1.json", "hits_part2.json"]:
            if os.path.exists(f):
                with open(f, "r", encoding="utf-8") as file:
                    all_hits += json.load(file)

        if not all_hits:
            send_wechat(f"📅 {now_str}\n扫描结束，未发现信号。")
            return

        # 排序取前10（按 amount 降序）
        top_hits = sorted(all_hits, key=lambda x: x['amount'], reverse=True)[:10]
        send_wechat(f"🌟 发现 {len(all_hits)} 只标的，Top3: {[h['name'] for h in top_hits[:3]]}")

    else:
        # mode = "1" 或 "2"，做分片扫描
        try:
            part = int(mode)
        except ValueError:
            print("mode 必须是 summary 或 1/2")
            return

        try:
            # 1. 创建 mootdx 行情客户端
            client = Quotes.factory(market='std', bestip=True, timeout=15)

            # 2. 获取全部 A 股列表（code + name）
            stock_df = client.stock_all()
            if stock_df is None or stock_df.empty:
                send_wechat(f"❌ 获取股票列表失败")
                return

            # 3. 筛选：只要 60/00 开头，且名称不含 ST、退
            mask_code = stock_df['code'].str.startswith(('60', '00'))
            mask_no_st = ~stock_df['name'].str.contains('ST|退', na=False)
            active = stock_df[mask_code & mask_no_st].copy()

            # 4. 分片处理，减少单次运行负担
            total = len(active)
            half = total // 2
            if part == 1:
                batch = active.head(half)
            else:
                batch = active.tail(total - half)

            hits = []
            for _, row in batch.iterrows():
                code = row['code']
                name = row['name']
                if check_strategy(code, name):
                    hits.append({"name": name, "code": code, "amount": 0})
                # 礼貌间隔，避免被服务器封禁
                time.sleep(0.1)

            with open(f"hits_part{part}.json", "w", encoding="utf-8") as f:
                json.dump(hits, f, ensure_ascii=False, indent=2)

        except Exception as e:
            send_wechat(f"❌ 列表获取失败: {str(e)[:50]}")


if __name__ == "__main__":
    main()
