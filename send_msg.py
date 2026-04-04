import pandas as pd
import requests
import akshare as ak
import time
import sys
import os
import json
import re
from datetime import datetime, timedelta
from langchain.tools import Tool
from langchain.agents import initialize_agent, AgentType
from langchain_google_genai import GoogleGenerativeAI  # 使用Gemini的LangChain集成

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
        top_news = news_df['新闻标题'].head(3).tolist()  # 修正：使用方括号
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
        
        # 防封杀重试机制
        df_daily = pd.DataFrame()
        for attempt in range(2):
            try:
                df_daily = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq", start_date=start_date)
                break
            except Exception as net_err:
                if "RemoteDisconnected" in str(net_err) or "Connection aborted" in str(net_err):
                    print(f"⚠️ {name}({code}): 网络被断开，休息2秒后重试...")
                    time.sleep(2)
                else:
                    raise net_err
        
        if df_daily.empty:
            print(f"❌ {name}({code}): 获取不到历史数据")
            return False
        
        # 统一index为DatetimeIndex
        if isinstance(df_daily.index, pd.DatetimeIndex):
            pass
        elif '日期' in df_daily.columns:
            df_daily['日期'] = pd.to_datetime(df_daily['日期'])
            df_daily = df_daily.set_index('日期')
        else:
            print(f"❌ {name}({code}): 找不到日期列！现有列名={list(df_daily.columns)}")
            return False
        
        # 价格获取
        today = datetime.now().date()
        latest_hist_date = df_daily.index[-1].date()
        
        if code in realtime_spot_dict and latest_hist_date == today:
            curr_price = realtime_spot_dict[code]
            print(f"💰 {name}({code}): 盘中实时价 {curr_price:.2f}")
        else:
            curr_price = df_daily['收盘'].iloc[-1]
            status_msg = "休市/盘后" if latest_hist_date != today else "收盘价"
            print(f"💰 {name}({code}): {status_msg} {curr_price:.2f} (截至:{latest_hist_date})")  # 补充右括号
        
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
    
    # 初始化Gemini LLM
    llm = GoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=GEMINI_KEY)
    
    # 构造prompt
    prompt = (
        f"你是具备全球视野的首席投资官。当前北京时间 {now_str} {period_tag}。\n"
        f"以下是本周（周一至周四）选出的四星以上标的名单：\n\n"
        f"【本周四星以上标的】：\n"
        + "\n".join(f"- {stock['name']}({stock['code']})" for stock in weekly_stars)
        + "\n\n"
        f"【决策维度】：\n"
        f"1. **综合评级**：基于本周表现和当前市场环境，重新评定星级（5星严格限制在1-2只）。\n"
        f"2. **短期走势**：预测下周走势，给出买入/持有/卖出建议。\n"
        f"3. **风险提示**：指出潜在风险（如政策、业绩）。\n\n"
        f"【输出要求】：\n"
        f"   - 🌟🌟... 股票名(代码) + 30字内深度分析（必须结合本周表现和当前环境）。\n"
        f"   - 未获星标的：仅在下方显示\"代码 名称\"。\n\n"
        f"【待优化标的】：\n"
        + "\n".join(f"- {stock['name']}({stock['code']})" for stock in weekly_stars)
    )

    try:
        response = llm.invoke(prompt)
        send_wechat(f"🌟 周五优化决策报告\n时间: {now_str}\n\n{response}\n\n📊 本周四星以上标的总数: {len(weekly_stars)}")
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

        top_hits = sorted(all_hits, key=lambda x: x['amount'], reverse=True)[:10]  # 取前10只

        # 初始化LangChain Agent
        llm = GoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=GEMINI_KEY)
        tools = [
            Tool(
                name="check_strategy",
                func=lambda code, name, realtime_spot_dict: check_strategy(code, name, realtime_spot_dict),
                description="检查股票是否符合策略（价格3-70 + 周线量能粘合 + 5周均量向上 + 站稳25周线）"
            ),
            Tool(
                name="get_stock_news",
                func=lambda code: get_stock_news(code),
                description="获取指定股票的最近3条核心新闻标题"
            )
        ]
        agent = initialize_agent(
            tools=tools,
            llm=llm,
            agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
            verbose=True
        )

        # 构造prompt，让Agent智能调用工具
        prompt = (
            f"你是具备全球视野的首席投资官。当前北京时间 {now_str} {period_tag}。\n"
            f"以下是 10 只量能突破标的：\n\n"
            f"【待分析标的】：\n"
            + "\n".join(f"- {stock['name']}({stock['code']})" for stock in top_hits)
            + "\n\n"
            f"【任务】：\n"
            f"1. 选择其中3只最值得分析的股票（基于成交额和策略符合度）。\n"
            f"2. 对选中的股票，调用`get_stock_news`获取新闻。\n"
            f"3. 基于新闻和策略，给出深度分析。\n"
        )

        try:
            response = agent.run(prompt)
            send_wechat(f"🌟 {period_tag} 深度决策报告\n时间: {now_str}\n\n{response}")
            
            # 提取星级股票并保存
            stars = []
            for line in response.split('\n'):
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
        
        # 增加延迟，减少AKShare调用频率
        for i, (_, row) in enumerate(batch.iterrows(), 1):
            stock_name = row['名称']
            stock_code = row['代码']
            print(f"🔄 正在扫描 {i}/{total_stocks}: {stock_name}({stock_code})")
            
            if check_strategy(stock_code, stock_name, spot_dict):
                hits.append({"name": stock_name, "code": stock_code, "amount": row['成交额']})
            
            time.sleep(0.3)  # 增加延迟，降低封禁风险

        print(f"✅ 扫描完成，找到 {len(hits)} 只符合策略的股票")
        with open(f"hits_part{part}.json", "w", encoding="utf-8") as f:
            json.dump(hits, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
