import pandas as pd
import requests
import akshare as ak
import warnings
import time
import os
import logging
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

VERSION = "v2026.03.28.Hotfix.v2"

WEB_KEY = os.environ.get("WECHAT_WEBHOOK_KEY")
WEBHOOK_URL = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEB_KEY}"

def send_wechat(content):
    """发送微信企业号消息"""
    if not WEB_KEY or not content:
        return False
    try:
        data = {"msgtype": "text", "text": {"content": content}}
        response = requests.post(WEBHOOK_URL, json=data, timeout=15)
        response.raise_for_status()
        logger.info("✅ WeChat 消息已发送")
        return True
    except requests.exceptions.Timeout:
        logger.error("❌ WeChat 发送超时 (15s)")
        return False
    except Exception as e:
        logger.error(f"❌ WeChat 发送异常: {type(e).__name__}: {e}")
        return False

def get_etf_list():
    """获取 ETF 列表，筛选成交额大于 1000 万"""
    try:
        df = ak.fund_etf_spot_em()
        df = df[df['成交额'] > 10000000]
        # 简单去重逻辑
        df['simple_name'] = df['名称'].str.extract(r'(.+?)(?:ETF|基金)')
        result = df.sort_values(by='成交额', ascending=False).drop_duplicates(subset=['simple_name'])
        logger.info(f"✅ 获取 ETF 列表: {len(result)} 只")
        return result
    except Exception as e:
        logger.error(f"❌ 获取 ETF 列表失败: {e}")
        return pd.DataFrame()

def check_etf_strategy(code):
    """
    ETF 量化策略：
    1. 周量能粘合 <= 3%
    2. 现价站稳 25 周线
    """
    try:
        time.sleep(0.5)
        df = ak.fund_etf_hist_em(symbol=code, period="weekly", adjust="qfq")
        if len(df) < 65:
            return False
        
        v_m5 = df['成交量'].rolling(5).mean()
        v_m60 = df['成交量'].rolling(60).mean()
        ma25 = df['收盘'].rolling(25).mean()
        
        # 防止除零
        if v_m60.iloc[-1] == 0:
            return False
        
        return (abs(v_m5.iloc[-1] - v_m60.iloc[-1]) / v_m60.iloc[-1] <= 0.03) and (df['收盘'].iloc[-1] > ma25.iloc[-1])
    except Exception as e:
        logger.debug(f"⚠️ ETF 策略检查失败 ({code}): {type(e).__name__}")
        return False

def main():
    """主函数"""
    logger.info(f"🚀 ETF 扫描启动 ({VERSION})")
    send_wechat(f"📊 [ETF 专项] 14:30 扫描启动 ({VERSION})")
    
    try:
        etfs = get_etf_list()
        if etfs.empty:
            logger.warning("⚠️ 未获取到 ETF 列表")
            send_wechat("⚠️ ETF 列表获取异常，请检查日志")
            return
        
        hits = []
        for _, row in etfs.iterrows():
            if check_etf_strategy(row['代码']):
                hits.append(f"💎 {row['名称']}({row['代码']})")
                logger.info(f"✅ 命中 ETF: {row['名称']}({row['代码']})")
        
        hit_count = len(hits)
        hit_msg = "\n".join(hits) if hits else "无信号"
        result_msg = f"✅ ETF 扫描完毕 ({VERSION})\n---\n{hit_msg}\n\n📊 共命中: {hit_count} 只"
        send_wechat(result_msg)
        logger.info(f"✅ ETF 扫描完毕，共命中 {hit_count} 只")
    except Exception as e:
        logger.error(f"❌ ETF 扫描异常: {e}")
        send_wechat(f"❌ ETF 扫描异常: {e}，请检查日志")

if __name__ == "__main__":
    main()