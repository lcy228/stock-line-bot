# -*- coding: utf-8 -*-
"""
產生圖表，存成 PNG 給 LINE 圖片訊息用。
Render 免費方案的硬碟是暫存性質，重啟會清空，所以檔案不用特別清理，
每次觸發時用時間戳記命名即可避免互相覆蓋。
"""
from __future__ import annotations

import datetime
import os
import uuid
from collections import OrderedDict
import matplotlib

matplotlib.use("Agg")  # 沒有畫面的伺服器環境要用非互動後端
import matplotlib.dates as mdates
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

import config
import stock_data

CHART_DIR = os.path.join(os.path.dirname(__file__), "static", "charts")
os.makedirs(CHART_DIR, exist_ok=True)

plt.rcParams["axes.unicode_minus"] = False

# 個股走勢圖要用中文標題（代號＋名稱），report_image.py 已經有 bundle 一份
# 中文字型檔，這裡直接註冊給 matplotlib 用，就不用再多帶一份字型檔。
# generate_change_chart() 原本只用代號/英文，不受影響，註冊字型不會讓既有圖表變樣。
_FONT_PATH = os.path.join(os.path.dirname(__file__), "fonts", "NotoSansTC-Variable.ttf")
if os.path.exists(_FONT_PATH):
    fm.fontManager.addfont(_FONT_PATH)
    plt.rcParams["font.family"] = fm.FontProperties(fname=_FONT_PATH).get_name()

# 跟 report_image.py 同一套配色，維持整個機器人輸出的視覺風格一致。
_PAPER = "#f3f4ef"
_INK_900 = "#1b2420"
_INK_700 = "#3f4a44"
_BORDER = "#dcded4"
_GAIN = "#c43d2b"  # 台股習慣：紅漲
_LOSS = "#04886f"  # 綠跌


def generate_change_chart(stock_rows: list[dict], title: str = "Change %") -> str:
    """依分類（持股／航運／載板...）各畫一小塊漲跌幅長條圖，堆疊成一張圖，
    避免全部股票擠在同一排、分不出哪些是同產業。回傳存檔後的檔名（不含路徑）。"""
    groups = OrderedDict()
    for r in stock_rows:
        groups.setdefault(r["category"], []).append(r)

    all_values = [r["quote"]["change_pct"] for r in stock_rows] or [0]
    y_min, y_max = min(all_values + [0]), max(all_values + [0])
    pad = max(0.5, (y_max - y_min) * 0.15)

    n = len(groups)
    fig, axes = plt.subplots(n, 1, figsize=(9, 2.3 * n))
    if n == 1:
        axes = [axes]

    for ax, (cat, rows) in zip(axes, groups.items()):
        rows = sorted(rows, key=lambda r: r["quote"]["code"])
        labels = [r["quote"]["code"] for r in rows]
        values = [r["quote"]["change_pct"] for r in rows]
        colors = ["#d9534f" if v >= 0 else "#2e7d32" for v in values]  # 台股習慣：紅漲綠跌
        ax.bar(labels, values, color=colors)
        ax.axhline(0, color="#888", linewidth=0.8)
        ax.set_ylim(y_min - pad, y_max + pad)
        ax.set_title(config.CATEGORY_LABELS_EN.get(cat, cat), fontsize=10, loc="left")
        ax.tick_params(axis="x", labelsize=8)

    fig.suptitle(title)
    plt.tight_layout()

    filename = f"{uuid.uuid4().hex}.png"
    filepath = os.path.join(CHART_DIR, filename)
    fig.savefig(filepath, dpi=130)
    plt.close(fig)
    return filename


def generate_price_trend_chart(code: str, name: str, history: list[dict], quote: dict) -> str | None:
    """聊天室即時查詢用：畫一張乾淨的近一個月股價走勢圖（只有一條線，不是
    資訊卡），字體和圖片都刻意放大，避免在手機上看起來模糊或字太小。
    history 沒資料（例如上櫃股票查不到日線）就回傳 None，呼叫端不附圖即可。"""
    dates, closes = [], []
    for h in history:
        d = stock_data.parse_roc_date(h["date"])
        if d:
            dates.append(d)
            closes.append(h["close"])
    if len(dates) < 2:
        return None

    # history 拿到的可能不只一個月（呼叫端為了保證資料夠多可能抓兩個月），
    # 這裡只留最近 30 天，圖表才是「近一個月」而不是全部都畫出來。
    cutoff = datetime.date.today() - datetime.timedelta(days=30)
    trimmed = [(d, c) for d, c in zip(dates, closes) if d >= cutoff]
    if len(trimmed) >= 2:
        dates, closes = (list(t) for t in zip(*trimmed))

    # 日線資料是收盤價，盤中查詢時「今天」還沒收盤、不會在裡面，會導致圖表
    # 最後一點跟文字訊息回報的即時股價對不起來；今天還沒收盤就把即時價格
    # 補成最後一點，讓圖表跟文字看到的現價一致。
    today = datetime.date.today()
    if dates[-1] < today and quote.get("price") is not None:
        dates.append(today)
        closes.append(quote["price"])

    line_color = _GAIN if quote.get("change_pct", 0) >= 0 else _LOSS

    fig, ax = plt.subplots(figsize=(9, 6))
    fig.patch.set_facecolor(_PAPER)
    ax.set_facecolor(_PAPER)

    ax.plot(dates, closes, color=line_color, linewidth=2.5, solid_capstyle="round")
    ax.scatter([dates[-1]], [closes[-1]], color=line_color, s=90, zorder=5,
               edgecolors=_PAPER, linewidths=2)
    ax.annotate(
        f"{closes[-1]:g}",
        xy=(dates[-1], closes[-1]), xytext=(12, 10), textcoords="offset points",
        fontsize=20, fontweight="bold", color=line_color,
    )

    ax.set_title(f"{code}　{name}　近一月股價", fontsize=24, pad=18, color=_INK_900, loc="left")
    ax.grid(axis="y", color=_BORDER, linewidth=0.8)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color(_BORDER)
    ax.tick_params(axis="both", labelsize=15, colors=_INK_700)

    step = max(1, len(dates) // 5)
    ax.set_xticks(dates[::step])
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    fig.autofmt_xdate(rotation=0, ha="center")

    plt.tight_layout()

    filename = f"{uuid.uuid4().hex}.png"
    filepath = os.path.join(CHART_DIR, filename)
    fig.savefig(filepath, dpi=200, facecolor=_PAPER)
    plt.close(fig)
    return filename
