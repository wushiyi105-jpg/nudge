"""引擎：把规则跑成一份可解释的催收建议。纯函数，不碰 IO。"""

from __future__ import annotations

from datetime import date

from .guard import guard
from .models import Client, Finding, Invoice, Recommendation
from .rules import aging, dunning


def _allowed_numbers(rec: Recommendation, invoice: Invoice) -> set[str]:
    """台账里真实存在的数字，模型只能引用这些。"""
    return {
        str(rec.days_overdue),
        f"{rec.outstanding_cents / 100:.2f}",
        f"{rec.outstanding_cents / 100:.0f}",
        f"{invoice.amount_cents / 100:.2f}",
        invoice.due_on.strftime("%d"),
        invoice.due_on.strftime("%Y"),
    }


def evaluate(client: Client, invoice: Invoice, today: date, *, stage2: int = 15, stage3: int = 30) -> Recommendation:
    od = aging.days_overdue(invoice, today)
    stage = dunning.stage_for(od, client.avg_delay_days, stage2=stage2, stage3=stage3)
    rec = Recommendation(
        invoice_id=invoice.id,
        client_id=client.id,
        days_overdue=od,
        outstanding_cents=invoice.outstanding_cents,
        stage=stage,
        tone=dunning.tone_for(stage),
    )
    findings: list[Finding] = []
    findings += aging.findings(invoice, today)
    findings += dunning.findings(client, invoice, od, stage2=stage2, stage3=stage3)
    rec.findings = findings
    return rec


def apply_guard(rec: Recommendation, invoice: Invoice, text: str) -> tuple[str, list[str]]:
    return guard(text, _allowed_numbers(rec, invoice))
