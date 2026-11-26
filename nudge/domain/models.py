"""领域模型：只用标准库 dataclass，不依赖任何 IO。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Client:
    id: int
    name: str
    contact: str = ""
    # 历史平均拖延天数，没有历史时为 None
    avg_delay_days: float | None = None
    # gentle / firm / final 的默认语气
    tone: str = "gentle"


@dataclass(frozen=True)
class Invoice:
    id: int
    client_id: int
    number: str
    amount_cents: int
    issued_on: date
    due_on: date
    paid_cents: int = 0

    @property
    def outstanding_cents(self) -> int:
        return max(self.amount_cents - self.paid_cents, 0)


@dataclass(frozen=True)
class Promise:
    id: int
    invoice_id: int
    promised_on: date
    kept: bool = False


@dataclass(frozen=True)
class Finding:
    """一条可解释的规则命中。score 为负表示扣分（风险）。"""

    rule_id: str
    severity: str  # info / warn / high
    message: str
    evidence: str
    suggestion: str = ""
    score: int = 0


@dataclass
class Recommendation:
    invoice_id: int
    client_id: int
    days_overdue: int
    outstanding_cents: int
    stage: int
    tone: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def score(self) -> int:
        return sum(f.score for f in self.findings)

    @property
    def top_findings(self) -> list[Finding]:
        return sorted(self.findings, key=lambda f: f.score)[:3]
