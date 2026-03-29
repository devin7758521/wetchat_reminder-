import os
import requests
import json

WEB_KEY = os.environ.get("WECHAT_WEBHOOK_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")

def send_wechat(text):
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEB_KEY}"
    requests.post(url, json={"msgtype": "text", "text": {"content": text}})

def main():
    if not GEMINI_KEY:
        send_wechat("❌ 未配置 GEMINI_API_KEY")
        return

    # 探测接口：列出该 Key 支持的所有模型
    list_url = f"https://generativelanguage.googleapis.com/v1/models?key={GEMINI_KEY}"
    
    try:
        response = requests.get(list_url, timeout=15)
        data = response.json()
        
        if "models" in data:
            # 提取前 5 个模型名称
            model_names = [m["name"].replace("models/", "") for m in data["models"][:8]]
            models_str = "\n".join(model_names)
            send_wechat(f"🔍 探测成功！你的 Key 支持以下模型：\n\n{models_str}\n\n请告诉我其中一个，我帮你填进代码。")
        else:
            send_wechat(f"❌ 探测失败，API 返回：\n{json.dumps(data)}")
    except Exception as e:
        send_wechat(f"❌ 网络请求异常：{str(e)}")

if __name__ == "__main__":
    main()
