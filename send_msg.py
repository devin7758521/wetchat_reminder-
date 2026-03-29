import os
import sys
import requests
import json

# 从 GitHub Secrets 获取变量
WEB_KEY = os.environ.get("WECHAT_WEBHOOK_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

def send_wechat(text):
    if not WEB_KEY: return
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEB_KEY}"
    try:
        requests.post(url, json={"msgtype": "text", "text": {"content": text}}, timeout=10)
    except Exception as e:
        print(f"微信发送失败: {e}")

def main():
    if len(sys.argv) < 2: return
    mode = sys.argv[1]

    if mode == "summary":
        if not GEMINI_KEY:
            send_wechat("❌ 错误：未在 Secrets 中配置 GEMINI_API_KEY")
            return

        # 使用你探测到的最新模型 ID
        model_id = "gemini-2.5-flash"
        api_url = f"https://generativelanguage.googleapis.com/v1/models/{model_id}:generateContent?key={GEMINI_KEY}"
        
        headers = {'Content-Type': 'application/json'}
        payload = {
            "contents": [{
                "parts": [{"text": "你好！这是一次连通性测试。请用15个字总结一下你作为 Gemini 2.5 的核心优势。"}]
            }]
        }

        try:
            print(f"正在请求模型: {model_id}...")
            response = requests.post(api_url, headers=headers, json=payload, timeout=20)
            res_data = response.json()

            if "candidates" in res_data:
                ai_text = res_data["candidates"][0]["content"]["parts"][0]["text"]
                send_wechat(f"🎉 Gemini 2.5 测试成功！\n\nAI 回复：\n{ai_text.strip()}")
            else:
                # 如果报错，把原始错误抓出来发到微信
                error_info = json.dumps(res_data.get("error", res_data))
                send_wechat(f"❌ AI 响应异常 (404/400):\n{error_info}")
                
        except Exception as e:
            send_wechat(f"❌ 请求发生物理异常：{str(e)[:100]}")

if __name__ == "__main__":
    main()
