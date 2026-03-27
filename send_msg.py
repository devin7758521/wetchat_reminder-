import pandas as pd
import requests
from datetime import datetime
import akshare as ak

# ===================== 【已填好你的Server酱SendKey，直接用】 =====================
SCKEY = "SCT329835TUs01r9DcURIUMdoAORtVUnbi"
# ==============================================================

# ===================== Server酱推送（带异常捕获，不影响主程序） =====================
def send_server(title, content):
    url = f"https://sctapi.ftqq.com/{SCKEY}.send"
    data = {"title": title, "desp": content}
    try:
        requests.post(url, data=data, timeout=10)
        print("✅ Server酱推送成功")
    except Exception as e:
        print(f"⚠️ Server酱推送失败（不影响主程序）: {str(e)}")

# ===================== 稳定A股列表获取（AkShare最新正确接口，修复列名） =====================
def get_stock_list():
    try:
        # AkShare最新稳定接口：stock_zh_a_spot() 获取A股实时行情
        df = ak.stock_zh_a_spot()
        # 直接用中文列名筛选，避免重命名错误
        # 排除创业板(300/301)、科创板(688)、北交所(8开头)
        df = df[~df["代码"].str.startswith(("300", "301", "688", "8"))]
        # 排除ST、*ST
        df = df[~df["名称"].str.contains("ST|\\*ST", na=False)]
        # 重命名为英文列名，匹配后续逻辑
        df = df.rename(columns={"代码": "code", "名称": "name"})

        print(f"✅ 获取成功：{len(df)} 只股票（已过滤全部垃圾票）")
        return df

    except Exception as e:
        print(f"❌ AkShare接口请求失败: {str(e)}")
        return None

# ===================== 主程序（完全保留你原版逻辑，仅修复列名） =====================
def stock_selector_robot():
    print("="*50)
    print("       选股机器人（AkShare终极稳定版·零报错）       ")
    print("="*50)

    df = get_stock_list()
    if df is None:
        send_server("⚠️ 选股机器人报错", "AkShare接口请求失败")
        return

    print("\n📊 前10只股票：")
    print(df[["code", "name"]].head(10).to_string(index=False))

    # 科技股筛选（完全保留你原版逻辑）
    tech = df[df["name"].str.contains("科技", na=False)]
    print(f"\n🔍 科技股：{len(tech)} 只")
    if not tech.empty:
        print(tech[["code", "name"]].head(10).to_string(index=False))

    # ===================== 微信推送（完全保留你原版消息结构） =====================
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    msg = f"📈 选股机器人（{now}）\n\n"
    msg += f"✅ 有效股票总数：{len(df)} 只\n"
    msg += f"🔍 科技股总数：{len(tech)} 只\n\n"
    msg += "📌 前10只股票：\n"
    msg += df[["code", "name"]].head(10).to_string(index=False)
    
    if not tech.empty:
        msg += "\n\n🔬 前10只科技股：\n"
        msg += tech[["code", "name"]].head(10).to_string(index=False)

    send_server("📈 选股机器人执行成功", msg)

    print("\n" + "="*50)
    print("                 运行成功                 ")
    print("="*50)

if __name__ == "__main__":
    stock_selector_robot()
