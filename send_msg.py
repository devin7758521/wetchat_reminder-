import pandas as pd
import requests
import akshare as ak
import google.generativeai as genai
import time
import sys
import os
import json
from datetime import datetime

# ── 版本 ────────────────────────────────────────────────────────────────────
VERSION = "v2026.04.02.CIO.Pro"

# ── 环境变量 ─────────────────────────────────────────────────────────────────
WEB_KEY    = os.environ.get("WECHAT_WEBHOOK_KEY")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")


# ── 企业微信推送 ──────────────────────────────────────────────────────────────

def send_wechat(content: str):
    if not WEB_KEY:
        print("[WARN] WECHAT_WEBHOOK_KEY 未设置，跳过推送")
        return
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEB_KEY}"
    try:
        resp = requests.post(
            url,
            json={"msgtype": "text", "text": {"content": content}},
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[WARN] 微信推送失败: {e}")


# ── 个股新闻（内参模块）────────────────────────────────────────────────────────

def get_stock_news(code: str) -> str:
    """抓取东方财富个股最近 3 条新闻标题，作为 AI 分析的内参。"""
    try:
        news_df = ak.stock_news_em(symbol=code)
        if news_df is None or news_df.empty:
            return "暂无近期核心公告。"
        top_news = news_df["新闻标题"].head(3).tolist()
        return " | ".join(top_news)
    except Exception:
        return "新闻检索接口繁忙。"


# ── 周线策略判断 ──────────────────────────────────────────────────────────────

def check_strategy(code: str, name: str) -> dict | None:
    """
    策略条件：
      1. 价格区间 3~70 元（前复权）
      2. 成交量 5 周均线向上
      3. 量能偏离度 (V5 - V60) / V60 ∈ [-3%, +7%]（温和启动区间）
      4. 现价站上 25 周均线

    命中返回包含基础信息的 dict，否则返回 None。
    """
    try:
        df = ak.stock_zh_a_hist(symbol=code, period="weekly", adjust="qfq")
        if df is None or len(df) < 65:
            return None

        curr_price = df["收盘"].iloc[-1]
        if not (3.0 <= curr_price <= 70.0):
            return None

        v5   = df["成交量"].rolling(5).mean()
        v60  = df["成交量"].rolling(60).mean()
        ma25 = df["收盘"].rolling(25).mean()

        # NaN 防护
        if any(pd.isna(x) for x in [v5.iloc[-1], v5.iloc[-2], v60.iloc[-1], ma25.iloc[-1]]):
            return None

        vol_up        = v5.iloc[-1] > v5.iloc[-2]
        deviation     = (v5.iloc[-1] - v60.iloc[-1]) / v60.iloc[-1]
        is_binding    = -0.03 <= deviation <= 0.07
        price_support = curr_price > ma25.iloc[-1]

        if vol_up and is_binding and price_support:
            amount = df["成交额"].iloc[-1] if "成交额" in df.columns else 0
            return {
                "name":   name,
                "code":   code,
                "price":  round(float(curr_price), 2),
                "amount": round(float(amount), 0),
            }
        return None

    except Exception as e:
        print(f"[{code} {name}] check_strategy error: {e}")
        return None


# ── Gemini AI 深度分析 ────────────────────────────────────────────────────────

def ai_analyse(top_hits: list, now_str: str, period_tag: str) -> str:
    """
    把 Top 标的 + 各自内参新闻喂给 Gemini，输出 CIO 级深度决策报告。
    失败时返回空字符串，不影响主流程。
    """
    if not GEMINI_KEY:
        print("[WARN] GEMINI_API_KEY 未设置，跳过 AI 分析")
        return ""

    enriched_list = []
    for stock in top_hits:
        print(f"  正在抓取内参: {stock['name']}...")
        news = get_stock_news(stock["code"])
        enriched_list.append(
            f"- {stock['name']}（{stock['code']}）现价 {stock['price']} 元 | 内参: {news}"
        )

    prompt = (
        f"你是具备全球视野的首席投资官。当前北京时间 {now_str} {period_tag}。\n"
        f"以下是 {len(top_hits)} 只量能突破标的及其【实时核心新闻内参】。请执行深度复核：\n\n"
        f"【决策维度】\n"
        f"1. 基于内参推理：分析所给新闻对股价的短期/中期影响。有重大利空（如立案、减持）直接判死刑。\n"
        f"2. 宏观背景联动：结合当前国内外大形势（如关税、地缘政治等）判断该行业是否处于风口。\n"
        f"3. 星级评定：5星严格限制在 1-2 只，用🌟表示。\n\n"
        f"【输出格式】\n"
        f"获星标的：🌟🌟... 股票名(代码) + 30字内深度走向预测（必须结合内参或宏观背景）\n"
        f"未获星标的：仅列出 代码 名称\n\n"
        f"【待分析内参名单】\n"
        + "\n".join(enriched_list)
    )

    try:
        genai.configure(api_key=GEMINI_KEY)
        model = genai.GenerativeModel("gemini-2.5-flash")
        resp  = model.generate_content(prompt)
        return resp.text.strip()
    except Exception as e:
        print(f"[WARN] Gemini 分析失败: {e}")
        return ""


# ── 主逻辑 ────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python send_msg.py <1|2|summary>")
        return

    mode       = sys.argv[1]
    now        = datetime.now()
    now_str    = now.strftime("%Y-%m-%d %H:%M")
    period_tag = "【早盘观察】" if now.hour < 12 else "【尾盘决策】"

    # ── summary 模式 ──────────────────────────────────────────────────────────
    if mode == "summary":
        all_hits = []
        for f in ["hits_part1.json", "hits_part2.json"]:
            if os.path.exists(f):
                with open(f, "r", encoding="utf-8") as fp:
                    all_hits += json.load(fp)

        if not all_hits:
            send_wechat(f"📅 {now_str}\n{period_tag} 扫描结束，未发现信号标的。")
            return

        top_hits = sorted(all_hits, key=lambda x: x["amount"], reverse=True)[:10]

        ai_text = ai_analyse(top_hits, now_str, period_tag)

        if ai_text:
            msg = (
                f"🌟 {period_tag} 深度决策报告\n"
                f"时间: {now_str}\n\n"
                f"{ai_text}\n\n"
                f"📊 今日总信号: {len(all_hits)}"
            )
        else:
            # AI 失败时降级为纯列表推送
            lines = [f"🌟 {now_str}  {period_tag}  共发现 {len(all_hits)} 只标的（Top {len(top_hits)}）\n"]
            for i, h in enumerate(top_hits, 1):
                lines.append(
                    f"{i}. {h['name']}（{h['code']}）"
                    f"  价格:{h['price']}  额:{int(h['amount'] / 1e4)}万"
                )
            msg = "\n".join(lines)

        send_wechat(msg)
        return

    # ── 扫描模式（part 1 / 2）────────────────────────────────────────────────
    try:
        part = int(mode)
        assert part in (1, 2)
    except (ValueError, AssertionError):
        print("mode 必须是 1、2 或 summary")
        return

    if part == 1:
        send_wechat(f"📢 机器人启动\n时间: {now_str}\n任务: {period_tag} 扫描开始...")

    try:
        spot_df = ak.stock_zh_a_spot_em()
        spot_df["code"] = spot_df["代码"].astype(str).str.zfill(6)
        active = (
            spot_df[spot_df["code"].str.startswith(("60", "00"))]
            .sort_values(by="成交额", ascending=False)
            .head(1200)
            .reset_index(drop=True)
        )
    except Exception as e:
        send_wechat(f"❌ 获取行情列表失败: {str(e)[:80]}")
        return

    batch = active.head(600) if part == 1 else active.tail(600)
    print(f"[Part {part}] 本批共 {len(batch)} 只，开始扫描…")

    hits = []
    for _, row in batch.iterrows():
        code = str(row["code"]).zfill(6)
        name = str(row["名称"])
        result = check_strategy(code, name)
        if result:
            # 用实时成交额覆盖（单位统一、更准确）
            result["amount"] = float(row.get("成交额", result["amount"]))
            hits.append(result)
            print(f"  ✅ HIT: {name}({code})  price={result['price']}")
        time.sleep(0.15)

    out_file = f"hits_part{part}.json"
    with open(out_file, "w", encoding="utf-8") as fp:
        json.dump(hits, fp, ensure_ascii=False, indent=2)

    print(f"[Part {part}] 完成，命中 {len(hits)} 只，结果已写入 {out_file}")


if __name__ == "__main__":
    main()
