import pandas as pd
import requests

# ===================== Server 酱 配置（已填你的 SendKey） =====================
SCKEY = "SCT329835TUs01r9DcURIUMdoAORtVUnbi"

def send_server(title, content):
    try:
        url = f"https://sctapi.ftqq.com/{SCKEY}.send"
        data = {
            "title": title,
            "desp": content
        }
        requests.post(url, data=data, timeout=8)
    except:
        # 不影响主程序，推送失败也不会报错
        pass

# ===================== 极速获取A股列表（官方接口，永不卡） =====================
def get_stock_list():
    try:
        # 极速接口：沪市+深市主板
        url = "https://60.push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": "1",
            "pz": "5000",
            "po": "1",
            "np": "1",
            "ut": "bd1d9ddb040897dfcf2f7f9a72521854",
            "fltt": "2",
            "invt": "2",
            "fid": "f3",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields": "f12,f14"
        }
        res = requests.get(url, params=params, timeout=10)
        data = res.json()

        df = pd.DataFrame([{
            "code": x["f12"],
            "name": x["f14"]
        } for x in data["data"]["diff"]])

        # ===================== 自动过滤 =====================
        # 排除创业板(300/301)、科创板(688)、北交所(8开头)
        df = df[~df["code"].str.startswith(("300", "301", "688", "8"))]
        # 排除ST、*ST
        df = df[~df["name"].str.contains("ST|\\*ST", na=False)]

        print(f"✅ 获取成功：{len(df)} 只股票（已过滤全部垃圾票）")
        return df

    except Exception as e:
        print(f"❌ 错误：{e}")
        return None

# ===================== 主程序 =====================
def stock_selector_robot():
    print("="*50)
    print("       选股机器人（秒出结果版）       ")
    print("="*50)

    df = get_stock_list()
    if df is None:
        send_server("⚠️ 选股机器人报错", "获取股票数据失败")
        return

    print("\n📊 前10只股票：")
    print(df.head(10).to_string(index=False))

    # 科技股筛选
    tech = df[df["name"].str.contains("科技", na=False)]
    print(f"\n🔍 科技股：{len(tech)} 只")
    if not tech.empty:
        print(tech.head(10).to_string(index=False))

    # ===================== 自动推送微信 =====================
    msg = f"✅ 选股机器人运行成功\n\n"
    msg += f"📊 有效股票总数：{len(df)} 只\n"
    msg += f"🔍 科技股总数：{len(tech)} 只\n\n"
    msg += "📌 前10只股票：\n"
    msg += df.head(10).to_string(index=False)
    
    if not tech.empty:
        msg += "\n\n🔬 前10只科技股：\n"
        msg += tech.head(10).to_string(index=False)

    send_server("📈 选股机器人", msg)

    print("\n" + "="*50)
    print("                 运行成功                 ")
    print("="*50)

if __name__ == "__main__":
    stock_selector_robot()
