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
# 请确保 Webhook Key 正确
WEBHOOK_KEY = "da748662-f3d1-4edd-8031-2ee05c428605"
WEBHOOK_URL = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEBHOOK_KEY}"

def beijing_time():
    # 适配不同环境的时区处理
    return (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%m")

def send_wechat(content):
    """发送推送至企业微信"""
    try:
        data = {"msgtype": "text", "text": {"content": content}}
        print(f"📡 尝试推送微信... 目标Key后四位: {WEBHOOK_KEY[-4:]}")
        response = requests.post(WEBHOOK_URL, json=data, timeout=15)
        
        if response.status_code == 200 and '"errcode":0' in response.text:
            print("✅ 微信推送成功！")
        else:
            print(f"❌ 微信推送失败: {response.text}")
    except Exception as e:
        print(f"❌ 微信推送异常: {e}")

# ===================== 数据助手 =====================
def get_ai_brief(code):
    try:
        # 修正：akshare 个股信息获取
        info = ak.stock_individual_info_em(symbol=code)
        industry = info[info['item'] == '板块'].iloc[0]['value']
        return f"【行业】: {industry}"
    except:
        return "【行业】: 暂无数据"

# ===================== 核心：获取并筛选名单 =====================
def get_strictly_main_board():
    """获取主板个股并进行初步过滤"""
    try:
        print("📡 正在调用 AkShare 获取全量行情...")
        # 获取实时行情数据
        df = ak.stock_zh_a_spot_em()
        
        if df is None or df.empty:
            print("❌ 接口返回数据为空，请检查网络或 AkShare 版本")
            return pd.DataFrame()

        # 1. 统一列名（适配 AkShare 不同版本的差异）
        rename_dict = {
            '代码': 'code', '名称': 'name', 
            '最新价': 'price', '最新': 'price',
            '成交额': 'amount'
        }
        df.rename(columns=rename_dict, inplace=True)
        
        # 2. 格式化代码
        df['code'] = df['code'].astype(str).str.zfill(6)
        
        # 3. 基础过滤逻辑
        # 筛选：沪深主板(60, 00) + 排除ST
        mask = (df['code'].str.startswith(('60', '00'))) & \
               (~df['name'].astype(str).str.contains("ST|\\*ST", na=False))
        
        # 4. 数值筛选：价格 3-70元 & 成交额 > 6000万
        if 'price' in df.columns and 'amount' in df.columns:
            df['price'] = pd.to_numeric(df['price'], errors='coerce')
            df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
            mask &= (df['price'] > 3) & (df['price'] < 70) & (df['amount'] > 60000000)
        
        res = df[mask][['code', 'name']].copy()
        
        if not res.empty:
            print(f"✅ 成功筛选出候选股: {len(res)} 只")
            return res
        else:
            print("⚠️ 筛选后符合条件的个股数量为 0")
            return pd.DataFrame()

    except Exception as e:
        print(f"❌ 获取名单流程发生异常: {e}")
        return pd.DataFrame()

# ===================== 选股逻辑：周K + 均量粘合 + 股价 > MA25 =====================
def check_strategy(code, retries=2):
    for _ in range(retries):
        try:
            # 随机休眠防止 IP 被封
            time.sleep(random.uniform(0.2, 0.5))
            start_dt = (datetime.now() - timedelta(days=730)).strftime("%Y%m%d")
            
            # 获取周K数据（前复权）
            df = ak.stock_zh_a_hist(symbol=code, period="weekly", start_date=start_dt, adjust="qfq")
            
            if df is None or len(df) < 65: 
                return False

            # --- 1. 成交量逻辑 ---
            v_series = df['成交量'].astype(float)
            v_m5 = v_series.rolling(5).mean()
            v_m60 = v_series.rolling(60).mean()
            
            last_v5, prev_v5, pprev_v5 = v_m5.iloc[-1], v_m5.iloc[-2], v_m5.iloc[-3]
            last_v60 = v_m60.iloc[-1]

            # --- 2. 价格逻辑 (MA25) ---
            p_series = df['收盘'].astype(float)
            ma25 = p_series.rolling(25).mean()
            last_price = p_series.iloc[-1]
            last_ma25 = ma25.iloc[-1]

            if last_v60 <= 0 or pd.isna(last_ma25): 
                return False

            # --- 3. 核心条件判定 ---
            # 条件A: 5周均量与60周均量粘合 (偏离度3%以内)
            cond_bind = abs(last_v5 - last_v60) / last_v60 <= 0.03 
            # 条件B: 5周均量连续三周递增 (量能温和放大)
            cond_up = last_v5 > prev_v5 > pprev_v5                
            # 条件C: 现价站稳25周线
            cond_price = last_price > last_ma25                    
            
            return cond_bind and cond_up and cond_price
        except Exception:
            continue
    return False

# ===================== 主流程 =====================
def main():
    start_ts = time.time()
    now_str = beijing_time()
    
    # 1. 启动提醒
    send_wechat(f"🚀 [AI 选股机器人] 周K级别扫描开始\n时间: {now_str}\n范围: 沪深主板\n策略: 均量粘合+站上MA25")
    
    # 2. 获取股票池
    stocks = get_strictly_main_board()
    if stocks.empty:
        send_wechat("❌ 错误：个股列表获取为空，扫描终止。请检查 AkShare 接口状态。")
        return

    total = len(stocks)
    hit_list = []
    
    # 3. 遍历扫描
    print(f"🔍 开始逐一扫描 {total} 只个股...")
    for i, (_, row) in enumerate(stocks.iterrows()):
        code, name = row["code"], row["name"]
        
        if check_strategy(code):
            brief = get_ai_brief(code)
            hit_list.append(f"🎯 {code} {name}\n   {brief}")
            print(f"✅ 命中信号: {code} {name}")
        
        # 每扫描 100 只打印一次进度
        if (i + 1) % 100 == 0:
            print(f"⏳ 进度: {i+1}/{total} | 耗时: {int(time.time()-start_ts)}s")

    # 4. 汇总发送
    duration = int(time.time() - start_ts)
    msg = f"【周K量价扫描报告】\n时间: {beijing_time()}\n"
    msg += f"----------------------------\n"
    
    if hit_list:
        msg += f"🔥 共命中 {len(hit_list)} 只个股：\n\n" + "\n\n".join(hit_list)
    else:
        msg += "✅ 扫描完毕，当前无符合信号个股。"
    
    msg += f"\n----------------------------\n总扫描: {total} | 总耗时: {duration}s"
    
    send_wechat(msg)
    print("🏁 全部流程执行完毕。")

if __name__ == "__main__":
    main()
