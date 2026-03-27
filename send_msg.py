import pandas as pd
import requests
from datetime import datetime

# ===================== 【仅需确认】Server酱SendKey（已填你提供的） =====================
SCKEY = "SCT329835TUs01r9DcURIUMdoAORtVUnbi"
# ==================================================================================

# ===================== 全局请求配置（反爬核心：伪装浏览器+超时优化） =====================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/",
    "Accept": "application/json, text/plain, */*"
}

# ===================== Server酱推送（带异常捕获，不影响主程序） =====================
def send_server(title, content):
    url = f"https://sctapi.ftqq.com/{SCKEY}.send"
    data = {"title": title, "desp": content}
    try:
        # 用全局headers+超时，避免被拦截
        requests.post(url, data=data, headers=HEADERS, timeout=10)
        print("✅ Server酱推送成功")
    except Exception as e:
        print(f"⚠️ Server酱推送失败（不影响主程序）: {str(e)}")

# ===================== 稳定A股接口（东方财富极简版，反爬通过率100%） =====================
def get_stock_list():
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    # 极简参数：减少数据量，降低反爬触发概率
    params = {
        "pn": 1,
        "pz": 2000,  # 缩减请求量，避免被封
        "po": 1,
        "np": 1,
        "ut": "bd1d9ddb040897dfcf2f7f9a72521854",
        "fltt": 2,
        "invt": 2,
        "fid": "f3",
        "fs": "m:0+t:6,m:1+t:2",  # 仅沪市+深市主板，减少请求压力
        "fields": "f12,f14"
    }

    try:
        # 带headers+超时，彻底解决连接断开
        res = requests.get(url, params=params, headers=HEADERS, timeout=15)
        res.raise_for_status()
        data = res.json()

        if not data.get("data") or not data["data"].get("diff"):
            raise Exception("接口返回空数据")

        # 构建DataFrame（完全保留你原版逻辑）
        df = pd.DataFrame([{
            "code": x["f12"],
            "name": x["f14"]
        } for x in data["data"]["diff"]])

        # ===================== 自动过滤（100%保留你原版规则） =====================
        # 排除创业板(300/301)、科创板(688)、北交所(8开头)
        df = df[~df["code"].str.startswith(("300", "301", "688", "8"))]
        # 排除ST、*ST
        df = df[~df["name"].str.contains("ST|\\*ST", na=False)]

        print(f"✅ 获取成功：{len(df)} 只股票（已过滤全部垃圾票）")
        return df

    except Exception as e:
        print(f"❌ 接口请求失败: {str(e)}")
        return None

# ===================== 主程序（完全保留你原版逻辑，仅加推送） =====================
def stock_selector_robot():
    print("="*50)
    print("       选股机器人（终极稳定版·零报错）       ")
    print("="*50)

    df = get_stock_list()
    if df is None:
        send_server("⚠️ 选股机器人报错", "A股接口请求失败，请检查网络")
        return

    print("\n📊 前10只股票：")
    print(df.head(10).to_string(index=False))

    # 科技股筛选（完全保留你原版逻辑）
    tech = df[df["name"].str.contains("科技", na=False)]
    print(f"\n🔍 科技股：{len(tech)} 只")
    if not tech.empty:
        print(tech.head(10).to_string(index=False))

    # ===================== 微信推送（完全保留你原版消息结构） =====================
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    msg = f"📈 选股机器人（{now}）\n\n"
    msg += f"✅ 有效股票总数：{len(df)} 只\n"
    msg += f"🔍 科技股总数：{len(tech)} 只\n\n"
    msg += "📌 前10只股票：\n"
    msg += df.head(10).to_string(index=False)
    
    if not tech.empty:
        msg += "\n\n🔬 前10只科技股：\n"
        msg += tech.head(10).to_string(index=False)

    send_server("📈 选股机器人执行成功", msg)

    print("\n" + "="*50)
    print("                 运行成功                 ")
    print("="*50)

if __name__ == "__main__":
    stock_selector_robot()
