# 选股机器人（带微信推送·终极稳定版）
import pandas as pd
import requests
import json

# ===================== 【关键：企业微信机器人配置】 =====================
WECHAT_WEBHOOK_KEY = "da748662-f3d1-4edd-8031-2ee05c428605"
WECHAT_WEBHOOK_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=da748662-f3d1-4edd-8031-2ee05c428605"

# ===================== 发送微信消息 =====================
def send_wechat_msg(content):
    headers = {"Content-Type": "application/json"}
    data = {
        "msgtype": "text",
        "text": {
            "content": content,
            "mentioned_list": ["@all"]
        }
    }
    try:
        response = requests.post(WECHAT_WEBHOOK_URL, headers=headers, data=json.dumps(data), timeout=10)
        result = response.json()
        if result["errcode"] == 0:
            print("✅ 微信消息发送成功")
        else:
            print(f"❌ 微信消息发送失败：{result}")
    except Exception as e:
        print(f"❌ 微信请求异常：{e}")

# ===================== 极速获取A股列表 =====================
def get_stock_list():
    try:
        url = "https://60.push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": "1", "pz": "5000", "po": "1", "np": "1",
            "ut": "bd1d9ddb040897dfcf2f7f9a72521854",
            "fltt": "2", "invt": "2", "fid": "f3",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields": "f12,f14"
        }
        res = requests.get(url, params=params, timeout=10)
        data = res.json()

        df = pd.DataFrame([{"code": x["f12"], "name": x["f14"]} for x in data["data"]["diff"]])

        # 过滤：ST/创业板/科创板/北交所
        df = df[~df["code"].str.startswith(("300", "301", "688", "8"))]
        df = df[~df["name"].str.contains("ST|\\*ST", na=False)]

        print(f"✅ 获取成功：{len(df)} 只股票（已过滤）")
        return df
    except Exception as e:
        print(f"❌ 获取列表失败：{e}")
        return None

# ===================== 主程序 =====================
def stock_selector_robot():
    print("="*50)
    print("       选股机器人（带微信推送版）       ")
    print("="*50)

    df = get_stock_list()
    if df is None:
        send_wechat_msg("❌ 选股机器人运行失败：无法获取股票列表")
        return

    # 构造微信消息
    msg = f"📊 选股机器人运行成功\n✅ 共获取 {len(df)} 只A股（已过滤ST/创业/科创/北交所）\n\n📋 前10只股票：\n"
    msg += df.head(10).to_string(index=False)

    # 发送微信
    send_wechat_msg(msg)

    print("\n✅ 运行完成，微信已推送")
    print("\n" + "="*50)
    print("                 运行成功                 ")
    print("="*50)

if __name__ == "__main__":
    stock_selector_robot()
