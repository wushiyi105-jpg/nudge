"""真实内存 Store 跑 scan：不建 SQLite，mypy 校验 StorePort。"""

from __future__ import annotations

from datetime import date
from typing import Any

from nudge.app.scan import scan
from nudge.config import Settings
from nudge.domain.models import Client, Invoice
from nudge.ports import Store


class InMemoryStore:
    def list_clients(self) -> list[Client]:
        return []

    def client(self, client_id: int) -> Client | None:
        return None

    def list_open_invoices(self) -> list[Invoice]:
        return []

    def enqueue(self, kind: str, payload: dict, idempotency_key: str) -> bool:
        return True

    def due_jobs(self, limit: int = 20) -> list[Any]:
        return []

    def finish_job(self, job_id: int, ok: bool, error: str = "") -> None:
        return None

    def start_run(self) -> int:
        return 1

    def finish_run(self, run_id: int, summary: str) -> None:
        return None


def test_scan_with_memory_store(tmp_path) -> None:
    store: Store = InMemoryStore()
    out = scan(store, None, Settings(db_path=tmp_path / "x.db"), today=date(2026, 1, 5))
    assert out.run_id == 1
    assert not (tmp_path / "x.db").exists()
