# -*- coding: utf-8 -*-
"""
股票資料抓取：即時報價（證交所 MIS）+ 歷史日線（證交所 OpenAPI）+ 簡單技術指標
+ 三大法人買賣超（證交所／櫃買中心公開資料）。
全部使用免費、不需金鑰的公開資料源，不靠 AI 猜數字。
"""
from __future__ import annotations

import datetime
import requests

MIS_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
DAY_URL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
TWSE_T86_URL = "https://www.twse.com.tw/rwd/zh/fund/T86"
TPEX_INSTI_URL = "https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade"

_session = requests.Session()
_session.headers.update({"User-Agent": "Mozilla/5.0 (LineStockBot/1.0)"})

# 一天份的三大法人買賣超資料有上萬筆，查一次代號就整天快取起來，
# 不用每次聊天室問一檔股票就重新抓一次全市場資料。Render 免費方案
# 常常會重啟，這個快取本來就不會活太久，不用特別做過期機制。
_inst_cache: dict[str, dict[str, tuple[int, int]] | None] = {}


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


def _fetch_twse_institutional(date_str: str) -> dict[str, tuple[int, int]] | None:
    """抓上市（TSE）當天三大法人買賣超，回傳 {代號: (外資買賣超股數, 三大法人合計買賣超股數)}。"""
    try:
        resp = _session.get(
            TWSE_T86_URL,
            params={"date": date_str, "selectType": "ALL", "response": "json"},
            timeout=10,
        )
        data = resp.json()
        if data.get("stat") != "OK":
            return None
        result = {}
        for row in data.get("data", []):
            code = row[0].strip()
            result[code] = (_to_int(row[4]), _to_int(row[-1]))
        return result
    except Exception:
        return None


def _fetch_tpex_institutional(date_str: str) -> dict[str, tuple[int, int]] | None:
    """抓上櫃（TPEx）當天三大法人買賣超，格式跟 TSE 略有不同，但一樣是
    「代號、名稱、[外資買/賣/買賣超]、...、三大法人合計買賣超」的排列方式。"""
    try:
        year = int(date_str[:4]) - 1911
        roc_date = f"{year}/{date_str[4:6]}/{date_str[6:8]}"
        resp = _session.get(
            TPEX_INSTI_URL,
            params={"type": "Daily", "sect": "EW", "date": roc_date, "id": "", "response": "json"},
            timeout=10,
        )
        data = resp.json()
        tables = data.get("tables") or []
        if not tables:
            return None
        result = {}
        for row in tables[0].get("data", []):
            code = row[0].strip()
            result[code] = (_to_int(row[4]), _to_int(row[-1]))
        return result
    except Exception:
        return None


def get_institutional_trading(code: str) -> dict | None:
    """查最近一個有公布資料的交易日三大法人買賣超（股數）。盤中查詢通常會拿到
    前一個交易日的數字，因為證交所要收盤後才會公布當天資料；最多往回找 6 天
    避開連續假日。抓不到（代號錯誤、資料源異常）回傳 None，呼叫端要自己處理。"""
    today = datetime.date.today()
    for back in range(6):
        d = today - datetime.timedelta(days=back)
        date_str = d.strftime("%Y%m%d")

        tse_key = f"tse_{date_str}"
        if tse_key not in _inst_cache:
            _inst_cache[tse_key] = _fetch_twse_institutional(date_str)
        tse_data = _inst_cache[tse_key]
        if tse_data and code in tse_data:
            foreign_net, total_net = tse_data[code]
            return {"date": d.strftime("%Y/%m/%d"), "foreign_net": foreign_net, "total_net": total_net}

        otc_key = f"otc_{date_str}"
        if otc_key not in _inst_cache:
            _inst_cache[otc_key] = _fetch_tpex_institutional(date_str)
        otc_data = _inst_cache[otc_key]
        if otc_data and code in otc_data:
            foreign_net, total_net = otc_data[code]
            return {"date": d.strftime("%Y/%m/%d"), "foreign_net": foreign_net, "total_net": total_net}
    return None


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


def _to_int(v):
    try:
        return int(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0


def parse_roc_date(s: str) -> datetime.date | None:
    """把 get_daily_history() 回傳的民國日期字串（例如「115/09/21」）轉成
    datetime.date，畫走勢圖的 X 軸要用。格式不對就回傳 None。"""
    try:
        y, m, d = s.split("/")
        return datetime.date(int(y) + 1911, int(m), int(d))
    except (ValueError, AttributeError):
        return None
