# -*- coding: utf-8 -*-
"""
上市（TSE）+ 上櫃（TPEx）全市場公司清單，依證交所官方「產業別」分類分組。
用來畫網站首頁的分類格子，以及點進分類後的個股清單。

資料來源都是公開、不用金鑰的 OpenAPI；產業別代碼對照表是證交所
「證券編碼_分類查詢」頁面（isin.twse.com.tw）目前使用的官方 33 類。
"""
from __future__ import annotations

import requests

TSE_COMPANY_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TPEX_COMPANY_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"

_session = requests.Session()
_session.headers.update({"User-Agent": "Mozilla/5.0 (LineStockBot/1.0)"})

# 證交所官方產業別代碼 -> 名稱（isin.twse.com.tw/isin/class_i.jsp?kind=1）
INDUSTRY_NAMES = {
    "01": "水泥工業", "02": "食品工業", "03": "塑膠工業", "04": "紡織纖維",
    "05": "電機機械", "06": "電器電纜", "08": "玻璃陶瓷", "09": "造紙工業",
    "10": "鋼鐵工業", "11": "橡膠工業", "12": "汽車工業", "13": "電子工業",
    "14": "建材營造業", "15": "航運業", "16": "觀光餐旅", "17": "金融保險業",
    "18": "貿易百貨業", "19": "綜合", "20": "其他業", "21": "化學工業",
    "22": "生技醫療業", "23": "油電燃氣業", "24": "半導體業",
    "25": "電腦及週邊設備業", "26": "光電業", "27": "通信網路業",
    "28": "電子零組件業", "29": "電子通路業", "30": "資訊服務業",
    "31": "其他電子業", "32": "文化創意業", "33": "農業科技業",
    "35": "綠能環保", "36": "數位雲端", "37": "運動休閒", "38": "居家生活",
    "91": "存託憑證",
}

# 模組層級快取：整個上市櫃公司清單一次抓齊、分組好，之後同一個 process
# 存活期間都重複使用，不用每個請求都重新打一次幾千筆資料的 API。
# Render 免費方案常常重啟，快取本來就不會活太久，不用特別做過期機制。
_directory: dict | None = None


def _fetch_list(url: str, code_key: str, name_key: str, industry_key: str) -> list[tuple[str, str, str]]:
    """回傳 [(股票代號, 公司簡稱, 產業別代碼), ...]，抓不到就回傳空清單。"""
    try:
        resp = _session.get(url, timeout=15)
        data = resp.json()
        rows = []
        for row in data:
            code = (row.get(code_key) or "").strip()
            name = (row.get(name_key) or "").strip()
            industry = (row.get(industry_key) or "").strip()
            if code and name:
                rows.append((code, name, industry))
        return rows
    except Exception:
        return []


def _build_directory() -> dict:
    tse_rows = _fetch_list(TSE_COMPANY_URL, "公司代號", "公司簡稱", "產業別")
    otc_rows = _fetch_list(TPEX_COMPANY_URL, "SecuritiesCompanyCode", "CompanyAbbreviation", "SecuritiesIndustryCode")
    all_rows = tse_rows + otc_rows

    by_industry: dict[str, list[tuple[str, str]]] = {}
    by_code: dict[str, str] = {}
    for code, name, industry in all_rows:
        by_code[code] = name
        by_industry.setdefault(industry, []).append((code, name))

    for companies in by_industry.values():
        companies.sort(key=lambda c: c[0])

    return {"by_industry": by_industry, "by_code": by_code}


def _get_directory() -> dict:
    global _directory
    if _directory is None:
        _directory = _build_directory()
    return _directory


def list_industries() -> list[dict]:
    """回傳每個產業別的代碼、名稱、公司數，依公司數由多到少排序，
    首頁的分類格子大小要用公司數決定。"""
    directory = _get_directory()
    items = []
    for code, companies in directory["by_industry"].items():
        items.append({
            "code": code,
            "name": INDUSTRY_NAMES.get(code, f"其他（{code}）"),
            "count": len(companies),
        })
    items.sort(key=lambda x: x["count"], reverse=True)
    return items


def get_industry_companies(code: str) -> list[tuple[str, str]]:
    """回傳某個產業別底下所有公司的 [(代號, 簡稱), ...]。"""
    return _get_directory()["by_industry"].get(code, [])


def get_industry_name(code: str) -> str:
    return INDUSTRY_NAMES.get(code, f"其他（{code}）")


def get_company_name(code: str) -> str | None:
    return _get_directory()["by_code"].get(code)


def search_companies(keyword: str, limit: int = 20) -> list[tuple[str, str]]:
    """用代號或名稱關鍵字搜尋公司，代號完全相符的排最前面。"""
    keyword = keyword.strip()
    if not keyword:
        return []
    directory = _get_directory()
    by_code = directory["by_code"]

    if keyword in by_code:
        return [(keyword, by_code[keyword])]

    matches = []
    for code, name in by_code.items():
        if keyword.upper() in code.upper() or keyword in name:
            matches.append((code, name))
    matches.sort(key=lambda c: (keyword not in c[1][:len(keyword)], c[0]))
    return matches[:limit]
