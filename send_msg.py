import os
import sys
import requests
from google import genai  # 确保使用的是新版库

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
            send_wechat("❌ 错误：GitHub Secrets 中未检测到 GEMINI_API_KEY")
            return

        # 初始化新版 Client (不指定版本，让 SDK 自动匹配)
        client = genai.Client(api_key=GEMINI_KEY)
        
        try:
            # 关键修正：直接写模型名，不要加 'models/' 前缀
            response = client.models.generate_content(
                model='gemini-1.5-flash', 
                contents="你好！请用20字点评一下今日A股市场的整体情绪。"
            )
            
            if response and hasattr(response, 'text'):
                send_wechat(f"🚀 AI 连通测试成功！\n\n点评内容：\n{response.text.strip()}")
            else:
                send_wechat("⚠️ AI 响应内容为空，请检查 API 额度或账户状态。")
                
        except Exception as e:
            # 打印出更完整的报错信息
            send_wechat(f"❌ AI 再次调用失败\n详细报错：{str(e)[:150]}")

if __name__ == "__main__":
    main()
