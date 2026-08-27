# -*- coding: utf-8 -*-
"""
把分析結果直接畫成一張圖片（風格參考「股市戰情室」網頁報告），
這樣 LINE 打開就能直接看到排版好的內容，不用另外點連結。

用 Pillow 手繪，不是網頁截圖 —— 網頁截圖需要開一個完整瀏覽器（Playwright/Chromium），
在 Render 免費方案（記憶體很有限）上很容易爆記憶體或直接把服務弄掛，
所以改用比較輕量的手繪方式，一樣能有類似的版面。

有持股筆記（stock_notes.py）的股票，會畫成完整卡片：價位區間圖 + 財報／買點文字，
跟原本那份「股市戰情室」報告一樣；只是追蹤用、沒有筆記的類股，維持簡單一行呈現。
"""
from __future__ import annotations

import os
import uuid
from collections import OrderedDict
from PIL import Image, ImageDraw, ImageFont

import config
import stock_notes

IMG_DIR = os.path.join(os.path.dirname(__file__), "static", "report_images")
os.makedirs(IMG_DIR, exist_ok=True)

FONT_PATH = os.path.join(os.path.dirname(__file__), "fonts", "NotoSansTC-Variable.ttf")

# 色盤（跟原本網頁報告用同一套配色，維持風格一致）
PAPER = (243, 244, 239)
CARD = (253, 253, 251)
INK_900 = (27, 36, 32)
INK_700 = (63, 74, 68)
INK_500 = (107, 117, 110)
BORDER = (220, 222, 212)
BORDER_SOFT = (231, 232, 224)
ACCENT = (150, 99, 29)
ACCENT_SOFT = (238, 229, 214)
GAIN = (196, 61, 43)   # 台股習慣：紅漲
LOSS = (4, 136, 111)   # 綠跌

WIDTH = 900
PAD = 32

_FONT_CACHE: dict[int, ImageFont.FreeTypeFont] = {}


def _font(size: int) -> ImageFont.FreeTypeFont:
    if size not in _FONT_CACHE:
        _FONT_CACHE[size] = ImageFont.truetype(FONT_PATH, size)
    return _FONT_CACHE[size]


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


class _Fonts:
    def __init__(self):
        self.eyebrow = _font(16)
        self.title = _font(30)
        self.subtitle = _font(15)
        self.stat_label = _font(13)
        self.stat_value = _font(20)
        self.tag = _font(13)
        self.body = _font(16)
        self.cat = _font(17)
        self.row = _font(15)
        self.row_mono = _font(15)
        self.footer = _font(12)
        self.card_ticker = _font(14)
        self.card_name = _font(17)
        self.card_tag = _font(12)
        self.card_badge = _font(14)
        self.card_label = _font(12)
        self.card_fact = _font(14)
        self.range_label = _font(11)
        self.zone_note = _font(12)


def _pct_in_range(value, low, high):
    span = (high - low) or 1
    return max(0.0, min(1.0, (value - low) / span))


def _measure_fact(md, label, text, f, content_w):
    lines = _wrap(md, text, f.card_fact, content_w - 4)
    return 18 + len(lines) * 20 + 6, lines


def _holding_card_height(md, f, notes, content_w):
    h = 0
    h += 26          # ticker/name/tag + P&L badge 那一行
    h += 46          # 區間圖（含上下標籤）
    for label, text in notes["facts"]:
        fh, _ = _measure_fact(md, label, text, f, content_w)
        h += fh
    h += 18          # 卡片底部間距
    return h


def _draw_rangebar(draw, md, f, x, y, w, notes, price):
    range_low, range_high = notes["range"]
    zone_low, zone_high = notes["zone"]
    track_y = y + 14
    track_h = 6
    draw.rounded_rectangle([x, track_y, x + w, track_y + track_h], radius=3, fill=BORDER_SOFT)

    zp_low = _pct_in_range(zone_low, range_low, range_high)
    zp_high = _pct_in_range(zone_high, range_low, range_high)
    draw.rounded_rectangle(
        [x + w * zp_low, track_y, x + w * zp_high, track_y + track_h],
        radius=3, fill=ACCENT,
    )

    pp = _pct_in_range(price, range_low, range_high)
    dot_cx = x + w * pp
    draw.ellipse([dot_cx - 6, track_y + track_h / 2 - 6, dot_cx + 6, track_y + track_h / 2 + 6],
                 fill=INK_900, outline=CARD, width=2)

    # 下面一排：左邊界 / 觀察買點區間文字（置中） / 右邊界
    low_text = f"{range_low:g}"
    high_text = f"{range_high:g}"
    draw.text((x, track_y + 16), low_text, font=f.range_label, fill=INK_500)
    hw = md.textlength(high_text, font=f.range_label)
    draw.text((x + w - hw, track_y + 16), high_text, font=f.range_label, fill=INK_500)
    note_text = notes["zone_note"]
    nw = md.textlength(note_text, font=f.zone_note)
    draw.text((x + w / 2 - nw / 2, track_y + 16), note_text, font=f.zone_note, fill=ACCENT)


def _draw_holding_card(draw, md, f, x, y, content_w, code, name, quote, holding, notes):
    top = y
    draw.text((x, top), code, font=f.card_ticker, fill=INK_500)
    name_x = x + 62
    draw.text((name_x, top - 2), name, font=f.card_name, fill=INK_900)
    name_w = md.textlength(name, font=f.card_name)
    tag_x = name_x + name_w + 10
    draw.text((tag_x, top + 1), notes["tag"], font=f.card_tag, fill=INK_500)

    pl_color = GAIN if holding["pl_amount"] >= 0 else LOSS
    badge_text = f"{holding['pl_amount']:+,.0f} 元　{holding['pl_pct']:+.1f}%"
    bw = md.textlength(badge_text, font=f.card_badge)
    draw.text((x + content_w - bw, top), badge_text, font=f.card_badge, fill=pl_color)

    y = top + 26
    _draw_rangebar(draw, md, f, x, y, content_w, notes, quote["price"])
    y += 46

    for label, text in notes["facts"]:
        draw.text((x, y), label, font=f.card_label, fill=ACCENT)
        _, lines = _measure_fact(md, label, text, f, content_w)
        ty = y + 18
        for line in lines:
            draw.text((x, ty), line, font=f.card_fact, fill=INK_700)
            ty += 20
        y = ty + 6

    y += 8
    draw.line([(x, y), (x + content_w, y)], fill=BORDER, width=1)
    return y + 10 - top


def generate_report_image(slot_label: str, generated_at: str, rows: list[dict], commentary: str) -> str:
    """畫出報告卡片圖，回傳存檔後的檔名（不含路徑）。"""
    f = _Fonts()
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
    commentary_lines = _wrap(md, commentary_flat, f.body, content_w - 24)

    overview_lines = _wrap(md, stock_notes.MARKET_OVERVIEW, f.card_fact, content_w - 24)

    row_h = 34
    row_h_holding = 50  # 沒有深度筆記、但有成本價的持股（理論上不會發生，保底用）

    def _cat_rows_height(cat_rows):
        h = 0
        for r in cat_rows:
            notes = stock_notes.get_notes(r["quote"]["code"]) if r["holding"] else None
            if notes:
                h += _holding_card_height(md, f, notes, content_w)
            elif r["holding"]:
                h += row_h_holding
            else:
                h += row_h
        return h

    # ---- 第一遍：只算高度，不實際畫 ----
    y = PAD
    y += 20 + 8       # eyebrow
    y += 38 + 6       # title
    y += 20 + 20      # subtitle + gap
    y += 78 + 20      # stat strip + gap
    y += 20 + len(commentary_lines) * 22 + 16 + 24  # commentary box + gap
    y += 24 + len(overview_lines) * 20 + 16 + 24    # 大盤總覽 box + gap
    for cat, cat_rows in groups.items():
        y += 28 + _cat_rows_height(cat_rows) + 16
    disclaimer_text = config.DISCLAIMER.strip().lstrip("⚠️ ")
    footer_lines = _wrap(md, disclaimer_text, f.footer, content_w)
    y += 16 + len(footer_lines) * 16 + PAD

    height = y

    img = Image.new("RGB", (WIDTH, height), PAPER)
    draw = ImageDraw.Draw(img)

    y = PAD
    draw.text((PAD, y), "股市戰情室", font=f.eyebrow, fill=ACCENT)
    y += 20 + 8
    draw.text((PAD, y), slot_label, font=f.title, fill=INK_900)
    y += 38 + 6
    draw.text((PAD, y), f"產生時間 {generated_at}（台北時間）", font=f.subtitle, fill=INK_500)
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
        lw = md.textlength(label, font=f.stat_label)
        draw.text((cx + stat_w / 2 - lw / 2, y + 16), label, font=f.stat_label, fill=INK_500)
        vw = md.textlength(value, font=f.stat_value)
        draw.text((cx + stat_w / 2 - vw / 2, y + 40), value, font=f.stat_value, fill=color)
    y += stat_h + 20

    # AI 觀察（即時）
    box_h = 20 + len(commentary_lines) * 22 + 16
    draw.rounded_rectangle([PAD, y, PAD + content_w, y + box_h], radius=10, fill=ACCENT_SOFT)
    draw.text((PAD + 16, y + 12), "AI 觀察・即時", font=f.tag, fill=ACCENT)
    ty = y + 34
    for line in commentary_lines:
        draw.text((PAD + 16, ty), line, font=f.body, fill=INK_700)
        ty += 22
    y += box_h + 24

    # 大盤總覽（固定資料，查證時間點的總經彙整，不會每次更新）
    ov_box_h = 24 + len(overview_lines) * 20 + 16
    draw.rounded_rectangle([PAD, y, PAD + content_w, y + ov_box_h], radius=10, fill=CARD, outline=BORDER)
    draw.text((PAD + 16, y + 12), f"大盤總覽・資料時間 {stock_notes.AS_OF}", font=f.tag, fill=INK_500)
    ty = y + 36
    for line in overview_lines:
        draw.text((PAD + 16, ty), line, font=f.card_fact, fill=INK_700)
        ty += 20
    y += ov_box_h + 24

    # 各分類股票列表
    for cat, cat_rows in groups.items():
        draw.text((PAD, y), cat, font=f.cat, fill=INK_900)
        y += 28
        for r in cat_rows:
            q, ind, holding = r["quote"], r["indicators"], r["holding"]
            notes = stock_notes.get_notes(q["code"]) if holding else None
            if notes:
                y += _draw_holding_card(draw, md, f, PAD, y, content_w, q["code"], q["name"], q, holding, notes)
                continue

            this_row_h = row_h_holding if holding else row_h
            row_top = y
            draw.text((PAD, row_top), q["code"], font=f.row_mono, fill=INK_500)
            draw.text((PAD + 70, row_top), q["name"], font=f.row, fill=INK_900)
            price_text = str(q["price"])
            pw = md.textlength(price_text, font=f.row_mono)
            draw.text((PAD + content_w - 170 - pw, row_top), price_text, font=f.row_mono, fill=INK_900)
            change_text = f"{q['change_pct']:+.2f}%"
            change_color = GAIN if q["change_pct"] >= 0 else LOSS
            cw = md.textlength(change_text, font=f.row_mono)
            draw.text((PAD + content_w - cw, row_top), change_text, font=f.row_mono, fill=change_color)
            trend_text = ind.get("trend", "")
            tw = md.textlength(trend_text, font=f.footer)
            draw.text((PAD + content_w - 170 - pw - 16 - tw, row_top + 2), trend_text, font=f.footer, fill=INK_500)
            if holding:
                pl_color = GAIN if holding["pl_amount"] >= 0 else LOSS
                pl_text = (
                    f"成本 {holding['cost']}｜損益 {holding['pl_amount']:+,.0f} 元"
                    f"（{holding['pl_pct']:+.1f}%）"
                )
                draw.text((PAD + 70, row_top + 22), pl_text, font=f.footer, fill=pl_color)
            draw.line([(PAD, y + this_row_h - 6), (PAD + content_w, y + this_row_h - 6)], fill=BORDER, width=1)
            y += this_row_h
        y += 16

    # 免責聲明
    for line in footer_lines:
        draw.text((PAD, y), line, font=f.footer, fill=INK_500)
        y += 16

    filename = f"{uuid.uuid4().hex}.png"
    img.save(os.path.join(IMG_DIR, filename), "PNG")
    return filename
