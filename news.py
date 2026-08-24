# -*- coding: utf-8 -*-
"""
新聞抓取：用 Google News RSS 搜尋（免費、不需金鑰）。
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
import requests

RSS_URL = "https://news.google.com/rss/search"

_session = requests.Session()
_session.headers.update({"User-Agent": "Mozilla/5.0 (LineStockBot/1.0)"})


def get_headlines(keyword: str, limit: int = 3) -> list[dict]:
    """搜尋關鍵字（例如「2330 台積電」），回傳最新新聞標題與連結。"""
    try:
        resp = _session.get(
            RSS_URL,
            params={"q": keyword, "hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant"},
            timeout=8,
        )
        root = ET.fromstring(resp.content)
        items = []
        for item in root.findall("./channel/item")[:limit]:
            title = item.findtext("title") or ""
            link = item.findtext("link") or ""
            items.append({"title": title, "link": link})
        return items
    except Exception:
        return []
