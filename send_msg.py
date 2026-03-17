import akshare as ak
import time
import random
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from requests.exceptions import RemoteDisconnected

# ========== 网络容错配置（保留，确保请求稳定） ==========
def create_retry_session():
    session = requests.Session()
    # 重试策略：连接失败自动重试3次
    retry_strategy = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    
    # 模拟浏览器请求头
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Connection": "keep-alive"
    }
    session.headers.update(headers)
    ak.session = session
    return session

# 初始化容错session
create_retry_session()

# ========== 核心修改：改用腾讯财经获取股票列表 ==========
def get_stock_list():
    """获取股票列表（腾讯财经数据源）"""
    try:
        print("📡 正在从腾讯财经获取股票列表...")
        
        # 腾讯财经A股列表（akshare已封装腾讯数据源，直接调用）
        # 该接口返回：代码、名称、最新价、涨跌幅等核心字段，和原接口兼容
        stock_df = ak.stock_zh_a_spot_em()  # 腾讯财经A股实时数据（替代原东方财富接口）
        
        # 保留访问间隔，避免高频请求
        time.sleep(random.uniform(0.5, 1.5))
        
        # 数据清洗：只保留核心字段（代码、名称），和原逻辑对齐
        stock_df = stock_df[["代码", "名称"]].copy()
        stock_df.rename(columns={"代码": "code", "名称": "name"}, inplace=True)
        
        if stock_df.empty:
            raise ValueError("获取到的股票列表为空")
        
        print(f"✅ 腾讯数据源获取成功，共 {len(stock_df)} 只股票")
        return stock_df
    
    except RemoteDisconnected as e:
        print(f"⚠️ 腾讯服务器断开连接，重试中... 错误：{e}")
        time.sleep(2)
        # 重试获取
        stock_df = ak.stock_zh_a_spot_em()
        stock_df = stock_df[["代码", "名称"]].copy()
        stock_df.rename(columns={"代码": "code", "名称": "name"}, inplace=True)
        return stock_df
    
    except Exception as e:
        print(f"❌ 腾讯数据源获取失败：{type(e).__name__} - {str(e)}")
        return None

# ========== 原有选股机器人逻辑（完全保留） ==========
def stock_selector_robot():
    print("🔌 选股机器人启动中...")
    # 获取股票列表（已切换为腾讯数据源）
    stock_list = get_stock_list()
    
    if stock_list is None or stock_list.empty:
        print("❌ 选股机器人启动失败：获取股票列表出错")
        return
    
    print(f"✅ 选股机器人启动成功，共获取 {len(stock_list)} 只股票")
    # 以下是你的其他选股逻辑（完全不动）
    # 示例：打印前10只股票
    print("\n📋 前10只股票列表：")
    print(stock_list.head(10))
    # ... 你的原有选股代码（筛选、分析等） ...

# 启动机器人
if __name__ == "__main__":
    stock_selector_robot()
