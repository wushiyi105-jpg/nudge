"""回放适配器：从 fixtures 读录制好的模型响应，测试不花钱、不连网。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


class ReplayClient:
    def __init__(self, fixture_dir: Path) -> None:
        self.dir = Path(fixture_dir)
        self.calls: list[str] = []

    @staticmethod
    def key(system: str, prompt: str) -> str:
        return hashlib.sha256((system + "\x00" + prompt).encode()).hexdigest()[:16]

    def complete(self, system: str, prompt: str) -> str:
        self.calls.append(self.key(system, prompt))
        path = self.dir / f"{self.key(system, prompt)}.json"
        if not path.exists():
            raise FileNotFoundError(f"没有录制响应：{path.name}")
        return json.loads(path.read_text(encoding="utf-8"))["content"]
