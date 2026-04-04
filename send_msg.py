import pandas as pd
import requests
import akshare as ak
import time
import sys
import os
import json
import re
from datetime import datetime, timedelta

# 配置
VERSION = "v2026.04.03.CIO.Pro"
WEB_KEY = os.environ.get("WECHAT_WEBHOOK_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

def send_wechat(content):
    """发送微信通知"""
    if not WEB_KEY:
        return
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEB_KEY}"
    try:
        requests.post(url, json={"msgtype": "text", "text": {"content": content}}, timeout=10)
    except:
        pass

def get_stock_news(code):
    """为指定个股抓取最近3条核心新闻标题"""
    try:
        news_df = ak.stock_news_em(symbol=code)
        if news_df.empty:
            return {"status": "暂无近期核心公告", "news": "", "code": code}
        top_news = news_df['新闻标题'].head(3).tolist()
        return {"status": "✅ 内参获取成功", "news": " | ".join(top_news), "code": code}
    except Exception as e:
        return {"status": f"❌ 新闻检索异常: {str(e)[:50]}", "news": "", "code": code}

def check_strategy(code, name, realtime_spot_dict):
    """策略：价格(3-70) + 周线量能粘合(-3%到+7%) + 5周均量向上 + 站稳25周线"""
    CFG_VOL_LOW = -0.03
    CFG_VOL_HIGH = 0.07
    
    try:
        print(f"🔍 开始分析 {name}({code})...")
        
        start_date = (datetime.now() - timedelta(days=800)).strftime('%Y%m%d')
        df_daily = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq", start_date=start_date)
        
        if df_daily.empty:
            print(f"❌ {name}({code}): 获取不到历史数据")
            return False
        
        # ============================
        # 【核心修复】暴力统一 index 为 DatetimeIndex
        # 不管 akshare 返回的是 RangeIndex + 日期列，还是已经是 DatetimeIndex
        # 甚至是列名叫别的，全部兜住
        # ============================
        
        # 先打印一次结构，方便排查（正式跑稳了可以删掉这行）
        if code == "600487":  # 只对第一只报错的票打印，避免日志爆炸
            print(f"  🔍 列名: {list(df_daily.columns)}")
            print(f"  🔍 Index类型: {type(df_daily.index).__name__}")
        
        # 第一步：如果已经是 DatetimeIndex，直接用
        if isinstance(df_daily.index, pd.DatetimeIndex):
            pass  # 不用处理
        
        # 第二步：如果 index 不是 DatetimeIndex，去列里找日期列
        else:
            date_col = None
            # 穷举所有可能的日期列名（akshare 不同版本可能不一样）
            for col in ['日期', '交易日期', 'trade_date', 'date', 'Date', 'DATE']:
                if col in df_daily.columns:
                    date_col = col
                    break
            
            if date_col:
                df_daily[date_col] = pd.to_datetime(df_daily[date_col])
                df_daily = df_daily.set_index(date_col)
            else:
                # 兜底：打印所有列名，方便你告诉我实际的列名
                print(f"⚠️ {name}({code}): 找不到日期列！现有列名={list(df_daily.columns)}")
                # 最后挣扎：试试把 index 直接转
                try:
                    df_daily.index = pd.to_datetime(df_daily.index)
                except:
                    print(f"❌ {name}({code}): 无法转换为日期索引，跳过")
                    return False
        
        # 再次确认
        if not isinstance(df_daily.index, pd.DatetimeIndex):
            print(f"❌ {name}({code}): index仍不是DatetimeIndex，跳过")
            return False
        
        # ============================
        # 修复结束，下面的逻辑安全了
        # ============================
        
        # --- 价格获取 ---
        today = datetime.now().date()
        latest_val = df_daily.index[-1]
        latest_hist_date = latest_val.date() if hasattr(latest_val, 'date') else latest_val
        
        if code in realtime_spot_dict and str(latest_hist_date) == str(today):
            curr_price = realtime_spot_dict[code]
            print(f"💰 {name}({code}): 盘中实时价 {curr_price:.2f}")
        else:
            curr_price = df_daily['收盘'].iloc[-1]
            status_msg = "休市/盘后" if str(latest_hist_date) != str(today) else "收盘价"
            print(f"💰 {name}({code}): {status_msg} {curr_price:.2f} (截至:{latest_hist_date})")
        
        if not (3.0 <= curr_price <= 70.0):
            return False
            
        # --- 周化拟合 ---
        df_daily = df_daily.copy()
        df_daily['week'] = df_daily.index.to_period('W')  # ✅ 现在安全了
        
        weekly_volumes = df_daily.groupby('week')['成交量'].sum()
        
        latest_week_period = weekly_volumes.index[-1]
        current_week_days = len(df_daily[df_daily['week'] == latest_week_period])
        
        is_week_incomplete = (str(latest_hist_date) == str(today)) and (today.weekday() < 4)
        
        if is_week_incomplete and current_week_days > 0:
            estimated_full_week_vol = weekly_volumes.iloc[-1] * (5.0 / current_week_days)
            weekly_volumes.iloc[-1] = estimated_full_week_vol
            print(f"📊 {name}({code}): 本周进行中({current_week_days}天)，执行周化拟合")
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
        
        print(f"📈 {name}({code}): 量能向上:{vol_up}, 粘合:{is_binding} (偏离度:{raw_deviation:.2%})")
        
        if len(df_daily) < 125:
            print(f"❌ {name}({code}): 日线不足125天")
            return False
            
        ma125 = df_daily['收盘'].rolling(125).mean().iloc[-1]
        price_support = curr_price > ma125
        print(f"🚀 {name}({code}): 125均线:{ma125:.2f}, 站稳:{price_support}")
        
        if vol_up and is_binding and price_support:
            print(f"🎯 命中信号: {name}({code}) | 现价:{curr_price:.2f} | 偏离度:{raw_deviation:.2%}")
            return True
        return False
    except Exception as e:
        print(f"❌ {name}({code}): 异常 -> {str(e)}")
        return False

def optimize_weekly_stars():
    """周五优化分析本周四星以上股票"""
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
    period_tag = "【周五优化决策】"
    
    api_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"

    prompt = (
        f"你是具备全球视野的首席投资官。当前北京时间 {now_str} {period_tag}。\n"
        f"以下是本周（周一至周四）选出的四星以上标的名单：\n\n"
        f"【本周四星以上标的】：\n"
        + "\n".join([f"- {stock['name']}({stock['code']})" for stock in weekly_stars])
        + "\n\n"
        f"【决策维度】：\n"
        f"1. **综合评级**：基于本周表现和当前市场环境，重新评定星级（5星严格限制在1-2只）。\n"
        f"2. **短期走势**：预测下周走势，给出买入/持有/卖出建议。\n"
        f"3. **风险提示**：指出潜在风险（如政策、业绩）。\n\n"
        f"【输出要求】：\n"
        f"   - 🌟🌟... 股票名(代码) + 30字内深度分析（必须结合本周表现和当前环境）。\n"
        f"   - 未获星标的：仅在下方显示\"代码 名称\"。\n\n"
        f"【待优化标的】：\n"
        + "\n".join([f"- {stock['name']}({stock['code']})" for stock in weekly_stars])
    )

    try:
        res = requests.post(api_url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60)
        ai_text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
        send_wechat(f"🌟 周五优化决策报告\n时间: {now_str}\n\n{ai_text}\n\n📊 本周四星以上标的总数: {len(weekly_stars)}")
    except Exception as e:
        send_wechat(f"❌ 周五优化AI决策异常: {str(e)[:100]}")

def main():
    if len(sys.argv) < 2:
        return
    mode = sys.argv[1]
    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M')
    period_tag = "【早盘观察】" if now.hour < 12 else "【尾盘决策】"

    if mode == "1" and now.weekday() == 0:
        if os.path.exists("weekly_stars.json"):
            os.remove("weekly_stars.json")

    if mode == "1":
        send_wechat(f"📢 机器人启动通知\n时间: {now_str}\n任务: {period_tag} 扫描开始...")

    if mode == "summary":
        all_hits = []
        for f in ["hits_part1.json", "hits_part2.json"]:
            if os.path.exists(f):
                with open(f, "r", encoding="utf-8") as file:
                    all_hits += json.load(file)

        if not all_hits:
            send_wechat(f"📅 {now_str}\n{period_tag} 扫描结束，今日未发现符合要求标的。")
            return

        top_hits = sorted(all_hits, key=lambda x: x['amount'], reverse=True)[:10]

        enriched_list = []
        news_status = []  
        for stock in top_hits:
            print(f"📊 正在抓取内参: {stock['name']}({stock['code']})...")
            news_result = get_stock_news(stock['code'])
            enriched_list.append(f"- {stock['name']}({stock['code']}): {news_result['news']}")
            news_status.append(f"{stock['name']}({stock['code']}): {news_result['status']}")

        api_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"

        prompt = (
            f"你是具备全球视野的首席投资官。当前北京时间 {now_str} {period_tag}。\n"
            f"以下是 10 只量能突破标的及其【实时核心新闻内参】。请执行深度复核：\n\n"
            f"【决策维度】：\n"
            f"1. **基于内参推理**：分析所给新闻对股价的短期/中期影响。有重大利空（如立案、减持）直接判死刑。\n"
            f"2. **宏观背景联动**：结合当前国内外大形势（如美国加息、地缘政治等）判断该行业是否处于风口。\n"
            f"3. **星级评定**：5星严格限制在 1-2 只。用🌟表示星级。\n\n"
            f"【输出要求】：\n"
            f"   - 🌟🌟... 股票名(代码) + 30字内深度走向预测（必须结合所给内参或宏观背景）。\n"
            f"   - 未获星标的：仅在下方显示\"代码 名称\"。\n\n"
            f"【待分析内参名单】：\n"
            + "\n".join(enriched_list)
        )

        try:
            res = requests.post(api_url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60)
            ai_text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
            
            wechat_content = (
                f"🌟 {period_tag} 深度决策报告\n"
                f"时间: {now_str}\n\n"
                f"📊 今日总信号: {len(all_hits)}\n\n"
                f"📰 内参获取状态：\n"
                + "\n".join(news_status)
                + "\n\n"
                f"🎯 符合技术指标的股票：\n"
            )
            
            for stock in all_hits:
                wechat_content += f"- {stock['name']}({stock['code']})\n"
            
            wechat_content += f"\n{ai_text}"
            send_wechat(wechat_content)
            
            stars = []
            for line in ai_text.split('\n'):
                if '🌟🌟🌟🌟' in line:
                    match = re.search(r'([^\s(]+)\((\d+)\)', line)
                    if match:
                        name = match.group(1)
                        code = match.group(2)
                        stars.append({"name": name, "code": code, "star": "4+"})
            
            if stars:
                existing_stars = []
                if os.path.exists("weekly_stars.json"):
                    try:
                        with open("weekly_stars.json", "r", encoding="utf-8") as f:
                            existing_stars = json.load(f)
                    except:
                        existing_stars = []
                
                existing_stars.extend(stars)
                with open("weekly_stars.json", "w", encoding="utf-8") as f:
                    json.dump(existing_stars, f, indent=2, ensure_ascii=False)
            
            if now.weekday() == 4:
                optimize_weekly_stars()
                
        except Exception as e:
            send_wechat(f"❌ AI 决策异常: {str(e)[:100]}")

    else:
        part = int(mode)
        df = ak.stock_zh_a_spot_em()
        
        df = df[
            (df['代码'].astype(str).str.startswith(('60', '00'))) & 
            (~df['名称'].str.contains('ST')) & 
            (3.0 <= df['最新价']) & (df['最新价'] <= 70.0)
        ]
        
        active = df.sort_values(by='成交额', ascending=False).head(1200)
        batch = active.head(600) if part == 1 else active.tail(600)

        spot_dict = dict(zip(df['代码'].astype(str), df['最新价']))

        hits = []
        total_stocks = len(batch)
        print(f"📊 开始扫描 {total_stocks} 只股票...")
        
        for i, (_, row) in enumerate(batch.iterrows(), 1):
            stock_name = row['名称']
            stock_code = row['代码']
            print(f"🔄 正在扫描 {i}/{total_stocks}: {stock_name}({stock_code})")
            
            if check_strategy(stock_code, stock_name, spot_dict):
                hits.append({"name": stock_name, "code": stock_code, "amount": row['成交额']})

        print(f"✅ 扫描完成，找到 {len(hits)} 只符合策略的股票")
        with open(f"hits_part{part}.json", "w", encoding="utf-8") as f:
            json.dump(hits, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
