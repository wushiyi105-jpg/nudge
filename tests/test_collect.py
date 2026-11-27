"""新功能：今日催款清单与三档话术。"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from nudge.domain.catalog import templates
from nudge.iface.cli import app


def test_ledger_has_thirty_clients_and_ten_templates() -> None:
    assert len(templates()) == 10
    data = json.loads((Path(__file__).resolve().parents[1] / "data" / "seed.json").read_text(encoding="utf-8"))
    assert len(data["clients"]) == 30


def test_collect_cli_writes_three_messages_per_client(tmp_path) -> None:
    runner = CliRunner()
    db = str(tmp_path / "nudge.db")
    assert runner.invoke(app, ["seed", "--db", db]).exit_code == 0
    out = tmp_path / "今日催款.md"
    result = runner.invoke(
        app, ["collect", "--db", db, "--today", "2026-11-27", "--out", str(out)]
    )
    assert result.exit_code == 0
    body = out.read_text(encoding="utf-8")
    assert "# 今日催款清单" in body
    assert "温和版" in body and "明确版" in body and "最后版" in body
    assert "回款率" in body
    assert "账龄分布" in body
