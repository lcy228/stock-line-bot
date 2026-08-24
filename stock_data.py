# -*- coding: utf-8 -*-
"""
股票資料抓取：即時報價（證交所 MIS）+ 歷史日線（證交所 OpenAPI）+ 簡單技術指標。
全部使用免費、不需金鑰的公開資料源。
"""
from __future__ import annotations

import datetime
import requests

MIS_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
DAY_URL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"

_session = requests.Session()
_session.headers.update({"User-Agent": "Mozilla/5.0 (LineStockBot/1.0)"})


def get_realtime_quote(code: str) -> dict | None:
    """抓單一股票即時報價，若上市（tse）查不到會嘗試上櫃（otc）。"""
    for market in ("tse", "otc"):
        try:
            resp = _session.get(
                MIS_URL,
                params={"ex_ch": f"{market}_{code}.tw", "json": 1, "delay": 0},
                timeout=8,
            )
            data = resp.json()
            arr = data.get("msgArray") or []
            if not arr:
                continue
            row = arr[0]
            price = _to_float(row.get("z")) or _to_float(row.get("o"))
            prev_close = _to_float(row.get("y"))
            if price is None or prev_close is None or prev_close == 0:
                continue
            change = price - prev_close
            change_pct = change / prev_close * 100
            return {
                "code": code,
                "name": row.get("n") or code,
                "price": price,
                "open": _to_float(row.get("o")),
                "high": _to_float(row.get("h")),
                "low": _to_float(row.get("l")),
                "prev_close": prev_close,
                "change": change,
                "change_pct": change_pct,
                "volume_lots": _to_float(row.get("v")),
                "time": row.get("t"),
            }
        except Exception:
            continue
    return None


def get_daily_history(code: str, months_back: int = 2) -> list[dict]:
    """抓最近 N 個月的日線資料（收盤價），用來算均線與 RSI。"""
    today = datetime.date.today()
    rows: list[dict] = []
    for i in range(months_back, -1, -1):
        year = today.year
        month = today.month - i
        while month <= 0:
            month += 12
            year -= 1
        date_str = f"{year}{month:02d}01"
        try:
            resp = _session.get(
                DAY_URL,
                params={"response": "json", "date": date_str, "stockNo": code},
                timeout=8,
            )
            data = resp.json()
            if data.get("stat") != "OK":
                continue
            for r in data.get("data", []):
                # r: [日期, 成交股數, 成交金額, 開盤, 最高, 最低, 收盤, 漲跌價差, 成交筆數]
                close = _to_float(r[6])
                if close is None:
                    continue
                rows.append({"date": r[0], "close": close})
        except Exception:
            continue
    return rows


def compute_indicators(history: list[dict]) -> dict:
    """從日線收盤價算 MA5 / MA20 / RSI14，資料不足就回傳 None 值。"""
    closes = [r["close"] for r in history]
    result = {"ma5": None, "ma20": None, "rsi14": None, "trend": "資料不足"}
    if len(closes) >= 5:
        result["ma5"] = round(sum(closes[-5:]) / 5, 2)
    if len(closes) >= 20:
        result["ma20"] = round(sum(closes[-20:]) / 20, 2)
    if len(closes) >= 15:
        gains, losses = [], []
        for i in range(-14, 0):
            diff = closes[i] - closes[i - 1]
            gains.append(max(diff, 0))
            losses.append(max(-diff, 0))
        avg_gain = sum(gains) / 14
        avg_loss = sum(losses) / 14
        if avg_loss == 0:
            result["rsi14"] = 100.0
        else:
            rs = avg_gain / avg_loss
            result["rsi14"] = round(100 - (100 / (1 + rs)), 1)
    if result["ma5"] and result["ma20"]:
        result["trend"] = "均線偏多（MA5 > MA20）" if result["ma5"] > result["ma20"] else "均線偏空（MA5 < MA20）"
    return result


def _to_float(v):
    try:
        if v in (None, "", "-"):
            return None
        if isinstance(v, str):
            v = v.replace(",", "").strip()
            if v in ("", "-", "--"):
                return None
        return float(v)
    except (TypeError, ValueError):
        return None
