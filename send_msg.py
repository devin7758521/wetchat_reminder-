import akshare as ak
import pandas as pd

# ===================== 全局配置 =====================
# 选股条件（可自行修改）
MIN_MARKET_CAP = 50  # 最小总市值（亿元）
MIN_PRICE = 1        # 最小股价（元）
MAX_PRICE = 100      # 最大股价（元）

def get_stock_list():
    """获取A股实时行情列表（无timeout参数，兼容所有版本）"""
    try:
        # 核心修复：完全移除timeout参数，使用最基础的调用方式
        stock_df = ak.stock_zh_a_spot_em()
        if stock_df.empty:
            raise ValueError("接口返回空数据")
        return stock_df
    except Exception as e:
        print(f"❌ 获取股票列表失败: {str(e)}")
        return None

def filter_stocks(stock_df):
    """按条件筛选股票（兼容不同版本akshare字段名）"""
    try:
        # 兼容不同版本的字段名映射
        col_map = {
            '总市值': 'market_cap',
            '市值': 'market_cap',
            '现价': 'price',
            '最新价': 'price',
            '股票代码': 'code',
            '代码': 'code',
            '股票名称': 'name',
            '名称': 'name'
        }
        stock_df = stock_df.rename(columns=col_map, errors='ignore')
        
        # 数据类型转换
        stock_df['market_cap'] = pd.to_numeric(stock_df['market_cap'], errors='coerce') / 10000  # 转成亿元
        stock_df['price'] = pd.to_numeric(stock_df['price'], errors='coerce')
        
        # 筛选条件
        mask = (
            (stock_df['market_cap'] >= MIN_MARKET_CAP) &
            (stock_df['price'] >= MIN_PRICE) &
            (stock_df['price'] <= MAX_PRICE)
        )
        filtered_df = stock_df[mask].sort_values('market_cap', ascending=False)
        return filtered_df
    except Exception as e:
        print(f"❌ 筛选股票失败: {str(e)}")
        return None

def run_bot():
    """选股机器人主函数"""
    print("🚀 选股机器人开始运行...")
    stock_list = get_stock_list()
    
    if stock_list is None or stock_list.empty:
        print("❌ 未获取到可筛选的股票列表")
        return  # 不再调用exit(1)，避免触发退出码1
    
    print(f"📊 成功获取股票列表，共{len(stock_list)}只")
    filtered_stocks = filter_stocks(stock_list)
    
    if filtered_stocks is None or filtered_stocks.empty:
        print("📉 未筛选出符合条件的股票")
    else:
        print(f"\n✅ 选股结果（共{len(filtered_stocks)}只）：")
        print("-" * 70)
        for _, row in filtered_stocks.head(20).iterrows():
            print(f"代码：{row['code']} | 名称：{row['name']} | 股价：{row['price']:.2f}元 | 市值：{row['market_cap']:.2f}亿元")
        print("-" * 70)
    
    print("\n🔚 选股机器人运行结束")

if __name__ == "__main__":
    run_bot()
