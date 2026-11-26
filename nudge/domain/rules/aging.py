"""账龄规则：分桶、逾期判定、部分回款。纯函数。"""

from __future__ import annotations

from datetime import date

from ..models import Finding, Invoice

BUCKETS = ("current", "1-30", "31-60", "61-90", "90+")


def days_overdue(invoice: Invoice, today: date) -> int:
    """已逾期天数；未到期返回负数。"""
    return (today - invoice.due_on).days


def bucket(overdue_days: int) -> str:
    if overdue_days <= 0:
        return "current"
    if overdue_days <= 30:
        return "1-30"
    if overdue_days <= 60:
        return "31-60"
    if overdue_days <= 90:
        return "61-90"
    return "90+"


def findings(invoice: Invoice, today: date) -> list[Finding]:
    out: list[Finding] = []
    od = days_overdue(invoice, today)

    if invoice.outstanding_cents <= 0:
        return out

    if od > 0:
        out.append(
            Finding(
                rule_id="aging.overdue",
                severity="warn" if od <= 30 else "high",
                message=f"已逾期 {od} 天",
                evidence=f"到期日 {invoice.due_on.isoformat()}，今日 {today.isoformat()}",
                suggestion="进入催收队列",
                score=-min(od, 30),
            )
        )

    if od > 90:
        out.append(
            Finding(
                rule_id="aging.heavy",
                severity="high",
                message=f"逾期超过 90 天（{bucket(od)} 桶）",
                evidence=f"欠款 {invoice.outstanding_cents / 100:.2f} 元",
                suggestion="建议转法务或计提坏账",
                score=-20,
            )
        )

    if 0 < invoice.paid_cents < invoice.amount_cents:
        ratio = invoice.paid_cents / invoice.amount_cents
        out.append(
            Finding(
                rule_id="aging.partial",
                severity="info",
                message=f"部分回款（已收 {ratio:.0%}）",
                evidence=f"应收 {invoice.amount_cents / 100:.2f}，已收 {invoice.paid_cents / 100:.2f}",
                suggestion="按余额催收，不要重复要全额",
                score=-2,
            )
        )

    return out
