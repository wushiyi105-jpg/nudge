from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest

from nudge.domain.models import Invoice
from nudge.domain.rules import aging

TODAY = date(2026, 11, 27)


def make_invoice(**kw) -> Invoice:
    base: dict[str, Any] = dict(
        id=1,
        client_id=1,
        number="INV-1",
        amount_cents=100_000,
        issued_on=TODAY - timedelta(days=60),
        due_on=TODAY - timedelta(days=10),
    )
    base.update(kw)
    return Invoice(**base)


@pytest.mark.parametrize(
    "overdue,expect",
    [(0, "current"), (-5, "current"), (1, "1-30"), (30, "1-30"), (31, "31-60"),
     (60, "31-60"), (61, "61-90"), (90, "61-90"), (91, "90+")],
)
def test_bucket_boundaries(overdue, expect):
    assert aging.bucket(overdue) == expect


def test_days_overdue_counts_calendar_days():
    inv = make_invoice(due_on=date(2026, 11, 20))
    assert aging.days_overdue(inv, TODAY) == 7


def test_fully_paid_invoice_has_no_findings():
    inv = make_invoice(paid_cents=100_000)
    assert aging.findings(inv, TODAY) == []


def test_overdue_produces_negative_score():
    inv = make_invoice(due_on=TODAY - timedelta(days=5))
    found = aging.findings(inv, TODAY)
    assert [f.rule_id for f in found] == ["aging.overdue"]
    assert found[0].score < 0


def test_over_ninety_days_adds_heavy_rule():
    inv = make_invoice(due_on=TODAY - timedelta(days=120))
    ids = {f.rule_id for f in aging.findings(inv, TODAY)}
    assert {"aging.overdue", "aging.heavy"} <= ids


def test_partial_payment_is_flagged():
    inv = make_invoice(paid_cents=30_000)
    ids = {f.rule_id for f in aging.findings(inv, TODAY)}
    assert "aging.partial" in ids


def test_outstanding_never_negative():
    inv = make_invoice(paid_cents=200_000)
    assert inv.outstanding_cents == 0
