"""催收档位：按逾期天数 + 客户历史拖延决定力度。纯函数。"""

from __future__ import annotations

from ..models import Client, Finding, Invoice


def stage_for(days_overdue: int, avg_delay_days: float | None, *, stage2: int, stage3: int) -> int:
    """0 = 不催，1 = 温和，2 = 明确，3 = 最后通牒。

    历史拖延久的客户，档位提前一档——同一个客户被拖成习惯，
    再用第一次的语气就不管用了。
    """
    if days_overdue <= 0:
        return 0
    stage = 1
    if days_overdue >= stage2:
        stage = 2
    if days_overdue >= stage3:
        stage = 3
    if avg_delay_days is not None and avg_delay_days >= 14 and days_overdue > 0:
        stage = min(stage + 1, 3)
    return stage


def tone_for(stage: int) -> str:
    return {1: "gentle", 2: "firm", 3: "final"}.get(stage, "gentle")


def findings(
    client: Client,
    invoice: Invoice,
    days_overdue: int,
    *,
    stage2: int,
    stage3: int,
) -> list[Finding]:
    out: list[Finding] = []
    stage = stage_for(days_overdue, client.avg_delay_days, stage2=stage2, stage3=stage3)
    if stage == 0:
        return out

    if client.avg_delay_days is not None and client.avg_delay_days >= 14:
        out.append(
            Finding(
                rule_id="dunning.chronic",
                severity="warn",
                message=f"该客户历史平均拖 {client.avg_delay_days:.0f} 天",
                evidence=f"客户 {client.name} 的历史回款记录",
                suggestion="档位已上调一档，并考虑预付款条款",
                score=-6,
            )
        )

    if stage == 3:
        out.append(
            Finding(
                rule_id="dunning.final",
                severity="high",
                message="进入最后通牒档",
                evidence=f"逾期 {days_overdue} 天 ≥ {stage3} 天",
                suggestion="明确截止日与后果，抄送对接人",
                score=-10,
            )
        )

    return out
