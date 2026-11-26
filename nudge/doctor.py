"""自检：配置 / 数据库 / 模型 / webhook，一条命令看清环境。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import httpx

from .config import Settings


def _check_db(settings: Settings) -> tuple[bool, str]:
    path: Path = settings.db_path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
    except Exception as exc:  # noqa: BLE001
        return False, f"{path} 不可写：{exc}"
    need = {"clients", "invoices", "jobs", "runs"}
    missing = need - tables
    if missing:
        return False, f"缺表 {sorted(missing)}，先跑 seed 或启动一次"
    return True, f"{path}（{len(tables)} 张表）"


def _check_llm(settings: Settings) -> tuple[bool, str]:
    if not settings.llm_enabled:
        return True, "未配置 API key，走离线模式"
    try:
        with httpx.Client(timeout=8) as c:
            r = c.get(f"{settings.llm_base_url.rstrip('/')}/models",
                      headers={"Authorization": f"Bearer {settings.llm_api_key}"})
        return r.status_code < 400, f"{settings.llm_model} · HTTP {r.status_code}"
    except httpx.HTTPError as exc:
        return False, f"连不上：{exc}"


def _check_webhook(settings: Settings) -> tuple[bool, str]:
    if not settings.webhook_url:
        return True, "未配置 webhook，跳过推送"
    try:
        with httpx.Client(timeout=8) as c:
            r = c.post(settings.webhook_url, json={"msg_type": "text", "content": {"text": "Nudge doctor 探活"}})
        return r.status_code < 300, f"HTTP {r.status_code}"
    except httpx.HTTPError as exc:
        return False, f"连不上：{exc}"


def run_doctor(settings: Settings) -> list[tuple[str, bool, str]]:
    return [
        ("config", True, f"db={settings.db_path} stage2={settings.stage2_days}d stage3={settings.stage3_days}d"),
        ("database", *_check_db(settings)),
        ("llm", *_check_llm(settings)),
        ("webhook", *_check_webhook(settings)),
    ]
