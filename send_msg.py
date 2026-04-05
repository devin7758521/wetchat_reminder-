import pandas as pd
import time
import sys
import os
import json
import re
import urllib3
from datetime import datetime, timedelta

# ============================
# 第一步：压制SSL警告
# ============================
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================
# 第二步：import requests 后立即打猴子补丁
# 伪装成Chrome浏览器，骗过东财反爬检测
# ============================
import requests

_original_get = requests.Session.get
_original_post = requests.Session.post

FAKE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Referer": "https://quote.eastmoney.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

def _patched_get(self, url, **kwargs):
    h = dict(FAKE_HEADERS)
    h.update(kwargs.pop("headers", {}) or {})
    kwargs["headers"] = h
    kwargs.setdefault("timeout", 20)
    kwargs.setdefault("verify", False)
    return _original_get(self, url, **kwargs)

def _patched_post(self, url, **kwargs):
    h = {}
    h.update(kwargs.pop("headers", {}) or {})
    kwargs["headers"] = h
    kwargs.setdefault("timeout", 20)
    kwargs.setdefault("verify", False)
    return _original_post(self, url, **kwargs)

requests.Session.get = _patched_get
requests.Session.post = _patched_post

# ============================
# 第三步：打完补丁再import akshare
# 这样akshare所有请求都自动带上浏览器身份
# ============================
import akshare as ak

# ============================
# 配置
# ============================
VERSION = "v2026.04.05.CIO.Pro"
WEB_KEY = os.environ.get("WECHAT_WEBHOOK_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")


# ============================
# 智能重试封装
# 区分错误类型，避免无效等待
# ============================
def robust_akshare_call(func, *args, max_retries=3, **kwargs):
    """
    智能重试：
    - 瞬间抖动(断连/超时) → 等3秒重试
    - 限流/封杀(429) → 等15秒重试
    - 其他未知错误 → 直接跳过不浪费时间
    - 最多重试3次，最坏情况9秒，不拖累整体进度
    """
    last_err = None
    for attempt in range(max_retries):
        try:
            result = func(*args, **kwargs)
            if isinstance(result, pd.DataFrame) and result.empty:
                return None
            return result
        except Exception as e:
            last_err = e
            err_str = str(e)

            if any(x in err_str for x in [
                "RemoteDisconnected", "Connection aborted",
                "timeout", "Timeout", "ConnectionError",
                "ConnectionReset", "ChunkedEncodingError"
            ]):
                wait = 3
                print(f"    ⚠️  网络抖动，{wait}秒后重试({attempt+1}/{max_retries})...")

            elif any(x in err_str for x in ["429", "Too Many", "频繁", "限制"]):
                wait = 15
                print(f"    🚫  被限流，{wait}秒后重试({attempt+1}/{max_retries})...")

            else:
                # 未知错误直接跳过，不重试
                print(f"    ❌  未知错误，直接跳过: {err_str[:80]}")
                return None

            time.sleep(wait)

    print(f"    ❌  重试{max_retries}次仍失败: {str(last_err)[:80]}")
    return None


# ============================
# 微信通知
# ============================
def send_wechat(content):
    if not WEB_KEY:
        return
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEB_KEY}"
    try:
        requests.post(url, json={"msgtype": "text", "text": {"content": content}}, timeout=15)
    except Exception as e:
        print(f"⚠️  微信发送失败: {e}")


# ============================
# 抓取个股新闻
# ============================
def get_stock_news(code):
    try:
        news_df = robust_akshare_call(ak.stock_news_em, symbol=code, max_retries=3)
        if news_df is None or news_df.empty:
            return {"status": "暂无近期核心公告", "news": "", "code": code}
        top_news = news_df['新闻标题'].head(3).tolist()
        return {"status": "✅ 内参获取成功", "news": " | ".join(top_news), "code": code}
    except Exception as e:
        return {"status": f"❌ 新闻检索异常: {str(e)[:50]}", "news": "", "code": code}


# ============================
# 核心策略
# ============================
def check_strategy(code, name, realtime_spot_dict):
    """
    策略：价格(3-70) + 周线量能粘合(-3%到+7%) + 5周均量向上 + 站稳125日均线
    """
    CFG_VOL_LOW = -0.03
    CFG_VOL_HIGH = 0.07

    try:
        print(f"🔍 分析 {name}({code})...")

        start_date = (datetime.now() - timedelta(days=800)).strftime('%Y%m%d')

        df_daily = robust_akshare_call(
            ak.stock_zh_a_hist,
            symbol=code,
            period="daily",
            adjust="qfq",
            start_date=start_date,
            max_retries=3
        )

        if df_daily is None or df_daily.empty:
            print(f"❌ {name}({code}): 获取历史数据失败，跳过")
            return False

        # 统一 DatetimeIndex
        if not isinstance(df_daily.index, pd.DatetimeIndex):
            if '日期' in df_daily.columns:
                df_daily['日期'] = pd.to_datetime(df_daily['日期'])
                df_daily = df_daily.set_index('日期')
            else:
                print(f"❌ {name}({code}): 找不到日期列，列名={list(df_daily.columns)}")
                return False

        # 价格
        today = datetime.now().date()
        latest_hist_date = df_daily.index[-1].date()

        if code in realtime_spot_dict and latest_hist_date == today:
            curr_price = realtime_spot_dict[code]
            print(f"💰 {name}({code}): 实时价 {curr_price:.2f}")
        else:
            curr_price = df_daily['收盘'].iloc[-1]
            status_msg = "休市/盘后" if latest_hist_date != today else "收盘价"
            print(f"💰 {name}({code}): {status_msg} {curr_price:.2f} (截至:{latest_hist_date})")

        if not (3.0 <= curr_price <= 70.0):
            return False

        # 周化拟合
        df_daily = df_daily.copy()
        df_daily['week'] = df_daily.index.to_period('W')
        weekly_volumes = df_daily.groupby('week')['成交量'].sum()

        latest_week_period = weekly_volumes.index[-1]
        current_week_days = len(df_daily[df_daily['week'] == latest_week_period])
        is_week_incomplete = (latest_hist_date == today) and (today.weekday() < 4)

        if is_week_incomplete and current_week_days > 0:
            weekly_volumes.iloc[-1] = weekly_volumes.iloc[-1] * (5.0 / current_week_days)
            print(f"📊 {name}({code}): 本周进行中({current_week_days}天)，周化拟合")
        else:
            print(f"📊 {name}({code}): 真实周量({current_week_days}天)")

        latest_weekly_data = weekly_volumes.tail(65)

        if len(latest_weekly_data) < 61:
            print(f"❌ {name}({code}): 周线不足61周")
            return False

        v5 = latest_weekly_data.rolling(5).mean()
        v60 = latest_weekly_data.rolling(60).mean()
        latest_v5 = v5.iloc[-1]
        latest_v60 = v60.iloc[-1]

        if pd.isna(latest_v5) or pd.isna(latest_v60) or latest_v60 == 0:
            print(f"❌ {name}({code}): 均量计算异常")
            return False

        vol_up = latest_v5 > v5.iloc[-2] if len(v5) > 1 else False
        raw_deviation = (latest_v5 - latest_v60) / latest_v60
        is_binding = CFG_VOL_LOW <= raw_deviation <= CFG_VOL_HIGH

        print(f"📈 {name}({code}): 量能向上:{vol_up}, 粘合:{is_binding} (偏离:{raw_deviation:.2%})")

        if len(df_daily) < 125:
            print(f"❌ {name}({code}): 日线不足125天")
            return False

        ma125 = df_daily['收盘'].rolling(125).mean().iloc[-1]
        price_support = curr_price > ma125
        print(f"🚀 {name}({code}): 125均线:{ma125:.2f}, 站稳:{price_support}")

        if vol_up and is_binding and price_support:
            print(f"🎯 命中: {name}({code}) | 现价:{curr_price:.2f} | 偏离:{raw_deviation:.2%}")
            return True
        return False

    except Exception as e:
        print(f"❌ {name}({code}): 异常 -> {str(e)}")
        return False


# ============================
# 周五优化决策
# ============================
def optimize_weekly_stars():
    if not os.path.exists("weekly_stars.json"):
        send_wechat("📅 周五优化：本周无四星以上股票记录。")
        return

    with open("weekly_stars.json", "r", encoding="utf-8") as f:
        weekly_stars = json.load(f)

    if not weekly_stars:
        send_wechat("📅 周五优化：本周无四星以上股票记录。")
        return

    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M')
    api_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"

    prompt = (
        f"你是具备全球视野的首席投资官。当前北京时间 {now_str} 【周五优化决策】。\n"
        f"以下是本周（周一至周四）选出的四星以上标的名单：\n\n"
        f"【本周四星以上标的】：\n"
        + "\n".join([f"- {s['name']}({s['code']})" for s in weekly_stars])
        + "\n\n【决策维度】：\n"
        f"1. **综合评级**：基于本周表现和当前市场环境，重新评定星级（5星严格限制在1-2只）。\n"
        f"2. **短期走势**：预测下周走势，给出买入/持有/卖出建议。\n"
        f"3. **风险提示**：指出潜在风险（如政策、业绩）。\n\n"
        f"【输出要求】：\n"
        f"   - 🌟🌟... 股票名(代码) + 30字内深度分析。\n"
        f"   - 未获星标的：仅显示\"代码 名称\"。\n\n"
        f"【待优化标的】：\n"
        + "\n".join([f"- {s['name']}({s['code']})" for s in weekly_stars])
    )

    try:
        res = requests.post(
            api_url,
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=60
        )
        ai_text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
        send_wechat(
            f"🌟 周五优化决策报告\n时间: {now_str}\n\n{ai_text}\n\n"
            f"📊 本周四星以上标的总数: {len(weekly_stars)}"
        )
    except Exception as e:
        send_wechat(f"❌ 周五优化AI决策异常: {str(e)[:100]}")


# ============================
# 主函数
# ============================
def main():
    if len(sys.argv) < 2:
        print("用法: python stock_scanner.py [1|2|summary]")
        return

    mode = sys.argv[1]
    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M')
    period_tag = "【早盘观察】" if now.hour < 12 else "【尾盘决策】"

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
        news_status = []
        for stock in top_hits:
            print(f"📊 抓取内参: {stock['name']}({stock['code']})...")
            news_result = get_stock_news(stock['code'])
            enriched_list.append(f"- {stock['name']}({stock['code']}): {news_result['news']}")
            news_status.append(f"{stock['name']}({stock['code']}): {news_result['status']}")
            time.sleep(0.5)

        api_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"

        prompt = (
            f"你是具备全球视野的首席投资官。当前北京时间 {now_str} {period_tag}。\n"
            f"以下是 10 只量能突破标的及其【实时核心新闻内参】。请执行深度复核：\n\n"
            f"【决策维度】：\n"
            f"1. **基于内参推理**：分析所给新闻对股价的短期/中期影响。有重大利空直接判死刑。\n"
            f"2. **宏观背景联动**：结合当前国内外大形势判断该行业是否处于风口。\n"
            f"3. **星级评定**：5星严格限制在 1-2 只。用🌟表示星级。\n\n"
            f"【输出要求】：\n"
            f"   - 🌟🌟... 股票名(代码) + 30字内深度走向预测。\n"
            f"   - 未获星标的：仅显示\"代码 名称\"。\n\n"
            f"【待分析内参名单】：\n"
            + "\n".join(enriched_list)
        )

        try:
            res = requests.post(
                api_url,
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=60
            )
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

        print("📡 获取全市场实时行情...")
        df = robust_akshare_call(ak.stock_zh_a_spot_em, max_retries=3)

        if df is None or df.empty:
            msg = "❌ 实时行情获取失败，任务终止"
            print(msg)
            send_wechat(msg)
            return

        print(f"✅ 行情获取成功，共 {len(df)} 条")

        df = df[
            (df['代码'].astype(str).str.startswith(('60', '00'))) &
            (~df['名称'].str.contains('ST')) &
            (3.0 <= df['最新价']) & (df['最新价'] <= 70.0)
        ]

        active = df.sort_values(by='成交额', ascending=False).head(1200)
        batch = active.head(600) if part == 1 else active.tail(600)
        spot_dict = dict(zip(df['代码'].astype(str), df['最新价']))

        hits = []
        total = len(batch)
        print(f"📊 开始扫描 {total} 只股票...")

        for i, (_, row) in enumerate(batch.iterrows(), 1):
            stock_name = row['名称']
            stock_code = str(row['代码'])
            print(f"\n🔄 [{i}/{total}] {stock_name}({stock_code})")

            if check_strategy(stock_code, stock_name, spot_dict):
                hits.append({
                    "name": stock_name,
                    "code": stock_code,
                    "amount": row['成交额']
                })

            time.sleep(0.3)

            if i % 50 == 0:
                print(f"☕ 已扫描{i}只，休息3秒...")
                time.sleep(3)

        print(f"\n✅ 扫描完成，命中 {len(hits)} 只")
        with open(f"hits_part{part}.json", "w", encoding="utf-8") as f:
            json.dump(hits, f, ensure_ascii=False, indent=2)
        print(f"💾 已保存至 hits_part{part}.json")


if __name__ == "__main__":
    main()