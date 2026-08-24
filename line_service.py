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


def broadcast_text_and_image(text: str, image_url: str | None = None):
    """廣播給這個官方帳號的所有好友（也就是你自己），不用另外儲存 userId。"""
    messages = [{"type": "text", "text": text[:4900]}]
    if image_url:
        messages.append({
            "type": "image",
            "originalContentUrl": image_url,
            "previewImageUrl": image_url,
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
