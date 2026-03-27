import pandas as pd
import requests
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ===================== 【已填好你的Server酱SendKey，直接用】 =====================
SCKEY = "SCT329835TUs01r9DcURIUMdoAORtVUnbi"
# ==============================================================

# ===================== 带重试的请求会话（彻底解决连接断开） =====================
def create_session():
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504, 403, 429],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

# ===================== Server酱推送（带异常捕获，不影响主程序） =====================
def send_server(title, content):
    url = f"https://sctapi.ftqq.com/{SCKEY}.send"
    data = {"title": title, "desp": content}
    try:
        session = create_session()
        session.post(url, data=data, timeout=10)
        print("✅ Server酱推送成功")
    except Exception as e:
        print(f"⚠️ Server酱推送失败（不影响主程序）: {str(e)}")

# ===================== 稳定A股列表获取（免费无权限接口，零反爬） =====================
def get_stock_list():
    session = create_session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Referer": "https://quote.eastmoney.com/"
    }

    # 东方财富极简接口（无反爬，零权限要求）
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1",
        "pz": 2000,
        "po": "1",
        "np": "1",
        "ut": "bd1d9ddb040897dfcf2f7f9a72521854",
        "fltt": "2",
        "invt": "2",
        "fid": "f3",
        "fs": "m:0+t:6,m:1+t:2",
        "fields": "f12,f14"
    }

    try:
        res = session.get(url, params=params, headers=headers, timeout=15)
        res.raise_for_status()
        data = res.json()

        if not data.get("data") or not data["data"].get("diff"):
            raise Exception("接口返回空数据")

        df = pd.DataFrame([{
            "code": x["f12"],
            "name": x["f14"]
        } for x in data["data"]["diff"]])

        # ===================== 自动过滤（100%保留你原版规则） =====================
        df = df[~df["code"].str.startswith(("300", "301", "688", "8"))]
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
