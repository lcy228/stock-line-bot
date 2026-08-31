# -*- coding: utf-8 -*-
"""
直接呼叫 LINE Messaging API 的 REST 介面（不依賴特定版本的 SDK，比較不會因為套件改版而壞掉）。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import requests

API_BASE = "https://api.line.me/v2/bot"


def _channel_access_token() -> str:
    return os.environ["LINE_CHANNEL_ACCESS_TOKEN"]


def _channel_secret() -> str:
    return os.environ["LINE_CHANNEL_SECRET"]


def verify_signature(body: bytes, signature: str) -> bool:
    mac = hmac.new(_channel_secret().encode("utf-8"), body, hashlib.sha256)
    expected = base64.b64encode(mac.digest()).decode("utf-8")
    return hmac.compare_digest(expected, signature or "")


def _headers():
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_channel_access_token()}",
    }


def broadcast_text_and_image(text: str, image_urls=None):
    """廣播給這個官方帳號的所有好友（也就是你自己），不用另外儲存 userId。
    image_urls 可以放多張圖（例如報告卡片 + 漲跌幅圖表），LINE 一次最多 5 則訊息，
    這裡文字算 1 則，圖片最多再放 4 張。"""
    messages = [{"type": "text", "text": text[:4900]}]
    for url in (image_urls or [])[:4]:
        messages.append({
            "type": "image",
            "originalContentUrl": url,
            "previewImageUrl": url,
        })
    resp = requests.post(
        f"{API_BASE}/message/broadcast",
        headers=_headers(),
        json={"messages": messages},
        timeout=15,
    )
    resp.raise_for_status()


def reply_text(reply_token: str, text: str):
    resp = requests.post(
        f"{API_BASE}/message/reply",
        headers=_headers(),
        json={"replyToken": reply_token, "messages": [{"type": "text", "text": text[:4900]}]},
        timeout=15,
    )
    resp.raise_for_status()


def reply_text_and_image(reply_token: str, text: str, image_url: str):
    """聊天室即時查詢個股用：回覆一則文字＋一張報告卡片圖（用 reply 不是
    broadcast，這樣完全免費、不限次數，也只有問的人自己看得到）。"""
    messages = [
        {"type": "text", "text": text[:4900]},
        {"type": "image", "originalContentUrl": image_url, "previewImageUrl": image_url},
    ]
    resp = requests.post(
        f"{API_BASE}/message/reply",
        headers=_headers(),
        json={"replyToken": reply_token, "messages": messages},
        timeout=15,
    )
    resp.raise_for_status()
