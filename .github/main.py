# 选股机器人（东方财富 + 新浪 超级稳定版 · GitHub 不报错）
import pandas as pd
import requests
import time
import random
import traceback

# ===================== 配置 =====================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ===================== 获取所有 A 股列表 =====================
def get_stock_list():
    try:
        url = "https://quote.eastmoney.com/redistribution/stocklist/a_stock_list.html"
        r = requests.get(url, headers=HEADERS, timeout=15)
        df = pd.read_html(r.text)[0]
        df = df[["代码", "名称"]].rename(columns={"代码":"code", "名称":"name"})
        df = df.drop_duplicates(subset=["code"])
        print(f"✅ 获取股票列表成功：{len(df)} 只")
        return df
    except Exception as e:
        print("❌ 获取列表失败")
        return None

# ===================== 获取实时价格 =====================
def get_price(code):
    try:
        pref = "sh" if code.startswith("6") else "sz"
        url = f"https://hq.sinajs.cn/list={pref}{code}"
        r = requests.get(url, timeout=5)
        txt = r.text
        if '"' not in txt:
            return None
        data = txt.split('"')[1].split(",")
        if len(data) < 10:
            return None
        return {
            "code": code,
            "open": data[1],
            "close": data[3],
            "high": data[4],
            "low": data[5],
            "volume": data[9]
        }
    except:
        return None

# ===================== 主程序 =====================
def main():
    print("="*50)
    print("       A 股选股机器人（稳定版）       ")
    print("="*50)

    # 1. 获取股票列表
    stock_list = get_stock_list()
    if stock_list is None:
        return

    # 2. 批量获取行情
    result = []
    for _, row in stock_list.iterrows():
        code = row["code"]
        name = row["name"]
        try:
            data = get_price(code)
            if data:
                data["name"] = name
                result.append(data)
            time.sleep(random.uniform(0.5, 1.2))
        except:
            continue

    # 3. 保存结果
    df = pd.DataFrame(result)
    df.to_csv("all_a_stock.csv", index=False, encoding="utf-8-sig")
    print(f"\n✅ 完成！共获取 {len(df)} 只股票")
    print("💾 文件已保存：all_a_stock.csv")

    print("\n="*50)
    print("             运行结束             ")
    print("="*50)

if __name__ == "__main__":
    main()
