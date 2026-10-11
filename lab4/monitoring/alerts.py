"""Deliver a generic Slack/Discord text webhook; never store its URL in evidence."""
from __future__ import annotations

import json
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def deliver(url: str, text: str) -> dict:
    if urlsplit(url).scheme != "https":
        raise ValueError("alert webhook must use HTTPS")
    request = Request(url, data=json.dumps({"text": text, "content": text}).encode(),
                      headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=30) as response:
        if not 200 <= response.status < 300:
            raise RuntimeError("alert channel rejected delivery")
        return {"http_status": response.status, "accepted": True,
                "recipient_receipt": "capture actual notification separately"}
