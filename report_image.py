# -*- coding: utf-8 -*-
"""
把分析結果直接畫成一張圖片（風格參考「股市戰情室」網頁報告），
這樣 LINE 打開就能直接看到排版好的內容，不用另外點連結。

用 Pillow 手繪，不是網頁截圖 —— 網頁截圖需要開一個完整瀏覽器（Playwright/Chromium），
在 Render 免費方案（記憶體很有限）上很容易爆記憶體或直接把服務弄掛，
所以改用比較輕量的手繪方式，一樣能有類似的版面。
"""
from __future__ import annotations

import os
import uuid
from collections import OrderedDict
from PIL import Image, ImageDraw, ImageFont

import config

IMG_DIR = os.path.join(os.path.dirname(__file__), "static", "report_images")
os.makedirs(IMG_DIR, exist_ok=True)

FONT_PATH = os.path.join(os.path.dirname(__file__), "fonts", "NotoSansTC-Variable.ttf")

# 色盤（跟 templates/report.html 用同一套配色，維持風格一致）
PAPER = (243, 244, 239)
CARD = (253, 253, 251)
INK_900 = (27, 36, 32)
INK_700 = (63, 74, 68)
INK_500 = (107, 117, 110)
BORDER = (220, 222, 212)
ACCENT = (150, 99, 29)
ACCENT_SOFT = (238, 229, 214)
GAIN = (196, 61, 43)   # 台股習慣：紅漲
LOSS = (4, 136, 111)   # 綠跌

WIDTH = 900
PAD = 32


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_PATH, size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    """中文沒有空白分隔，用逐字元加寬度量測的方式換行。"""
    lines, current = [], ""
    for ch in text:
        test = current + ch
        if draw.textlength(test, font=font) <= max_width or not current:
            current = test
        else:
            lines.append(current)
            current = ch
    if current:
        lines.append(current)
    return lines


def generate_report_image(slot_label: str, generated_at: str, rows: list[dict], commentary: str) -> str:
    """畫出報告卡片圖，回傳存檔後的檔名（不含路徑）。"""
    f_eyebrow = _font(16)
    f_title = _font(30)
    f_subtitle = _font(15)
    f_stat_label = _font(13)
    f_stat_value = _font(20)
    f_tag = _font(13)
    f_body = _font(16)
    f_cat = _font(17)
    f_row = _font(15)
    f_row_mono = _font(15)
    f_footer = _font(12)

    measure_img = Image.new("RGB", (10, 10))
    md = ImageDraw.Draw(measure_img)
    content_w = WIDTH - 2 * PAD

    total = len(rows)
    gainers = sum(1 for r in rows if r["quote"]["change_pct"] > 0)
    losers = sum(1 for r in rows if r["quote"]["change_pct"] < 0)
    avg_change = (sum(r["quote"]["change_pct"] for r in rows) / total) if total else 0.0

    groups = OrderedDict()
    for r in sorted(rows, key=lambda x: (x["category"], x["quote"]["code"])):
        groups.setdefault(r["category"], []).append(r)

    # PIL 的 textlength() 不支援含換行的字串，AI 生成的評論可能自己帶換行，
    # 先把所有空白（含換行）normalize 成單一空格，換行完全交給下面的 _wrap 自己處理。
    commentary_flat = " ".join(commentary.split())
    commentary_lines = _wrap(md, commentary_flat, f_body, content_w - 24)

    # ---- 第一遍：只算高度，不實際畫 ----
    y = PAD
    y += 20 + 8       # eyebrow
    y += 38 + 6       # title
    y += 20 + 20      # subtitle + gap
    y += 78 + 20      # stat strip + gap
    y += 20 + len(commentary_lines) * 22 + 16 + 24  # commentary box + gap
    row_h = 34
    for cat, cat_rows in groups.items():
        y += 28 + len(cat_rows) * row_h + 16
    # 字型沒有涵蓋 emoji，圖片版本的免責聲明拿掉開頭的警告符號，避免變成空白方框
    disclaimer_text = config.DISCLAIMER.strip().lstrip("⚠️ ")
    footer_lines = _wrap(md, disclaimer_text, f_footer, content_w)
    y += 16 + len(footer_lines) * 16 + PAD

    height = y

    img = Image.new("RGB", (WIDTH, height), PAPER)
    draw = ImageDraw.Draw(img)

    y = PAD
    draw.text((PAD, y), "股市戰情室", font=f_eyebrow, fill=ACCENT)
    y += 20 + 8
    draw.text((PAD, y), slot_label, font=f_title, fill=INK_900)
    y += 38 + 6
    draw.text((PAD, y), f"產生時間 {generated_at}（台北時間）", font=f_subtitle, fill=INK_500)
    y += 20 + 20

    # 統計條
    stat_h = 78
    stat_w = content_w / 4
    stats = [
        ("追蹤檔數", str(total), INK_900),
        ("上漲", str(gainers), GAIN),
        ("下跌", str(losers), LOSS),
        ("平均漲跌幅", f"{avg_change:+.2f}%", GAIN if avg_change >= 0 else LOSS),
    ]
    draw.rounded_rectangle([PAD, y, PAD + content_w, y + stat_h], radius=10, fill=CARD, outline=BORDER)
    for i, (label, value, color) in enumerate(stats):
        cx = PAD + stat_w * i
        if i > 0:
            draw.line([(cx, y + 12), (cx, y + stat_h - 12)], fill=BORDER, width=1)
        lw = md.textlength(label, font=f_stat_label)
        draw.text((cx + stat_w / 2 - lw / 2, y + 16), label, font=f_stat_label, fill=INK_500)
        vw = md.textlength(value, font=f_stat_value)
        draw.text((cx + stat_w / 2 - vw / 2, y + 40), value, font=f_stat_value, fill=color)
    y += stat_h + 20

    # AI 評論
    box_h = 20 + len(commentary_lines) * 22 + 16
    draw.rounded_rectangle([PAD, y, PAD + content_w, y + box_h], radius=10, fill=ACCENT_SOFT)
    draw.text((PAD + 16, y + 12), "AI 觀察", font=f_tag, fill=ACCENT)
    ty = y + 34
    for line in commentary_lines:
        draw.text((PAD + 16, ty), line, font=f_body, fill=INK_700)
        ty += 22
    y += box_h + 24

    # 各分類股票列表
    for cat, cat_rows in groups.items():
        draw.text((PAD, y), cat, font=f_cat, fill=INK_900)
        y += 28
        for r in cat_rows:
            q, ind = r["quote"], r["indicators"]
            row_top = y
            draw.text((PAD, row_top), q["code"], font=f_row_mono, fill=INK_500)
            draw.text((PAD + 70, row_top), q["name"], font=f_row, fill=INK_900)
            price_text = str(q["price"])
            pw = md.textlength(price_text, font=f_row_mono)
            draw.text((PAD + content_w - 170 - pw, row_top), price_text, font=f_row_mono, fill=INK_900)
            change_text = f"{q['change_pct']:+.2f}%"
            change_color = GAIN if q["change_pct"] >= 0 else LOSS
            cw = md.textlength(change_text, font=f_row_mono)
            draw.text((PAD + content_w - cw, row_top), change_text, font=f_row_mono, fill=change_color)
            trend_text = ind.get("trend", "")
            tw = md.textlength(trend_text, font=f_footer)
            draw.text((PAD + content_w - 170 - pw - 16 - tw, row_top + 2), trend_text, font=f_footer, fill=INK_500)
            draw.line([(PAD, y + row_h - 6), (PAD + content_w, y + row_h - 6)], fill=BORDER, width=1)
            y += row_h
        y += 16

    # 免責聲明
    for line in footer_lines:
        draw.text((PAD, y), line, font=f_footer, fill=INK_500)
        y += 16

    filename = f"{uuid.uuid4().hex}.png"
    img.save(os.path.join(IMG_DIR, filename), "PNG")
    return filename
