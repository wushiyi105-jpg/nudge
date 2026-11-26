from __future__ import annotations

import json
from datetime import date

from nudge.adapters.llm.replay import ReplayClient
from nudge.adapters.store.sqlite import SqliteStore
from nudge.app.scan import scan
from nudge.config import Settings

TODAY = date(2026, 11, 27)


def make_store(tmp_path) -> SqliteStore:
    store = SqliteStore(tmp_path / "nudge.db")
    cid = store.add_client("青禾设计", avg_delay_days=21.0)
    store.add_invoice(cid, "INV-1", 125_000, date(2026, 9, 20), date(2026, 10, 20))
    return store


def test_offline_scan_generates_message_without_llm(tmp_path):
    store = make_store(tmp_path)
    result = scan(store, None, Settings(db_path=tmp_path / "nudge.db"), today=TODAY)
    assert len(result.items) == 1
    item = result.items[0]
    assert item.source == "offline"
    assert "1250.00" in item.message
    assert item.rec.stage >= 2  # 逾期 38 天 + 历史拖延，直接高挡


def test_second_scan_same_day_does_not_duplicate(tmp_path):
    store = make_store(tmp_path)
    settings = Settings(db_path=tmp_path / "nudge.db")
    first = scan(store, None, settings, today=TODAY)
    second = scan(store, None, settings, today=TODAY)
    assert first.items[0].enqueued is True
    assert second.items[0].enqueued is False


def test_scan_skips_not_yet_due_invoices(tmp_path):
    store = SqliteStore(tmp_path / "nudge.db")
    cid = store.add_client("北岸书店")
    store.add_invoice(cid, "INV-2", 50_000, date(2026, 11, 1), date(2026, 12, 31))
    result = scan(store, None, Settings(db_path=tmp_path / "nudge.db"), today=TODAY)
    assert result.items == []
    assert result.skipped == 1


def test_llm_numbers_outside_ledger_are_dropped(tmp_path, monkeypatch):
    store = make_store(tmp_path)

    class LyingLLM:
        def complete(self, system: str, prompt: str) -> str:
            return "INV-1 欠 1250.00 元。另需支付违约金 500 元。"

    result = scan(store, LyingLLM(), Settings(db_path=tmp_path / "nudge.db"), today=TODAY)
    item = result.items[0]
    assert "500" not in item.message
    assert "违约金" not in item.message
    assert "500" in item.dropped_numbers
    assert item.source == "llm"


def test_llm_failure_falls_back_to_offline(tmp_path):
    store = make_store(tmp_path)

    class BrokenLLM:
        def complete(self, system: str, prompt: str) -> str:
            raise RuntimeError("boom")

    result = scan(store, BrokenLLM(), Settings(db_path=tmp_path / "nudge.db"), today=TODAY)
    assert result.items[0].source == "offline"


def test_replay_client_reads_fixture(tmp_path):
    fixture = tmp_path / "fx"
    fixture.mkdir()
    system, prompt = "sys", "hello"
    key = ReplayClient.key(system, prompt)
    (fixture / f"{key}.json").write_text(json.dumps({"content": "回放命中"}), encoding="utf-8")
    client = ReplayClient(fixture)
    assert client.complete(system, prompt) == "回放命中"
    assert client.calls == [key]
