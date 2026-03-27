import pandas as pd
import requests
from datetime import datetime
import akshare as ak

# ===================== 【已填好你的企业微信key】 =====================
WEBHOOK_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=da748662-f3d1-4edd-8031-2ee05c428605"
# ====================================================================

# ===================== 微信推送（完整内容正常显示） =====================
def send_wechat(content):
    try:
        data = {
            "msgtype": "text",
            "text": {
                "content": content
            }
        }
        requests.post(WEBHOOK_URL, json=data, timeout=15)
        print("✅ 推送成功")
    except:
        print("⚠️ 推送失败")

# ===================== 5日均量线上穿60日均量线 =====================
def check_volume_cross(code):
    try:
        df = ak.stock_zh_a_daily(symbol=code, adjust="hfq", count=120)
        if len(df) < 60:
            return False
        
        df["vol_ma5"] = df["volume"].rolling(5).mean()
        df["vol_ma60"] = df["volume"].rolling(60).mean()

        return df["vol_ma5"].iloc[-2] < df["vol_ma60"].iloc[-2] and \
               df["vol_ma5"].iloc[-1] > df["vol_ma60"].iloc[-1]
    except:
        return False

# ===================== 选股 =====================
def get_selected_stocks():
    try:
        df = ak.stock_zh_a_spot()

        # 只留主板 60 / 00 / 001
        df = df[df["代码"].str.match(r'^(60|00|001)')]

        # 排除不需要的
        df = df[~df["代码"].str.startswith(("9", "300", "301", "688", "8"))]
        df = df[~df["名称"].str.contains("ST|\*ST", na=False)]

        # 只保留：5日均量金叉
        df["vol_ok"] = df["代码"].apply(check_volume_cross)
        df = df[df["vol_ok"] == True]

        df = df.rename(columns={"代码": "code", "名称": "name"})
        return df[["code", "name"]]

    except Exception as e:
        return pd.DataFrame()

# ===================== 主程序 =====================
def main():
    print("开始选股...")
    res = get_selected_stocks()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    content = f"【选股结果】{now}\n\n"
    content += "筛选条件：\n"
    content += "1. 主板A股（60/00/001）\n"
    content += "2. 非ST、非创业板/科创板/北交所/B股\n"
    content += "3. 5日均量线上穿60日均量线\n\n"

    if res.empty:
        content += "✅ 今日无符合条件股票"
    else:
        content += f"符合条件共：{len(res)} 只\n\n"
        for _, row in res.iterrows():
            content += f"{row['code']}  {row['name']}\n"

    print(content)
    send_wechat(content)

if __name__ == "__main__":
    main()
