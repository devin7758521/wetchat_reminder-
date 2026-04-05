import pandas as pd
import time
import sys
import os
import json
import re
import urllib3
from datetime import datetime, timedelta

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import requests
import baostock as bs
import akshare as ak  # 仅用于抓新闻（东财新闻接口未被封）

# ============================

# 配置

# ============================

VERSION    = "v2026.04.05.CIO.Pro"
WEB_KEY    = os.environ.get(“WECHAT_WEBHOOK_KEY”)
GEMINI_KEY = os.environ.get(“GEMINI_API_KEY”)

# ============================

# 微信通知

# ============================

def send_wechat(content):
if not WEB_KEY:
return
url = f”https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEB_KEY}”
try:
requests.post(url, json={“msgtype”: “text”, “text”: {“content”: content}}, timeout=15)
except Exception as e:
print(f”⚠️  微信发送失败: {e}”)

# ============================

# BaoStock：代码格式转换

# 600001 -> sh.600001

# 000001 -> sz.000001

# ============================

def to_bs_code(code):
code = str(code).zfill(6)
if code.startswith(‘6’):
return f”sh.{code}”
else:
return f”sz.{code}”

def from_bs_code(bs_code):
return bs_code.split(’.’)[1]

# ============================

# BaoStock：获取最近一个交易日的收盘行情

# 替代 ak.stock_zh_a_spot_em()

# ============================

def get_all_stocks_quote():
“””
获取全市场主板股票最新收盘价和成交额
返回 DataFrame，列：code, name, close, amount
“””
print(“📡 BaoStock 获取全市场收盘行情…”)

```
# 获取最近交易日
today = datetime.now().strftime('%Y-%m-%d')
rs = bs.query_trade_dates(start_date=(datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d'),
                           end_date=today)
trade_dates = []
while rs.error_code == '0' and rs.next():
    row = rs.get_row_data()
    if row[1] == '1':  # is_trading_day
        trade_dates.append(row[0])

if not trade_dates:
    print("❌ 获取交易日失败")
    return None

last_trade_date = trade_dates[-1]
print(f"📅 最近交易日: {last_trade_date}")

# 获取当日全市场行情
rs = bs.query_all_stock(day=last_trade_date)
stock_list = []
while rs.error_code == '0' and rs.next():
    stock_list.append(rs.get_row_data())

if not stock_list:
    print("❌ 获取股票列表失败")
    return None

df_stocks = pd.DataFrame(stock_list, columns=rs.fields)

# 只要主板：sh.6xxxxx 和 sz.0xxxxx
df_stocks = df_stocks[
    df_stocks['code'].str.startswith(('sh.6', 'sz.0'))
].copy()

print(f"📊 主板股票共 {len(df_stocks)} 只，开始获取收盘价...")

# 批量获取当日K线（收盘价+成交额）
results = []
codes = df_stocks['code'].tolist()
names = dict(zip(df_stocks['code'], df_stocks['code_name']))

for i, bs_code in enumerate(codes, 1):
    try:
        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,code,close,volume,amount,tradestatus",
            start_date=last_trade_date,
            end_date=last_trade_date,
            frequency="d",
            adjustflag="2"
        )
        data = []
        while rs.error_code == '0' and rs.next():
            data.append(rs.get_row_data())

        if data and data[0][5] == '1':  # tradestatus=1 正常交易
            row = data[0]
            close  = float(row[2]) if row[2] else 0
            amount = float(row[4]) if row[4] else 0
            results.append({
                'code':   from_bs_code(bs_code),
                'name':   names.get(bs_code, ''),
                'close':  close,
                'amount': amount
            })
    except Exception as e:
        pass

    if i % 200 == 0:
        print(f"  ⏳ 已处理 {i}/{len(codes)}...")

df_result = pd.DataFrame(results)
print(f"✅ 收盘行情获取完成，有效股票 {len(df_result)} 只")
return df_result, last_trade_date
```

# ============================

# BaoStock：获取个股日线历史

# 替代 ak.stock_zh_a_hist()

# ============================

def get_hist_data(code, start_date):
“””
获取个股复权日线数据
返回 DataFrame，index为DatetimeIndex，列含：收盘、成交量
“””
bs_code = to_bs_code(code)
rs = bs.query_history_k_data_plus(
bs_code,
“date,close,volume”,
start_date=start_date,
end_date=datetime.now().strftime(’%Y-%m-%d’),
frequency=“d”,
adjustflag=“2”  # 前复权
)
data = []
while rs.error_code == ‘0’ and rs.next():
data.append(rs.get_row_data())

```
if not data:
    return None

df = pd.DataFrame(data, columns=['日期', '收盘', '成交量'])
df['日期']  = pd.to_datetime(df['日期'])
df['收盘']  = pd.to_numeric(df['收盘'],  errors='coerce')
df['成交量'] = pd.to_numeric(df['成交量'], errors='coerce')
df = df.dropna().set_index('日期')
return df
```

# ============================

# 抓取个股新闻（保留AKShare，新闻接口未被封）

# ============================

def get_stock_news(code):
try:
news_df = ak.stock_news_em(symbol=code)
if news_df is None or news_df.empty:
return {“status”: “暂无近期核心公告”, “news”: “”, “code”: code}
top_news = news_df[‘新闻标题’].head(3).tolist()
return {“status”: “✅ 内参获取成功”, “news”: “ | “.join(top_news), “code”: code}
except Exception as e:
return {“status”: f”❌ 新闻检索异常: {str(e)[:50]}”, “news”: “”, “code”: code}

# ============================

# 核心策略：周线量能粘合

# ============================

def check_strategy(code, name, spot_dict):
“””
策略：价格(3-70) + 周线量能粘合(-3%~+7%) + 5周均量向上 + 站稳125日均线
“””
CFG_VOL_LOW  = -0.03
CFG_VOL_HIGH =  0.07

```
try:
    print(f"🔍 分析 {name}({code})...")

    curr_price = spot_dict.get(code, 0)
    if curr_price == 0:
        return False

    print(f"💰 {name}({code}): 收盘价 {curr_price:.2f}")

    if not (3.0 <= curr_price <= 70.0):
        return False

    start_date = (datetime.now() - timedelta(days=800)).strftime('%Y-%m-%d')
    df_daily = get_hist_data(code, start_date)

    if df_daily is None or df_daily.empty:
        print(f"❌ {name}({code}): 历史数据获取失败，跳过")
        return False

    if len(df_daily) < 125:
        print(f"❌ {name}({code}): 日线不足125天")
        return False

    # 周化拟合
    df_daily = df_daily.copy()
    df_daily['week'] = df_daily.index.to_period('W')
    weekly_volumes   = df_daily.groupby('week')['成交量'].sum()
    latest_weekly_data = weekly_volumes.tail(65)

    if len(latest_weekly_data) < 61:
        print(f"❌ {name}({code}): 周线不足61周")
        return False

    v5  = latest_weekly_data.rolling(5).mean()
    v60 = latest_weekly_data.rolling(60).mean()
    latest_v5  = v5.iloc[-1]
    latest_v60 = v60.iloc[-1]

    if pd.isna(latest_v5) or pd.isna(latest_v60) or latest_v60 == 0:
        print(f"❌ {name}({code}): 均量计算异常")
        return False

    vol_up        = latest_v5 > v5.iloc[-2] if len(v5) > 1 else False
    raw_deviation = (latest_v5 - latest_v60) / latest_v60
    is_binding    = CFG_VOL_LOW <= raw_deviation <= CFG_VOL_HIGH

    print(f"📈 {name}({code}): 量能向上:{vol_up}, 粘合:{is_binding} (偏离:{raw_deviation:.2%})")

    ma125         = df_daily['收盘'].rolling(125).mean().iloc[-1]
    price_support = curr_price > ma125
    print(f"🚀 {name}({code}): 125均线:{ma125:.2f}, 站稳:{price_support}")

    if vol_up and is_binding and price_support:
        print(f"🎯 命中: {name}({code}) | 现价:{curr_price:.2f} | 偏离:{raw_deviation:.2%}")
        return True
    return False

except Exception as e:
    print(f"❌ {name}({code}): 异常 -> {str(e)}")
    return False
```

# ============================

# 周五优化决策

# ============================

def optimize_weekly_stars():
if not os.path.exists(“weekly_stars.json”):
send_wechat(“📅 周五优化：本周无四星以上股票记录。”)
return

```
with open("weekly_stars.json", "r", encoding="utf-8") as f:
    weekly_stars = json.load(f)

if not weekly_stars:
    send_wechat("📅 周五优化：本周无四星以上股票记录。")
    return

now     = datetime.now()
now_str = now.strftime('%Y-%m-%d %H:%M')
api_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"

prompt = (
    f"你是具备全球视野的首席投资官。当前北京时间 {now_str} 【周五优化决策】。\n"
    f"以下是本周（周一至周四）选出的四星以上标的名单：\n\n"
    f"【本周四星以上标的】：\n"
    + "\n".join([f"- {s['name']}({s['code']})" for s in weekly_stars])
    + "\n\n【决策维度】：\n"
    "1. **综合评级**：基于本周表现和当前市场环境，重新评定星级（5星严格限制在1-2只）。\n"
    "2. **短期走势**：预测下周走势，给出买入/持有/卖出建议。\n"
    "3. **风险提示**：指出潜在风险（如政策、业绩）。\n\n"
    "【输出要求】：\n"
    "   - 🌟🌟... 股票名(代码) + 30字内深度分析。\n"
    "   - 未获星标的：仅显示\"代码 名称\"。\n\n"
    "【待优化标的】：\n"
    + "\n".join([f"- {s['name']}({s['code']})" for s in weekly_stars])
)

try:
    res     = requests.post(api_url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60)
    ai_text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
    send_wechat(
        f"🌟 周五优化决策报告\n时间: {now_str}\n\n{ai_text}\n\n"
        f"📊 本周四星以上标的总数: {len(weekly_stars)}"
    )
except Exception as e:
    send_wechat(f"❌ 周五优化AI决策异常: {str(e)[:100]}")
```

# ============================

# 主函数

# ============================

def main():
if len(sys.argv) < 2:
print(“用法: python stock_scanner.py [1|2|summary]”)
return

```
mode       = sys.argv[1]
now        = datetime.now()
now_str    = now.strftime('%Y-%m-%d %H:%M')
period_tag = "【早盘观察】" if now.hour < 12 else "【尾盘决策】"

# 周一清空上周四星记录
if mode == "1" and now.weekday() == 0:
    if os.path.exists("weekly_stars.json"):
        os.remove("weekly_stars.json")
        print("🗑️  已清空上周四星记录")

if mode == "1":
    send_wechat(f"📢 机器人启动\n时间: {now_str}\n任务: {period_tag} 扫描开始...")

# ============================
# summary 模式
# ============================
if mode == "summary":
    all_hits = []
    for fname in ["hits_part1.json", "hits_part2.json"]:
        if os.path.exists(fname):
            with open(fname, "r", encoding="utf-8") as file:
                all_hits += json.load(file)

    if not all_hits:
        send_wechat(f"📅 {now_str}\n{period_tag} 扫描结束，今日未发现符合要求标的。")
        return

    top_hits = sorted(all_hits, key=lambda x: x['amount'], reverse=True)[:10]

    enriched_list = []
    news_status   = []
    for stock in top_hits:
        print(f"📊 抓取内参: {stock['name']}({stock['code']})...")
        news_result = get_stock_news(stock['code'])
        enriched_list.append(f"- {stock['name']}({stock['code']}): {news_result['news']}")
        news_status.append(f"{stock['name']}({stock['code']}): {news_result['status']}")
        time.sleep(0.5)

    api_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    prompt  = (
        f"你是具备全球视野的首席投资官。当前北京时间 {now_str} {period_tag}。\n"
        f"以下是 10 只量能突破标的及其【实时核心新闻内参】。请执行深度复核：\n\n"
        "【决策维度】：\n"
        "1. **基于内参推理**：分析所给新闻对股价的短期/中期影响。有重大利空直接判死刑。\n"
        "2. **宏观背景联动**：结合当前国内外大形势判断该行业是否处于风口。\n"
        "3. **星级评定**：5星严格限制在 1-2 只。用🌟表示星级。\n\n"
        "【输出要求】：\n"
        "   - 🌟🌟... 股票名(代码) + 30字内深度走向预测。\n"
        "   - 未获星标的：仅显示\"代码 名称\"。\n\n"
        "【待分析内参名单】：\n"
        + "\n".join(enriched_list)
    )

    try:
        res     = requests.post(api_url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60)
        ai_text = res.json()["candidates"][0]["content"]["parts"][0]["text"]

        wechat_content = (
            f"🌟 {period_tag} 深度决策报告\n时间: {now_str}\n\n"
            f"📊 今日总信号: {len(all_hits)}\n\n"
            f"📰 内参状态：\n" + "\n".join(news_status)
            + "\n\n🎯 符合技术指标：\n"
            + "".join([f"- {s['name']}({s['code']})\n" for s in all_hits])
            + f"\n{ai_text}"
        )
        send_wechat(wechat_content)

        # 提取四星以上存档
        stars = []
        for line in ai_text.split('\n'):
            if '🌟🌟🌟🌟' in line:
                match = re.search(r'([^\s(]+)\((\d+)\)', line)
                if match:
                    stars.append({"name": match.group(1), "code": match.group(2), "star": "4+"})

        if stars:
            existing_stars = []
            if os.path.exists("weekly_stars.json"):
                try:
                    with open("weekly_stars.json", "r", encoding="utf-8") as f:
                        existing_stars = json.load(f)
                except Exception:
                    existing_stars = []
            existing_stars.extend(stars)
            with open("weekly_stars.json", "w", encoding="utf-8") as f:
                json.dump(existing_stars, f, indent=2, ensure_ascii=False)

        if now.weekday() == 4:
            optimize_weekly_stars()

    except Exception as e:
        send_wechat(f"❌ AI 决策异常: {str(e)[:100]}")

# ============================
# 扫描模式 1 或 2
# ============================
else:
    part = int(mode)

    # BaoStock登录
    lg = bs.login()
    if lg.error_code != '0':
        msg = f"❌ BaoStock登录失败: {lg.error_msg}"
        print(msg)
        send_wechat(msg)
        return
    print("✅ BaoStock登录成功")

    try:
        result = get_all_stocks_quote()
        if result is None:
            msg = "❌ 全市场行情获取失败，任务终止"
            print(msg)
            send_wechat(msg)
            return

        df, last_trade_date = result

        # 过滤ST、价格范围
        df = df[
            (~df['name'].str.contains('ST', na=False)) &
            (3.0 <= df['close']) & (df['close'] <= 70.0)
        ].copy()

        # 按成交额排序取前1200
        active = df.sort_values(by='amount', ascending=False).head(1200)
        batch  = active.head(600) if part == 1 else active.tail(600)

        spot_dict = dict(zip(df['code'].astype(str), df['close']))

        hits  = []
        total = len(batch)
        print(f"📊 开始扫描 {total} 只股票...")

        for i, (_, row) in enumerate(batch.iterrows(), 1):
            stock_name = row['name']
            stock_code = str(row['code'])
            print(f"\n🔄 [{i}/{total}] {stock_name}({stock_code})")

            if check_strategy(stock_code, stock_name, spot_dict):
                hits.append({
                    "name":   stock_name,
                    "code":   stock_code,
                    "amount": row['amount']
                })

            time.sleep(0.1)  # BaoStock不限速，0.1秒足够

            if i % 100 == 0:
                print(f"☕ 已扫描{i}只...")

        print(f"\n✅ 扫描完成，命中 {len(hits)} 只")
        with open(f"hits_part{part}.json", "w", encoding="utf-8") as f:
            json.dump(hits, f, ensure_ascii=False, indent=2)
        print(f"💾 已保存至 hits_part{part}.json")

    finally:
        bs.logout()
        print("👋 BaoStock已登出")
```

if **name** == “**main**”:
main()