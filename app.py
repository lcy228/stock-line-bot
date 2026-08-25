# -*- coding: utf-8 -*-
"""
主程式：
- GET  /health              給 keep-alive / 健康檢查用
- POST /trigger/<slot>      給 GitHub Actions 排程呼叫，觸發一次分析並廣播到 LINE
- POST /webhook             LINE 官方帳號的 Webhook，處理你在聊天室問的問題
- GET  /charts/<filename>   讓 LINE 抓取產生好的圖表圖片
"""
import os
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import Flask, request, jsonify, send_from_directory

import config
import stock_data
import news
import ai_analysis
import charts
import line_service

app = Flask(__name__)

TRIGGER_SECRET = os.environ.get("TRIGGER_SECRET", "")
# Render 會提供這個環境變數告訴你服務對外的網址；本機測試時可以留空。
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "")


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


def _fetch_one(code, name, category):
    quote = stock_data.get_realtime_quote(code)
    if not quote:
        return None
    history = stock_data.get_daily_history(code, months_back=1)
    indicators = stock_data.compute_indicators(history)
    return {"quote": quote, "indicators": indicators, "category": category, "news": []}


def _fetch_all(tickers):
    """平行抓取所有股票的即時報價與技術指標，加快速度。"""
    rows = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(_fetch_one, c, n, cat): (c, n, cat) for c, n, cat in tickers}
        for fut in as_completed(futures):
            result = fut.result()
            if result:
                rows.append(result)
    return rows


def _attach_news(rows, top_n=3):
    """只幫波動最大的幾檔抓新聞，避免每次觸發要打太多次新聞 API、拖慢速度。"""
    sorted_rows = sorted(rows, key=lambda r: abs(r["quote"]["change_pct"]), reverse=True)
    targets = sorted_rows[:top_n]
    with ThreadPoolExecutor(max_workers=top_n or 1) as pool:
        futures = {}
        for r in targets:
            q = r["quote"]
            futures[pool.submit(news.get_headlines, f"{q['code']} {q['name']}")] = r
        for fut in as_completed(futures):
            r = futures[fut]
            r["news"] = fut.result()


def run_session(slot: str):
    slot_label = config.SCHEDULE_SLOTS.get(slot, slot)
    rows = _fetch_all(config.all_tickers())
    if not rows:
        raise RuntimeError("抓不到任何股票報價，可能是證交所 API 暫時異常")
    _attach_news(rows)

    try:
        commentary = ai_analysis.generate_session_commentary(slot_label, rows)
    except Exception:
        traceback.print_exc()
        commentary = "（這次 AI 評論暫時抓不到，可能是額度限流，稍後的時段會恢復正常，先看數據本身參考）"

    lines = [f"📈 {slot_label}\n"]
    for r in sorted(rows, key=lambda x: (x["category"], x["quote"]["code"])):
        q = r["quote"]
        lines.append(f"[{r['category']}] {q['code']} {q['name']} {q['price']}（{q['change_pct']:+.2f}%）")
    text = "\n".join(lines) + "\n\n" + commentary + config.DISCLAIMER

    chart_filename = charts.generate_change_chart(rows, f"{slot} change %")
    image_url = None
    if PUBLIC_BASE_URL:
        image_url = f"{PUBLIC_BASE_URL.rstrip('/')}/charts/{chart_filename}"

    line_service.broadcast_text_and_image(text, image_url)


@app.post("/trigger/<slot>")
def trigger(slot):
    if not TRIGGER_SECRET or request.headers.get("X-Trigger-Secret") != TRIGGER_SECRET:
        return jsonify({"error": "unauthorized"}), 401
    try:
        run_session(slot)
        return jsonify({"status": "sent", "slot": slot})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "detail": str(e)}), 500


@app.get("/charts/<path:filename>")
def serve_chart(filename):
    return send_from_directory(charts.CHART_DIR, filename)


def _match_tickers(text: str):
    matched = []
    for code, name, _cat in config.all_tickers():
        if code in text or name in text:
            matched.append((code, name))
    return matched


@app.post("/webhook")
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data()
    if not line_service.verify_signature(body, signature):
        return "invalid signature", 400

    payload = request.get_json(silent=True) or {}
    for event in payload.get("events", []):
        if event.get("type") != "message" or event.get("message", {}).get("type") != "text":
            continue
        reply_token = event.get("replyToken")
        user_text = event["message"]["text"]
        try:
            matched = _match_tickers(user_text)
            if matched:
                rows = _fetch_all([(c, n, "詢問") for c, n in matched])
            else:
                rows = _fetch_all([(c, n, "持股") for c, n in config.HOLDINGS])
            answer = ai_analysis.answer_question(user_text, rows)
            line_service.reply_text(reply_token, answer + config.DISCLAIMER)
        except Exception as e:
            traceback.print_exc()
            if reply_token:
                line_service.reply_text(reply_token, f"抱歉，查詢時發生問題：{e}")
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
