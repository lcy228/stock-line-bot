# -*- coding: utf-8 -*-
"""
主程式：
- GET  /health              給 keep-alive / 健康檢查用
- POST /trigger/<slot>      手動觸發整批分析並廣播到 LINE（原本的盤前/盤中/盤後排程
                             已經關閉，這個路由保留給之後想手動補推播時用，平常不會自動跑）
- POST /webhook             LINE 官方帳號的 Webhook：你在聊天室打股票代號或名稱，
                             就查即時股價、三大法人買賣超、最近新聞，簡短回覆文字，
                             附上一張近一月走勢圖（資料都來自公開 API，不靠 AI 現場查證）
- GET  /charts/<filename>   讓 LINE 抓取產生好的圖表圖片
- GET  /                    網站首頁：依產業分類的股票格子＋搜尋
- GET  /search              搜尋股票代號／名稱
- GET  /industry/<code>     某產業分類底下的個股（圓圈大小＝外資買賣超力道）
- GET  /stock/<code>        個股頁面：股價、法人、互動走勢圖、新聞（點開不跳頁）
"""
import os
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeoutError
from datetime import datetime, timezone, timedelta

from flask import Flask, request, jsonify, send_from_directory, render_template, redirect

import config
import stock_data
import news
import ai_analysis
import charts
import report_image
import line_service
import industries

app = Flask(__name__)

TAIPEI_TZ = timezone(timedelta(hours=8))

# 給「呼叫 Gemini 但最多只等 N 秒、逾時就放棄」用的共用執行緒池。
# 不能用 `with ThreadPoolExecutor() as pool`，因為離開 with 區塊時會等所有工作做完，
# 這樣就算我們判定逾時放棄了，還是會被卡住 —— 用共用池、不 shutdown，才能真正做到「不等它」。
_AI_POOL = ThreadPoolExecutor(max_workers=2)

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
    holding = None
    cost_basis = config.get_cost_basis(code)
    if cost_basis:
        shares, cost = cost_basis
        pl_amount = (quote["price"] - cost) * shares
        pl_pct = (quote["price"] - cost) / cost * 100 if cost else 0.0
        holding = {"shares": shares, "cost": cost, "pl_amount": pl_amount, "pl_pct": pl_pct}
    return {"quote": quote, "indicators": indicators, "category": category, "news": [], "holding": holding}


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

    # Gemini SDK 本身的重試機制不可靠（逾時設定不保證有效），改成另開執行緒
    # 硬性等待，時間到就放棄、不等它真正結束，避免拖垮整個請求被 gunicorn 從外部砍斷。
    future = _AI_POOL.submit(ai_analysis.generate_session_commentary, slot_label, rows)
    try:
        commentary = future.result(timeout=25)
    except FutureTimeoutError:
        commentary = "（這次 AI 評論來不及產生，可能是額度限流，稍後的時段會恢復正常，先看數據本身參考）"
    except Exception:
        traceback.print_exc()
        commentary = "（這次 AI 評論暫時抓不到，可能是額度限流，稍後的時段會恢復正常，先看數據本身參考）"

    lines = [f"📈 {slot_label}\n"]
    for r in sorted(rows, key=lambda x: (x["category"], x["quote"]["code"])):
        q = r["quote"]
        lines.append(f"[{r['category']}] {q['code']} {q['name']} {q['price']}（{q['change_pct']:+.2f}%）")
    text = "\n".join(lines) + "\n\n" + commentary + config.DISCLAIMER

    generated_at = datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M")
    report_filename = report_image.generate_report_image(slot_label, generated_at, rows, commentary)
    chart_filename = charts.generate_change_chart(rows, f"{slot} change %")

    image_urls = []
    if PUBLIC_BASE_URL:
        base = PUBLIC_BASE_URL.rstrip("/")
        image_urls = [
            f"{base}/static/report_images/{report_filename}",
            f"{base}/charts/{chart_filename}",
        ]

    line_service.broadcast_text_and_image(text, image_urls)


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


def _handle_query(reply_token: str, user_text: str):
    """聊天室收到一句話：先解析成股票代號，查即時報價，再平行抓三大法人買賣超、
    近三月日線、最近新聞，回一則簡短文字＋一張走勢圖。不限於原本追蹤的清單，
    任何上市櫃股票代號或名稱都可以查。全部是真實公開資料源，不靠 AI 現場查證，
    只有「代號/名稱怎麼對應」這一步會用到 Gemini（快、不用等即時搜尋）。"""
    resolve_future = _AI_POOL.submit(ai_analysis.resolve_ticker_code, user_text)
    try:
        code = resolve_future.result(timeout=10)
    except FutureTimeoutError:
        line_service.reply_text(reply_token, "現在有點塞車（可能是 AI 額度限流），等一下再問我一次看看")
        return

    if not code:
        line_service.reply_text(
            reply_token,
            "打股票代碼（例如 2330）或公司名稱給我，我幫你查即時股價、外資買賣超、最近新聞，附上走勢圖。",
        )
        return

    quote = stock_data.get_realtime_quote(code)
    if not quote:
        line_service.reply_text(reply_token, f"查不到「{code}」的即時報價，確認一下代號是不是打對了？")
        return

    with ThreadPoolExecutor(max_workers=3) as pool:
        inst_future = pool.submit(stock_data.get_institutional_trading, code)
        history_future = pool.submit(stock_data.get_daily_history, code, 1)
        news_future = pool.submit(news.get_headlines, f"{code} {quote['name']}", 2)
        inst = inst_future.result()
        history = history_future.result()
        headlines = news_future.result()

    lines = [f"📊 {code} {quote['name']}", f"現價 {quote['price']:g}（{quote['change_pct']:+.2f}%）"]
    if inst:
        foreign_lots = inst["foreign_net"] / 1000
        total_lots = inst["total_net"] / 1000
        lines.append(f"外資買賣超 {foreign_lots:+,.0f} 張（{inst['date']}）")
        lines.append(f"三大法人合計 {total_lots:+,.0f} 張")
    else:
        lines.append("外資買賣超：查無最新資料")

    if headlines:
        lines.append("")
        lines.append("📰 最近新聞")
        for h in headlines:
            lines.append(f"・{h['title']}")

    lines.append("")
    lines.append("（資料為即時查詢，僅供參考）")
    text = "\n".join(lines)

    chart_filename = charts.generate_price_trend_chart(code, quote["name"], history, quote)

    if chart_filename and PUBLIC_BASE_URL:
        image_url = f"{PUBLIC_BASE_URL.rstrip('/')}/charts/{chart_filename}"
        line_service.reply_text_and_image(reply_token, text, image_url)
    else:
        line_service.reply_text(reply_token, text)


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
            _handle_query(reply_token, user_text)
        except Exception as e:
            traceback.print_exc()
            if reply_token:
                line_service.reply_text(reply_token, f"抱歉，查詢時發生問題：{e}")
    return jsonify({"status": "ok"})


# ============ 網站：依產業分類點選查股票 ============

def _size_class(count: int, max_count: int) -> str:
    """依公司數量決定首頁格子大小，數量越多格子越大（面積不是真的按比例算，
    分成四級比較好維護、螢幕小的時候版面也比較不會亂）。"""
    ratio = count / max_count if max_count else 0
    if ratio >= 0.6:
        return "xl"
    if ratio >= 0.35:
        return "lg"
    if ratio >= 0.15:
        return "md"
    return "sm"


@app.get("/")
def home():
    industry_list = industries.list_industries()
    max_count = max((it["count"] for it in industry_list), default=1)
    for it in industry_list:
        it["size"] = _size_class(it["count"], max_count)
    return render_template("home.html", holdings=config.HOLDING_CODES_NAMES, industries=industry_list)


@app.get("/search")
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return redirect("/")
    results = industries.search_companies(q)
    if len(results) == 1:
        return redirect(f"/stock/{results[0][0]}")
    return render_template("search.html", q=q, results=results)


@app.get("/industry/<code>")
def industry_page(code):
    companies = industries.get_industry_companies(code)
    industry_name = industries.get_industry_name(code)

    rows = []
    for stock_code, name in companies:
        inst = stock_data.get_institutional_trading(stock_code)
        rows.append({"code": stock_code, "name": name, "net": inst["foreign_net"] if inst else None})

    magnitudes = [abs(r["net"]) for r in rows if r["net"]]
    max_abs = max(magnitudes) if magnitudes else 1
    for r in rows:
        net = r.pop("net")
        if not net:
            r["size"] = 14
            r["color"] = "var(--border)"
        else:
            # 開根號讓「面積」比較符合直覺的比例，而不是半徑直接線性對應金額
            # （不然一檔股票買超是另一檔的 4 倍，圓圈半徑看起來會差到 4 倍、面積差 16 倍，太誇張）。
            ratio = (abs(net) / max_abs) ** 0.5
            r["size"] = round(14 + ratio * 34)
            r["color"] = "var(--gain)" if net > 0 else "var(--loss)"

    return render_template("industry.html", industry_name=industry_name, companies=rows)


@app.get("/stock/<code>")
def stock_page(code):
    quote = stock_data.get_realtime_quote(code)
    if not quote:
        return render_template("search.html", q=code, results=[]), 404

    with ThreadPoolExecutor(max_workers=3) as pool:
        inst_future = pool.submit(stock_data.get_institutional_trading, code)
        history_future = pool.submit(stock_data.get_daily_history, code, 1)
        news_future = pool.submit(news.get_headlines, f"{code} {quote['name']}", 5)
        inst = inst_future.result()
        history = history_future.result()
        headlines = news_future.result()

    dates, closes = stock_data.recent_price_series(history, quote, days=30)
    chart_data = {"labels": [d.strftime("%m/%d") for d in dates], "closes": closes}

    return render_template("stock.html", quote=quote, inst=inst, news=headlines, chart_data=chart_data)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
