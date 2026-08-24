# -*- coding: utf-8 -*-
"""
產生簡單圖表（今日漲跌幅長條圖），存成 PNG 給 LINE 圖片訊息用。
Render 免費方案的硬碟是暫存性質，重啟會清空，所以檔案不用特別清理，
每次觸發時用時間戳記命名即可避免互相覆蓋。
"""
from __future__ import annotations

import os
import uuid
import matplotlib

matplotlib.use("Agg")  # 沒有畫面的伺服器環境要用非互動後端
import matplotlib.pyplot as plt

CHART_DIR = os.path.join(os.path.dirname(__file__), "static", "charts")
os.makedirs(CHART_DIR, exist_ok=True)

# Render 的 Linux 環境沒有內建中文字型，畫中文會變空白方框，
# 所以圖表本身只用股票代號 / 英文（完整中文名稱看文字訊息就好）。
plt.rcParams["axes.unicode_minus"] = False


def generate_change_chart(stock_rows: list[dict], title: str = "Change %") -> str:
    """畫出所有追蹤股票的今日漲跌幅長條圖，回傳存檔後的檔名（不含路徑）。"""
    labels = [r["quote"]["code"] for r in stock_rows]
    values = [r["quote"]["change_pct"] for r in stock_rows]
    colors = ["#d9534f" if v >= 0 else "#2e7d32" for v in values]  # 台股習慣：紅漲綠跌

    fig_width = max(8, len(labels) * 0.5)
    fig, ax = plt.subplots(figsize=(fig_width, 5))
    ax.bar(labels, values, color=colors)
    ax.axhline(0, color="#888", linewidth=0.8)
    ax.set_ylabel("Change (%)")
    ax.set_title(title)
    plt.xticks(rotation=60, ha="right", fontsize=8)
    plt.tight_layout()

    filename = f"{uuid.uuid4().hex}.png"
    filepath = os.path.join(CHART_DIR, filename)
    fig.savefig(filepath, dpi=130)
    plt.close(fig)
    return filename
