"""OpenAI 兼容模型适配器：httpx + 超时 + 退避重试 + 空 content 重试。"""

from __future__ import annotations

import time
from typing import Any

import httpx


class OpenAICompatClient:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 30.0, max_tokens: int = 1200) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens

    def complete(self, system: str, prompt: str, *, retries: int = 3) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": self.max_tokens,
        }
        last_error = ""
        for attempt in range(retries):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(
                        f"{self.base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json=payload,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                choice = (data.get("choices") or [{}])[0]
                content = (choice.get("message") or {}).get("content") or ""
                if content.strip():
                    return content.strip()
                last_error = "empty content"
                payload["max_tokens"] = min(int(payload["max_tokens"]) * 2, 8000)
            except (httpx.HTTPError, ValueError) as exc:  # noqa: PERF203
                last_error = str(exc)
            time.sleep(0.5 * (2**attempt))
        raise RuntimeError(f"LLM 调用失败：{last_error}")
