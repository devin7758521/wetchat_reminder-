import akshare as ak
import requests
import pandas as pd

# ===================== 全局配置（可根据需求调整） =====================
# 设置全局请求超时（适配akshare的超时配置）
ak.utils.set_timeout(10)
# 选股条件配置
MIN_MARKET_CAP = 50  # 最小总市值（单位：亿元）
MIN_PRICE = 1        # 最小股价（单位：元）
MAX_PRICE = 100      # 最大股价（单位：元）

def get_stock_list():
    """
    获取A股全市场实时行情列表（核心函数，修复timeout参数问题）
    返回：DataFrame | None
    """
    try:
        # 核心修复：移除不兼容的timeout参数，直接调用函数
        stock_df = ak.stock_zh_a_spot_em()
        
        # 数据清洗：过滤无效数据
        if stock_df.empty:
            raise ValueError("接口返回空数据")
        
        # 统一字段名（不同版本akshare字段名可能不同，做兼容）
        stock_df.rename(columns={
            '总市值': 'market_cap',
            '现价': 'price',
            '股票代码': 'code',
            '股票名称': 'name'
        }, inplace=True, errors='ignore')
        
        return stock_df
    
    except Exception as e:
        print(f"❌ 获取股票列表失败：{str(e)}")
        return None

def filter_stocks(stock_df):
    """
    按自定义条件筛选股票
    """
    try:
        # 1. 过滤市值（转换为亿元）
        stock_df['market_cap'] = pd.to_numeric(stock_df['market_cap'], errors='coerce') / 10000
        filter1 = stock_df['market_cap'] >= MIN_MARKET_CAP
        
        # 2. 过滤股价
        stock_df['price'] = pd.to_numeric(stock_df['price'], errors='coerce')
        filter2 = (stock_df['price'] >= MIN_PRICE) & (stock_df['price'] <= MAX_PRICE)
        
        # 3. 合并筛选条件
        filtered_df = stock_df[filter1 & filter2].copy()
        
        # 按市值降序排序
        filtered_df = filtered_df.sort_values('market_cap', ascending=False)
        
        return filtered_df
    
    except Exception as e:
        print(f"❌ 筛选股票失败：{str(e)}")
        return None

def print_stock_result(filtered_df):
    """
    格式化输出选股结果
    """
    if filtered_df is None or filtered_df.empty:
        print("📉 未筛选出符合条件的股票")
        return
    
    print(f"\n✅ 选股结果（共{len(filtered_df)}只）：")
    print("-" * 80)
    # 只展示核心字段
    result_df = filtered_df[['code', 'name', 'price', 'market_cap']].head(20)  # 只展示前20只
    for idx, row in result_df.iterrows():
        print(f"代码：{row['code']} | 名称：{row['name']} | 股价：{row['price']:.2f}元 | 市值：{row['market_cap']:.2f}亿元")
    print("-" * 80)

# ===================== 主程序入口 =====================
if __name__ == "__main__":
    print("🚀 选股机器人启动...")
    
    # 1. 获取全市场股票列表
    stock_list = get_stock_list()
    if stock_list is None or stock_list.empty:
        print("❌ 未获取到可筛选的股票列表，程序终止")
        exit(1)
    print(f"📊 成功获取A股列表，共{len(stock_list)}只股票")
    
    # 2. 执行选股逻辑
    filtered_stocks = filter_stocks(stock_list)
    
    # 3. 输出结果
    print_stock_result(filtered_stocks)
    
    print("\n🔚 选股机器人运行结束")
