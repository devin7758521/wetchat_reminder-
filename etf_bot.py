import pandas as pd
import requests
import akshare as ak
import os
import json
import re
from datetime import datetime

# 配置
VERSION = "v2026.03.29.CIO.V10"
WEB_KEY = os.environ.get("WECHAT_WEBHOOK_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

def send_wechat(content):
    if not WEB_KEY: return
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEB_KEY}"
    try:
        requests.post(url, json={"msgtype": "text", "text": {"content": content}}, timeout=10)
    except: pass

def check_strategy(code, name):
    """
    策略：周线量能粘合(±3%) + 站稳25周线
    """
    try:
        # ETF 专项数据接口
        df = ak.fund_etf_hist_em(symbol=code, period="weekly", adjust="qfq")
        if len(df) < 65: return False
        
        # 1. 计算量能指标
        v5 = df['成交量'].rolling(5).mean().iloc[-1]
        v60 = df['成交量'].rolling(60).mean().iloc[-1]
        
        # 2. 核心判定逻辑
        deviation = abs(v5 - v60) / v60
        is_binding = deviation <= 0.03                 # 粘合度在 3% 以内
        price_support = df['收盘'].iloc[-1] > df['收盘'].rolling(25).mean().iloc[-1] # 站稳25周线

        if is_binding and price_support:
            print(f"🎯 ETF命中: {name}({code}) | 偏离度:{deviation:.2%}")
            return True
        return False
    except: return False

def deduplicate_hits(hits):
    """
    ETF 行业去重逻辑：同一个行业或指数只保留成交额最大的 1 只
    核心关键词：300, 500, 半导体, 医疗, 白酒, 恒生, 纳斯达克 等
    """
    if not hits: return []
    
    # 按成交额从大到小排序
    hits_sorted = sorted(hits, key=lambda x: x['amount'], reverse=True)
    
    # 定义核心行业/指数关键词
    key_themes = [
        '300', '500', '1000', '50', '800', # 宽基指数
        '半导体', '芯片', '医疗', '医药', '白酒', '证券', '券商', '银行', '地产', '基础建设', '煤炭', # 核心行业
        '恒生', '纳斯达克', '标普', '德国', '日经', # 跨境指数
        '创业板', '科创板', '港股通' # 特殊板块
    ]
    
    deduped_hits = []
    seen_themes = set()
    
    for etf in hits_sorted:
        theme = '其他'
        # 提取标的的核心主题
        for t in key_themes:
            if t in etf['name']:
                theme = t
                break
        
        # 如果这个主题未被选取过，或者属于'其他'类，则选取
        if theme == '其他' or theme not in seen_themes:
            deduped_hits.append(etf)
            if theme != '其他':
                seen_themes.add(theme)
                
    # 返回去重后的 Top 10 名单
    return deduped_hits[:10]

def main():
    if not WEB_KEY: return
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    print("=== 开始 ETF CIO 专项扫描 ===")
    
    try:
        # 1. 获取所有 ETF 现货数据
        df_spot = ak.fund_etf_spot_em()
        all_hits = []
        
        # 2. 扫描成交额前 60 的主流 ETF，确保流动性
        for _, row in df_spot.sort_values(by='成交额', ascending=False).head(60).iterrows():
            print(f"检查 ETF: {row['名称']}...", end="\r")
            if check_strategy(row['代码'], row['名称']):
                all_hits.append({"name": row['名称'], "code": row['代码'], "amount": row['成交额']})
        
        if all_hits:
            # 3. 执行行业去重逻辑，选出去重后的 Top 10 
            top_10 = deduplicate_hits(all_hits)
            
            # 4. 首席 CIO 人设 + 宏观视野 Prompt
            api_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
            
            prompt = (
                f"你是具备全球视野的首席投资官(CIO)。当前时间 {now_str}。\n"
                f"以下 {len(top_10)} 只 ETF 在行业/指数中具备高流动性，且技术面出现周线量能粘合信号。\n\n"
                f"【你的职责】：\n"
                f"1. **宏观联动 (最高权重)**：优先结合当前【国内外宏观形势】（如：美联储货币政策、地缘局势、美元指数）分析该 ETF 板块的收益预期。\n"
                f"2. **配置建议**：从中选出你认为最值得配置的 1-2 只给🌟🌟🌟🌟🌟评分。其他标的仅用符号 🔹 显示。\n"
                f"3. **输出格式**：\n"
                f"   - 🌟🌟🌟 标的名字(代码)\n"
                f"     【配置点评】：[30字内简述宏观逻辑，必点核心背景]\n"
                f"   - 🔹 其余标的名(代码)\n\n"
                f"待分析名单：\n"
                + "\n".join([f"- {x['name']}({x['code']}), 成交额:{x['amount']/1e8:.2f}亿" for x in top_10])
            )
            
            try:
                # 增加了 timeout 确保联网检索不受限
                res = requests.post(api_url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60)
                ai_text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                
                # 5. 推送纯文本报告
                send_wechat(f"💎 ETF CIO 配置报告 ({VERSION})\n时间: {now_str}\n\n{ai_text}\n\n📊 今日信号池去重后总数: {len(top_10)}")
            except Exception as e:
                send_wechat(f"❌ AI 决策超时: {str(e)[:100]}")
        
        else:
            send_wechat(f"📅 {now_str}\n今日主流 ETF 中无粘合信号。")
            
    except Exception as e:
        print(f"ETF 专项任务异常: {e}")

if __name__ == "__main__": main()
