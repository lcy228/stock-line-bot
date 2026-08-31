# -*- coding: utf-8 -*-
"""
呼叫 Gemini API 做即時分析。

改用新版 google-genai SDK（原本的 google-generativeai 官方已經棄用），
並且加上 Google 搜尋 grounding，讓 Gemini 可以真的即時上網查資料，
不再只靠訓練資料裡的舊知識瞎猜財報數字或新聞——這是讓 LINE 聊天室能
「打股票代碼或名稱、即時查財報和新聞」這個功能的關鍵。
"""
from __future__ import annotations

import json
import os
import re

from google import genai
from google.genai import types

# 模型名稱之後如果 Google 改版棄用，去 https://ai.google.dev/gemini-api/docs/models
# 找一個目前可用、支援 Google 搜尋 grounding 的模型名稱換掉即可，其他程式碼不用動。
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

_client: genai.Client | None = None

# 這裡的 timeout 是防呆用（毫秒），真正「等太久就放棄」的邏輯在 app.py 用
# ThreadPoolExecutor 另外做（SDK 內部的 timeout/重試不保證可靠），兩層一起比較保險。
_GROUNDING_TOOL = types.Tool(google_search=types.GoogleSearch())
_GROUNDED_CONFIG = types.GenerateContentConfig(
    tools=[_GROUNDING_TOOL], http_options=types.HttpOptions(timeout=40000),
)
_QUICK_CONFIG = types.GenerateContentConfig(http_options=types.HttpOptions(timeout=8000))
_COMMENTARY_CONFIG = types.GenerateContentConfig(http_options=types.HttpOptions(timeout=30000))

_TICKER_RE = re.compile(r"[0-9]{4,6}[A-Za-z]?")


def _client_instance() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


def resolve_ticker_code(user_text: str) -> str | None:
    """把使用者輸入（股票代號、公司名稱、甚至一整句話）解析成台股代號。

    這一步不用即時搜尋——股票代號是穩定的常識，用一般模型快速判斷即可，
    不用每次都等 grounding 那麼久；使用者直接打代號的話更是完全不用問 AI。
    解析不出來（或使用者明顯不是在問股票）回傳 None。
    """
    text = user_text.strip()
    if re.fullmatch(r"[0-9]{4,6}[A-Za-z]?", text):
        return text.upper()

    client = _client_instance()
    prompt = (
        "使用者在台股分析機器人聊天室輸入了以下文字，請判斷他想查詢哪一檔台股"
        "（上市或上櫃）的股票代號。只回覆代號本身（例如 2330 或 00895），"
        "不要加任何其他文字、標點或說明；如果無法判斷、或這句話明顯不是在問股票，"
        f"只回覆 UNKNOWN。\n\n使用者輸入：「{text}」"
    )
    resp = client.models.generate_content(model=MODEL_NAME, contents=prompt, config=_QUICK_CONFIG)
    answer = (resp.text or "").strip().upper()
    if "UNKNOWN" in answer:
        return None
    m = _TICKER_RE.search(answer)
    return m.group(0) if m else None


def deep_dive_report(code: str, name: str, quote: dict) -> dict | None:
    """用 Gemini + Google 搜尋 grounding，即時查這檔股票的財報重點、最新新聞、
    技術位階，回傳跟 stock_notes.py 同樣格式的字典，讓 report_image.py 可以
    直接拿去畫成跟「股市戰情室」一樣的卡片。

    查不到、或 AI 回傳格式不對，回傳 None，呼叫端要自己處理 fallback文字回覆，
    不要讓格式錯誤直接讓整個查詢失敗。
    """
    client = _client_instance()
    prompt = f"""你是台股分析助理，請針對「{code} {name}」這檔股票，用 Google 搜尋找目前
最新的公開資訊（財報、法說會、近期新聞、股價區間），整理成一份分析。
使用者目前參考報價：現價 {quote['price']} 元，今日漲跌 {quote['change_pct']:+.2f}%。

請只回覆一個 JSON 物件，不要加 ```json 這種標記、不要加任何其他文字或說明，格式如下：
{{
  "tag": "一句話產業標籤，例如「半導體．AI供應鏈核心」",
  "range_low": 數字（52 週低點，或近期合理技術區間下緣，不要加千分位逗號）,
  "range_high": 數字（52 週高點，或近期合理技術區間上緣，不要加千分位逗號）,
  "zone_low": 數字（觀察買點區間下緣）,
  "zone_high": 數字（觀察買點區間上緣）,
  "zone_note": "一句話買點註記，例如「觀察買點 900–1000」",
  "facts": [
    {{"label": "財報", "text": "最新一季財報重點，營收/獲利/毛利率等具體數字"}},
    {{"label": "新聞", "text": "近期影響股價的重大消息"}},
    {{"label": "位階", "text": "本益比、股價淨值比等評價位階，是否偏貴或便宜"}},
    {{"label": "買點", "text": "根據以上資訊給的觀察買點看法，語氣是參考觀察不是保證，不要用「建議買進」這種字眼"}}
  ]
}}

facts 每項 text 限制在 90 字以內、繁體中文，數字盡量具體，避免空泛描述；
如果查不到某項資訊，就誠實寫「目前查無最新資料」，不要編造數字。"""

    try:
        resp = client.models.generate_content(
            model=MODEL_NAME, contents=prompt, config=_GROUNDED_CONFIG,
        )
        raw = (resp.text or "").strip()
        raw = re.sub(r"^```(json)?|```$", "", raw, flags=re.MULTILINE).strip()
        data = json.loads(raw)
        facts = [(item["label"], item["text"]) for item in data["facts"]]
        return {
            "tag": data["tag"],
            "range": (float(data["range_low"]), float(data["range_high"])),
            "zone": (float(data["zone_low"]), float(data["zone_high"])),
            "zone_note": data["zone_note"],
            "facts": facts,
        }
    except Exception:
        return None


def generate_session_commentary(slot_label: str, stock_rows: list[dict]) -> str:
    """幫整批追蹤股票產生一段當個時段的整體評論。

    排程已經關閉（改成聊天室即時查詢個股），這個函式只留給 /trigger 手動
    觸發時用，平常不會自動執行。"""
    lines = []
    for r in stock_rows:
        q = r["quote"]
        ind = r["indicators"]
        news_titles = "；".join(n["title"] for n in r["news"][:2])
        holding_note = ""
        if r["holding"]:
            h = r["holding"]
            holding_note = f"，你的成本 {h['cost']}（目前損益 {h['pl_pct']:+.1f}%）"
        lines.append(
            f"{r['category']} {q['code']} {q['name']}：現價 {q['price']}"
            f"（{q['change_pct']:+.2f}%），{ind['trend']}，"
            f"RSI14={ind['rsi14']}{holding_note}，相關新聞：{news_titles or '無'}"
        )
    data_block = "\n".join(lines)

    prompt = f"""你是一位謹慎的台股助理，正在幫使用者做「{slot_label}」的整理。
以下是使用者追蹤股票的即時數據，有標「你的成本」的是他實際持有的部位：

{data_block}

請用繁體中文寫一段簡短的整體評論（150～250 字），包含：
1. 大盤氛圍與資金流向的簡單觀察（根據上面數據推測即可，不用假裝有额外資訊）
2. 挑出 2～3 檔波動較明顯、有新聞題材、或現價明顯偏離自己成本的股票，簡短說明原因
3. 對有標成本的持股，可以用「參考觀察」的語氣提一下現價相對成本的位置算不算加碼／減碼的合理區間
   （例如季線、月線附近，或距離成本仍有安全邊際），不要用「建議買進」「保證」這類字眼
4. 語氣自然、像朋友在聊股票，不要用條列式，不要重複數據本身（數據使用者已經看得到）
不要加免責聲明，系統會自動附加。"""

    client = _client_instance()
    resp = client.models.generate_content(model=MODEL_NAME, contents=prompt, config=_COMMENTARY_CONFIG)
    return (resp.text or "").strip()
