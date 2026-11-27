"""30 客户台账上的催款话术与回款口径。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .models import Client, Invoice, Recommendation

ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def templates() -> list[dict[str, Any]]:
    return json.loads((ROOT / "data" / "templates.json").read_text(encoding="utf-8"))["templates"]


def _fill(text: str, client: Client, invoice: Invoice, rec: Recommendation) -> str:
    return text.format(
        client=client.name,
        invoice=invoice.number,
        amount=f"{rec.outstanding_cents / 100:,.2f}",
        days=rec.days_overdue,
        due=invoice.due_on.isoformat(),
    )


def three_messages(client: Client, invoice: Invoice, rec: Recommendation) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for stage in (1, 2, 3):
        row = next(t for t in templates() if t["stage"] == stage)
        out.append({"tone": row["tone"], "text": _fill(row["text"], client, invoice, rec)})
    return out


def collection_metrics(invoices: list[Invoice], clients: list[Client]) -> dict[str, float]:
    billed = sum(i.amount_cents for i in invoices)
    paid = sum(i.paid_cents for i in invoices)
    delays = [c.avg_delay_days for c in clients if c.avg_delay_days is not None]
    return {
        "billed": billed / 100,
        "paid": paid / 100,
        "rate": paid / billed if billed else 0.0,
        "avg_delay": sum(delays) / len(delays) if delays else 0.0,
    }


def aging(invoices: list[Invoice], today) -> dict[str, float]:
    buckets = {"未到期": 0.0, "1-30 天": 0.0, "31-60 天": 0.0, "61-90 天": 0.0, "90 天以上": 0.0}
    for inv in invoices:
        od = (today - inv.due_on).days
        if od <= 0:
            key = "未到期"
        elif od <= 30:
            key = "1-30 天"
        elif od <= 60:
            key = "31-60 天"
        elif od <= 90:
            key = "61-90 天"
        else:
            key = "90 天以上"
        buckets[key] += inv.outstanding_cents / 100
    return buckets
