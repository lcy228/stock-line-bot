# -*- coding: utf-8 -*-
"""
新聞抓取：用 Google News RSS 搜尋（免費、不需金鑰）。

老實說的限制：Google News RSS 的連結是 Google 自己的轉址頁面，需要瀏覽器執行
JavaScript 才會真正跳到原始新聞網站，伺服器端沒辦法直接把全文抓下來顯示；
RSS 本身也沒有提供文章摘要（description 欄位只是把標題再包一次，不是真的摘要）。
所以「網站點開新聞不跳頁」這個功能，只能就地顯示標題／來源／時間這些 RSS 本身
就有的資訊，看完整內容還是要點連結去原網站——這點已經跟使用者說明過。
"""
from __future__ import annotations

import datetime
import xml.etree.ElementTree as ET
import requests

RSS_URL = "https://news.google.com/rss/search"

_session = requests.Session()
_session.headers.update({"User-Agent": "Mozilla/5.0 (LineStockBot/1.0)"})


def _format_pubdate(raw: str) -> str:
    """RSS pubDate 是 RFC 822 格式（例如 Fri, 25 Sep 2026 16:21:50 GMT），
    轉成比較好讀的「09/25 16:21」（GMT，沒有另外換算時區，只是給個大概時間感）。"""
    try:
        dt = datetime.datetime.strptime(raw, "%a, %d %b %Y %H:%M:%S %Z")
        return dt.strftime("%m/%d %H:%M")
    except (ValueError, TypeError):
        return ""


def get_headlines(keyword: str, limit: int = 3) -> list[dict]:
    """搜尋關鍵字（例如「2330 台積電」），回傳最新新聞標題、連結、來源、時間。"""
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
            source = item.findtext("source") or ""
            pub_date = _format_pubdate(item.findtext("pubDate") or "")
            items.append({"title": title, "link": link, "source": source, "pub_date": pub_date})
        return items
    except Exception:
        return []
