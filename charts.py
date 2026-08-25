# -*- coding: utf-8 -*-
"""
產生簡單圖表（今日漲跌幅長條圖），存成 PNG 給 LINE 圖片訊息用。
Render 免費方案的硬碟是暫存性質，重啟會清空，所以檔案不用特別清理，
每次觸發時用時間戳記命名即可避免互相覆蓋。
"""
from __future__ import annotations

import os
import uuid
from collections import OrderedDict
import matplotlib

matplotlib.use("Agg")  # 沒有畫面的伺服器環境要用非互動後端
import matplotlib.pyplot as plt

import config

CHART_DIR = os.path.join(os.path.dirname(__file__), "static", "charts")
os.makedirs(CHART_DIR, exist_ok=True)

# Render 的 Linux 環境沒有內建中文字型，畫中文會變空白方框，
# 所以圖表本身只用股票代號 / 英文（完整中文名稱看文字訊息就好）。
plt.rcParams["axes.unicode_minus"] = False


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
