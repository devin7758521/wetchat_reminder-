import requests
import json

# 替换成你的企业微信群机器人 Webhook 地址
WEBHOOK_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=da748662-f3d1-4edd-8031-2ee05c428605"

def send_wechat_msg():
    data = {
        "msgtype": "text",
        "text": {
            "content": "Plank时间到！该做平板支撑了！"
        }
    }
    response = requests.post(WEBHOOK_URL, data=json.dumps(data))
    print("发送结果:", response.json())

if __name__ == "__main__":
    send_wechat_msg()
