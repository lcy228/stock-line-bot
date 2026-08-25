# -*- coding: utf-8 -*-
"""
呼叫 Gemini API 產生分析文字。
免費額度用的是 Google AI Studio 申請的 GEMINI_API_KEY。
"""
from __future__ import annotations

import os
import google.generativeai as genai

# 模型名稱之後如果 Google 改版棄用，去 https://ai.google.dev/gemini-api/docs/models
# 找一個目前可用的 flash 模型名稱換掉即可，其他程式碼不用動。
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

_configured = False


def _ensure_configured():
    global _configured
    if not _configured:
        api_key = os.environ["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)
        _configured = True


def generate_session_commentary(slot_label: str, stock_rows: list[dict]) -> str:
    """幫整批追蹤股票產生一段當個時段的整體評論（給排程推播用）。"""
    _ensure_configured()
    lines = []
    for r in stock_rows:
        q = r["quote"]
        ind = r["indicators"]
        news_titles = "；".join(n["title"] for n in r["news"][:2])
        lines.append(
            f"{r['category']} {q['code']} {q['name']}：現價 {q['price']}"
            f"（{q['change_pct']:+.2f}%），{ind['trend']}，"
            f"RSI14={ind['rsi14']}，相關新聞：{news_titles or '無'}"
        )
    data_block = "\n".join(lines)

    prompt = f"""你是一位謹慎的台股助理，正在幫使用者做「{slot_label}」的整理。
以下是使用者追蹤股票的即時數據與新聞標題：

{data_block}

請用繁體中文寫一段簡短的整體評論（150～250 字），包含：
1. 大盤氛圍與資金流向的簡單觀察（根據上面數據推測即可，不用假裝有额外資訊）
2. 挑出 2～3 檔波動較明顯或有新聞題材的股票，簡短說明原因
3. 用「參考觀察」的語氣提一下這個時段可以留意的價位或訊號，不要用「建議買進」「保證」這類字眼
4. 語氣自然、像朋友在聊股票，不要用條列式，不要重複數據本身（數據使用者已經看得到）
不要加免責聲明，系統會自動附加。"""

    model = genai.GenerativeModel(MODEL_NAME)
    # 明確設定逾時，避免免費額度偶爾限流時，SDK 內部重試卡住拖垮整個請求。
    resp = model.generate_content(prompt, request_options={"timeout": 30})
    return (resp.text or "").strip()


def answer_question(user_text: str, context_rows: list[dict]) -> str:
    """使用者在 LINE 聊天室問問題時，讓 Gemini 根據目前追蹤清單的即時資料回答。"""
    _ensure_configured()
    lines = []
    for r in context_rows:
        q = r["quote"]
        lines.append(f"{q['code']} {q['name']}：現價 {q['price']}（{q['change_pct']:+.2f}%）")
    data_block = "\n".join(lines) if lines else "（目前沒有抓到即時報價資料）"

    prompt = f"""你是使用者的台股助理，個性像朋友、講話白話不生硬。
使用者目前追蹤的股票即時報價如下：
{data_block}

使用者的問題：「{user_text}」

請用繁體中文回答，簡短清楚（100 字內為主，除非問題明確需要更長）。
如果問題跟買賣時機有關，用「參考觀察」的語氣回答，不要給保證性的操作建議，
也不要每次都提醒風險（系統會自動附加免責聲明，你只要專注回答問題）。
如果使用者問的股票不在上面清單裡，就誠實說目前沒有即時資料，
但可以就你所知的產業背景簡單回應。"""

    model = genai.GenerativeModel(MODEL_NAME)
    resp = model.generate_content(prompt, request_options={"timeout": 30})
    return (resp.text or "").strip()
