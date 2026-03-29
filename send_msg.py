import os
import sys
import requests
import json

# 配置
WEB_KEY = os.environ.get("WECHAT_WEBHOOK_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

def send_wechat(text):
    if not WEB_KEY: return
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEB_KEY}"
    try:
        requests.post(url, json={"msgtype": "text", "text": {"content": text}}, timeout=10)
    except: pass

def main():
    if len(sys.argv) < 2: return
    mode = sys.argv[1]

    if mode == "summary":
        if not GEMINI_KEY:
            send_wechat("❌ 错误：未配置 GEMINI_API_KEY")
            return

        # 核心修正：使用原生 HTTP POST 请求，手动指定 v1 版本 (避开 v1beta)
        api_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
        
        headers = {'Content-Type': 'application/json'}
        payload = {
            "contents": [{
                "parts": [{"text": "你好！请用15字点评今日A股行情。"}]
            }]
        }

        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=20)
            res_data = response.json()

            # 解析原生返回结果
            if "candidates" in res_data:
                ai_text = res_data["candidates"][0]["content"]["parts"][0]["text"]
                send_wechat(f"🚀 AI 原生连通成功！\n\n点评：{ai_text.strip()}")
            else:
                # 如果还是报错，把完整的 API 错误发回微信
                send_wechat(f"❌ API 响应异常：\n{json.dumps(res_data)}")
                
        except Exception as e:
            send_wechat(f"❌ 请求发生异常：{str(e)[:100]}")

if __name__ == "__main__":
    main()
