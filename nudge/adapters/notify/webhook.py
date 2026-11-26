"""群机器人 webhook：飞书 / 钉钉 / 企业微信同构，默认按飞书文本消息格式发。"""

from __future__ import annotations

import httpx


class WebhookNotifier:
    def __init__(self, url: str, timeout: float = 10.0) -> None:
        self.url = url
        self.timeout = timeout

    def send(self, title: str, text: str) -> bool:
        if not self.url:
            return False
        body = {"msg_type": "text", "content": {"text": f"{title}\n{text}"}}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(self.url, json=body)
                return resp.status_code < 300
        except httpx.HTTPError:
            return False
