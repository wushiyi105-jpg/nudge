from __future__ import annotations

from datetime import date, timedelta

import pytest

from nudge.domain.models import Client, Invoice
from nudge.domain.rules import dunning

TODAY = date(2026, 11, 27)


@pytest.mark.parametrize(
    "overdue,stage",
    [(0, 0), (-3, 0), (1, 1), (14, 1), (15, 2), (29, 2), (30, 3), (200, 3)],
)
def test_stage_thresholds(overdue, stage):
    assert dunning.stage_for(overdue, None, stage2=15, stage3=30) == stage


def test_chronic_client_is_pushed_one_stage_up():
    # 逾期 1 天本该是 1 档，但客户历史平均拖 21 天 → 升到 2 档
    assert dunning.stage_for(1, 21.0, stage2=15, stage3=30) == 2


def test_chronic_bump_never_exceeds_final_stage():
    assert dunning.stage_for(30, 40.0, stage2=15, stage3=30) == 3


def test_good_client_is_not_pushed_up():
    assert dunning.stage_for(5, 2.0, stage2=15, stage3=30) == 1


def test_tone_mapping():
    assert dunning.tone_for(1) == "gentle"
    assert dunning.tone_for(2) == "firm"
    assert dunning.tone_for(3) == "final"


def test_chronic_finding_mentions_history():
    client = Client(id=1, name="青禾设计", avg_delay_days=21.0)
    invoice = Invoice(
        id=1, client_id=1, number="INV-1", amount_cents=100_000,
        issued_on=TODAY - timedelta(days=40), due_on=TODAY - timedelta(days=5),
    )
    found = dunning.findings(client, invoice, 5, stage2=15, stage3=30)
    assert any(f.rule_id == "dunning.chronic" for f in found)


def test_final_finding_only_at_stage_three():
    client = Client(id=1, name="北岸书店", avg_delay_days=3.0)
    invoice = Invoice(
        id=1, client_id=1, number="INV-1", amount_cents=100_000,
        issued_on=TODAY - timedelta(days=40), due_on=TODAY - timedelta(days=40),
    )
    found = dunning.findings(client, invoice, 40, stage2=15, stage3=30)
    assert any(f.rule_id == "dunning.final" for f in found)
