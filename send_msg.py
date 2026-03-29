import os
import sys
import json
import requests
from google import genai

# 配置
WEB_KEY = os.environ.get("WECHAT_WEBHOOK_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

def send_wechat(text):
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEB_KEY}"
    requests.post(url, json={"msgtype": "text", "text": {"content": text}})

def main():
    if len(sys.argv) < 2: return
    mode = sys.argv[1]

    # AI 汇总测试模式
    if mode == "summary":
        if not GEMINI_KEY:
            send_wechat("❌ 错误：未配置 GEMINI_API_KEY")
            return

        client = genai.Client(api_key=GEMINI_KEY)
        try:
            # 直接用一个简单的 Prompt 测试连通性
            response = client.models.generate_content(
                model="gemini-1.5-flash", 
                contents="你好！请用15字点评一下今日A股行情。"
            )
            send_wechat(f"🚀 AI 连通成功！\n点评：{response.text}")
        except Exception as e:
            send_wechat(f"❌ AI 调用失败：{str(e)[:100]}")

if __name__ == "__main__":
    main()
