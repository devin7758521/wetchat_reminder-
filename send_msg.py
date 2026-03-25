# 选股机器人（无akshare·GitHub稳定版）
import time
import random
import requests
import traceback
import pandas as pd
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from requests.exceptions import RequestException

# ===================== 配置 =====================
MAX_RETRY = 3
RETRY_INTERVAL = 0.5
REQUEST_INTERVAL = (0.5, 1.2)
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 20

# ===================== 网络会话 =====================
def init_request_session():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    session = requests.Session()
    retry_strategy = Retry(
        total=MAX_RETRY,
        backoff_factor=RETRY_INTERVAL,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(headers)
    return session

session = init_request_session()

# ===================== 获取所有A股 =====================
def get_stock_list():
    for attempt in range(MAX_RETRY):
        try:
            url = "https://quote.eastmoney.com/redistribution/stocklist/a_stock_list.html"
            r = session.get(url, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
            df = pd.read_html(r.text)[0]
            df = df[["代码", "名称"]].rename(columns={"代码":"code", "名称":"name"})
            df = df.drop_duplicates(subset=["code"])
            print(f"✅ 获取股票列表成功：{len(df)} 只")
            return df
        except Exception as e:
            print(f"⚠️ 第{attempt+1}次获取列表失败")
            time.sleep(1)
    print("❌ 获取列表失败")
    return None

# ===================== 选股机器人主逻辑 =====================
def stock_selector_robot():
    print("="*50)
    print("       选股机器人（无akshare稳定版）       ")
    print("="*50)

    try:
        stock_list = get_stock_list()
        if stock_list is None or stock_list.empty:
            print("\n❌ 无法获取股票列表")
            return

        print("\n✅ 启动成功！")
        print(f"📊 共 {len(stock_list)} 只A股")
        print("\n📋 前10只股票：")
        print(stock_list.head(10).to_string(index=False))

        tech_stocks = stock_list[stock_list["name"].str.contains("科技", na=False)]
        if not tech_stocks.empty:
            print(f"\n🔍 含'科技'股票共 {len(tech_stocks)} 只：")
            print(tech_stocks.to_string(index=False))
        else:
            print("\n🔍 未找到含'科技'的股票")

    except Exception as e:
        print(f"\n❌ 运行异常：{e}")
        traceback.print_exc()

    print("\n" + "="*50)
    print("             运行结束             ")
    print("="*50)

# ===================== 启动 =====================
if __name__ == "__main__":
    stock_selector_robot()
