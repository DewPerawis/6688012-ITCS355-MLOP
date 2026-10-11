"""Deliver a generic Slack/Discord text webhook; never store its URL in evidence."""
from __future__ import annotations

import json
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def deliver(url: str, text: str) -> dict:
    if urlsplit(url).scheme != "https":
        raise ValueError("alert webhook must use HTTPS")
    payload = {"content": text} if urlsplit(url).hostname in {"discord.com", "discordapp.com"} else {"text": text}
    request = Request(url, data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json",
                               "User-Agent": "DiscordBot (https://github.com/DewPerawis/6688012-ITCS355-MLOP, 1.0)"},
                      method="POST")
    with urlopen(request, timeout=30) as response:
        if not 200 <= response.status < 300:
            raise RuntimeError("alert channel rejected delivery")
        return {"http_status": response.status, "accepted": True,
                "recipient_receipt": "capture actual notification separately"}
