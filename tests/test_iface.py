from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from nudge.adapters.notify.webhook import WebhookNotifier
from nudge.adapters.store.sqlite import SqliteStore
from nudge.app.jobs import process_jobs
from nudge.config import Settings
from nudge.doctor import run_doctor
from nudge.iface.cli import app
from nudge.iface.web import create_app

runner = CliRunner()


def make_store(tmp_path: Path) -> SqliteStore:
    store = SqliteStore(tmp_path / "nudge.db")
    cid = store.add_client("青禾设计", "王工", avg_delay_days=21.0)
    store.add_invoice(cid, "INV-2026-011", 860_000, date(2026, 9, 20), date(2026, 10, 20))
    cid2 = store.add_client("北岸书店", "李姐", avg_delay_days=3.0)
    store.add_invoice(cid2, "INV-2026-014", 240_000, date(2026, 10, 25), date(2026, 11, 24))
    return store


def make_settings(tmp_path: Path) -> Settings:
    return Settings(db_path=tmp_path / "nudge.db", llm_api_key="", webhook_url="")


def test_web_index_empty(tmp_path: Path) -> None:
    client = TestClient(create_app(make_settings(tmp_path)))
    body = client.get("/").text
    assert client.get("/").status_code == 200
    assert "今天先收回哪几笔" in body
    assert "0.00" in body


def test_web_index_bucket_and_total(tmp_path: Path) -> None:
    make_store(tmp_path)
    client = TestClient(create_app(make_settings(tmp_path)))
    body = client.get("/").text
    assert "INV-2026-011" in body
    assert "31-60" in body or "61-90" in body
    assert "11000.00" in body


def test_web_index_shows_scanned_flash(tmp_path: Path) -> None:
    make_store(tmp_path)
    client = TestClient(create_app(make_settings(tmp_path)))
    body = client.get("/", params={"scanned": "2"}).text
    assert "生成 2 条催收建议" in body


def test_web_scan_offline_redirects_with_count(tmp_path: Path) -> None:
    make_store(tmp_path)
    client = TestClient(create_app(make_settings(tmp_path)))
    r = client.post("/scan", data={"offline": "1"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/?scanned=")
    assert int(r.headers["location"].split("=")[1]) >= 1


def test_web_pay_reduces_outstanding(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    inv = store.list_open_invoices()[0]
    client = TestClient(create_app(make_settings(tmp_path)))
    r = client.post(f"/pay/{inv.id}", data={"amount": "1000"}, follow_redirects=False)
    assert r.status_code == 303
    after = [i for i in store.list_open_invoices() if i.id == inv.id][0]
    assert after.outstanding_cents == inv.outstanding_cents - 100_000


def test_web_health(tmp_path: Path) -> None:
    client = TestClient(create_app(make_settings(tmp_path)))
    assert client.get("/health").json() == {"status": "ok"}


def test_cli_seed_then_report(tmp_path: Path) -> None:
    db = str(tmp_path / "cli.db")
    seed = runner.invoke(app, ["seed", "--db", db])
    assert seed.exit_code == 0
    assert "已写入" in seed.output
    report = runner.invoke(app, ["report", "--db", db])
    assert report.exit_code == 0
    assert "账龄分布" in report.output


def test_cli_scan_json_offline(tmp_path: Path) -> None:
    db = str(tmp_path / "cli.db")
    runner.invoke(app, ["seed", "--db", db])
    r = runner.invoke(app, ["scan", "--db", db, "--offline", "--json"])
    assert r.exit_code == 0
    payload = json.loads(r.output[r.output.index("{") : r.output.rindex("}") + 1])
    assert len(payload["items"]) >= 1
    assert payload["items"][0]["source"] == "offline"
    assert payload["items"][0]["days_overdue"] > 0


def test_cli_scan_table_output(tmp_path: Path) -> None:
    db = str(tmp_path / "cli.db")
    runner.invoke(app, ["seed", "--db", db])
    r = runner.invoke(app, ["scan", "--db", db, "--offline"])
    assert r.exit_code == 0
    assert "待催" in r.output


def test_cli_jobs_dry_run_then_send(tmp_path: Path) -> None:
    db = str(tmp_path / "cli.db")
    runner.invoke(app, ["seed", "--db", db])
    runner.invoke(app, ["scan", "--db", db, "--offline"])
    dry = runner.invoke(app, ["jobs", "--db", db, "--dry-run"])
    assert dry.exit_code == 0
    assert "条待发" in dry.output
    send = runner.invoke(app, ["jobs", "--db", db])
    assert send.exit_code == 0
    assert "发送成功 0" in send.output


def test_cli_pay(tmp_path: Path) -> None:
    db = str(tmp_path / "cli.db")
    runner.invoke(app, ["seed", "--db", db])
    r = runner.invoke(app, ["pay", "1", "--amount", "800", "--db", db])
    assert r.exit_code == 0
    assert "800.00" in r.output


def test_cli_doctor_green(tmp_path: Path) -> None:
    db = str(tmp_path / "cli.db")
    runner.invoke(app, ["seed", "--db", db])
    r = runner.invoke(app, ["doctor", "--db", db])
    assert r.exit_code == 0
    assert "fail" not in r.output


def test_cli_doctor_flags_missing_tables(tmp_path: Path) -> None:
    r = runner.invoke(app, ["doctor", "--db", str(tmp_path / "blank.db")])
    assert r.exit_code == 1
    assert "缺表" in r.output


def test_run_doctor_reports_config_and_offline_flags(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    rows = run_doctor(settings)
    names = [r[0] for r in rows]
    assert names == ["config", "database", "llm", "webhook"]
    llm = [r for r in rows if r[0] == "llm"][0]
    assert llm[1] is True and "离线模式" in llm[2]


def test_doctor_database_check_fails_on_missing_tables(tmp_path: Path) -> None:
    rows = run_doctor(make_settings(tmp_path))
    db = [r for r in rows if r[0] == "database"][0]
    assert db[1] is False
    assert "缺表" in db[2]


def test_process_jobs_with_fake_notifier(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "jobs.db")
    store.enqueue("reminder", {"client": "青禾设计", "stage": 2, "message": "请回款"}, "k-1")

    class Ok:
        def send(self, title: str, text: str) -> bool:
            return True

    ok, failed = process_jobs(store, Ok())
    assert (ok, failed) == (1, 0)
    assert store.due_jobs() == []


def test_process_jobs_marks_failure_when_notifier_raises(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "jobs.db")
    store.enqueue("reminder", {"client": "北岸书店", "stage": 1, "message": "请回款"}, "k-2")

    class Boom:
        def send(self, title: str, text: str) -> bool:
            raise RuntimeError("webhook 500")

    ok, failed = process_jobs(store, Boom())
    assert (ok, failed) == (0, 1)


def test_webhook_notifier_without_url_returns_false() -> None:
    assert WebhookNotifier("").send("催收", "正文") is False


@respx.mock
def test_webhook_notifier_posts_feishu_text_payload() -> None:
    route = respx.post("https://hook.example.com/bot").mock(return_value=httpx.Response(200, json={"code": 0}))
    assert WebhookNotifier("https://hook.example.com/bot").send("催收", "正文") is True
    body = json.loads(route.calls[0].request.content)
    assert body["msg_type"] == "text"
    assert "催收" in body["content"]["text"]


@respx.mock
def test_webhook_notifier_returns_false_on_http_error() -> None:
    respx.post("https://hook.example.com/bot").mock(return_value=httpx.Response(500))
    assert WebhookNotifier("https://hook.example.com/bot").send("催收", "正文") is False


@respx.mock
def test_webhook_notifier_returns_false_on_network_error() -> None:
    respx.post("https://hook.example.com/bot").mock(side_effect=httpx.ConnectError("boom"))
    assert WebhookNotifier("https://hook.example.com/bot").send("催收", "正文") is False


@pytest.mark.parametrize(("days_overdue", "bucket"), [(0, "current"), (20, "1-30"), (45, "31-60"), (75, "61-90"), (120, "90+")])
def test_web_bucket_labels(tmp_path: Path, days_overdue: int, bucket: str) -> None:
    db = tmp_path / f"b{days_overdue}.db"
    store = SqliteStore(db)
    cid = store.add_client("客户A")
    due = date.fromordinal(date.today().toordinal() - days_overdue)
    store.add_invoice(cid, "INV-B", 100_000, due, due)
    body = TestClient(create_app(Settings(db_path=db, llm_api_key="", webhook_url=""))).get("/").text
    assert "INV-B" in body
    assert bucket in body
