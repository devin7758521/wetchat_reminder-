import os
import sys
import requests
from google import genai

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
            send_wechat("❌ 错误：GitHub Secrets 中未配置 GEMINI_API_KEY")
            return

        # 初始化新版 Client
        client = genai.Client(api_key=GEMINI_KEY)
        
        try:
            # 修正点：直接使用 'gemini-1.5-flash'，新版 SDK 会自动处理前缀
            response = client.models.generate_content(
                model='gemini-1.5-flash', 
                contents="你好！请用20字点评一下今日A股半导体板块的表现。"
            )
            
            if response and response.text:
                send_wechat(f"🚀 AI 连通测试成功！\n\n点评内容：\n{response.text.strip()}")
            else:
                send_wechat("⚠️ AI 响应为空，请检查 API 额度。")
                
        except Exception as e:
            # 捕获详细报错以便排查
            error_msg = str(e)
            send_wechat(f"❌ AI 调用最终失败\n报错信息：{error_msg[:150]}")

if __name__ == "__main__":
    main()
