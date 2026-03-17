# 选股机器人（腾讯财经数据源 稳定版）
import akshare as ak
import time
import random
import requests
import traceback
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from requests.exceptions import RemoteDisconnected, RequestException

# ===================== 1. 全局配置（可根据需要微调） =====================
# 重试次数/间隔
MAX_RETRY = 3          # 最大重试次数
RETRY_INTERVAL = 0.5   # 重试间隔基数（秒）
REQUEST_INTERVAL = (1, 3)  # 随机请求间隔（秒）
# 超时设置
CONNECT_TIMEOUT = 10   # 连接超时（秒）
READ_TIMEOUT = 30      # 读取超时（秒）

# ===================== 2. 网络请求容错配置 =====================
def init_request_session():
    """初始化带重试/请求头的请求会话（核心：防反爬、防断连）"""
    # 模拟真实浏览器请求头
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Cache-Control": "max-age=0"
    }

    # 创建会话并配置重试策略
    session = requests.Session()
    retry_strategy = Retry(
        total=MAX_RETRY,
        backoff_factor=RETRY_INTERVAL,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    
    # 应用配置
    session.headers.update(headers)
    ak.session = session  # 让akshare使用该会话
    return session

# 初始化会话
session = init_request_session()

# ===================== 3. 腾讯数据源获取股票列表 =====================
def get_tencent_stock_list():
    """
    从腾讯财经获取A股列表
    返回：DataFrame（columns: code, name） | None
    """
    stock_df = None
    for attempt in range(1, MAX_RETRY + 1):
        try:
            print(f"\n【第 {attempt} 次尝试】获取腾讯财经A股列表...")
            
            # 调用腾讯A股实时数据接口（akshare最新稳定版）
            stock_df = ak.stock_zh_a_spot_qq()
            
            # 随机休眠，降低请求频率
            time.sleep(random.uniform(*REQUEST_INTERVAL))
            
            # 数据校验与清洗
            if stock_df.empty:
                raise ValueError("腾讯接口返回空数据")
            
            # 字段兼容（适配不同版本akshare的列名）
            column_mapping = {
                "代码": "code",
                "名称": "name",
                "证券代码": "code",
                "证券名称": "name"
            }
            # 重命名列名
            stock_df.rename(columns={k: v for k, v in column_mapping.items() if k in stock_df.columns}, inplace=True)
            
            # 只保留核心字段
            if "code" not in stock_df.columns or "name" not in stock_df.columns:
                raise KeyError(f"核心字段缺失，返回列名：{stock_df.columns.tolist()}")
            
            stock_df = stock_df[["code", "name"]].drop_duplicates()
            print(f"✅ 成功获取股票列表：共 {len(stock_df)} 只A股")
            return stock_df

        except RemoteDisconnected:
            print(f"⚠️ 第 {attempt} 次失败：腾讯服务器断开连接")
            time.sleep(RETRY_INTERVAL * 2)  # 延长间隔后重试
        except RequestException as e:
            print(f"⚠️ 第 {attempt} 次失败：网络请求错误 - {str(e)}")
            time.sleep(RETRY_INTERVAL * 2)
        except Exception as e:
            print(f"⚠️ 第 {attempt} 次失败：数据处理错误 - {type(e).__name__}: {str(e)}")
            traceback.print_exc()  # 打印详细错误栈
            time.sleep(RETRY_INTERVAL * 2)
    
    # 所有重试失败
    print("\n❌ 所有重试均失败，无法获取股票列表")
    return None

# ===================== 4. 选股机器人主逻辑 =====================
def stock_selector_robot():
    """选股机器人主函数"""
    print("="*50)
    print("        选股机器人（腾讯数据源）        ")
    print("="*50)
    
    try:
        # 1. 获取股票列表
        stock_list = get_tencent_stock_list()
        if stock_list is None or stock_list.empty:
            print("\n❌ 选股机器人启动失败：获取股票列表出错")
            return
        
        # 2. 成功启动（以下是你的选股逻辑，保留原有代码即可）
        print("\n✅ 选股机器人启动成功！")
        print(f"📊 股票列表总数：{len(stock_list)} 只")
        print("\n📋 前10只股票预览：")
        print(stock_list.head(10).to_string(index=False))
        
        # --------------------------
        # 这里添加你的选股逻辑（示例）
        # 比如：筛选市值>100亿的股票、筛选涨跌幅>3%的股票等
        # --------------------------
        # 示例：筛选名称含"科技"的股票
        tech_stocks = stock_list[stock_list["name"].str.contains("科技", na=False)]
        if not tech_stocks.empty:
            print(f"\n🔍 筛选出含'科技'的股票（共 {len(tech_stocks)} 只）：")
            print(tech_stocks.to_string(index=False))
        else:
            print("\n🔍 未筛选出含'科技'的股票")

    except Exception as e:
        print(f"\n❌ 选股机器人运行崩溃：{type(e).__name__} - {str(e)}")
        traceback.print_exc()
    finally:
        print("\n="*50)
        print("        选股机器人运行结束        ")
        print("="*50)

# ===================== 5. 启动入口 =====================
if __name__ == "__main__":
    # 先升级akshare（可选，确保接口兼容）
    try:
        import subprocess
        subprocess.run(["pip", "install", "--upgrade", "akshare", "-q"], check=True)
        print("✅ akshare已更新至最新版本")
    except:
        print("⚠️ akshare升级失败，使用当前版本继续运行")
    
    # 启动机器人
    stock_selector_robot()
