"""用例：扫描应收，出建议，把催收消息排进队列。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from ..config import Settings
from ..domain import engine
from ..domain.models import Client, Invoice, Recommendation
from ..ports import LLMClient, Store

PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"


@dataclass
class ScanItem:
    invoice: Invoice
    client: Client
    rec: Recommendation
    message: str
    source: str  # llm / offline
    enqueued: bool
    dropped_numbers: list[str] = field(default_factory=list)


@dataclass
class ScanResult:
    run_id: int
    items: list[ScanItem]
    skipped: int = 0

    @property
    def total_outstanding(self) -> int:
        return sum(i.rec.outstanding_cents for i in self.items)


def _offline_message(client: Client, invoice: Invoice, rec: Recommendation) -> str:
    amount = rec.outstanding_cents / 100
    templates = {
        1: f"{client.name} 您好，{invoice.number} 这笔 {amount:.2f} 元已经到期 {rec.days_overdue} 天了，方便的时候安排一下？",
        2: f"{client.name} 您好，{invoice.number} 的 {amount:.2f} 元已逾期 {rec.days_overdue} 天，麻烦本周内确认一下付款时间。",
        3: f"{client.name} 您好，{invoice.number} 的 {amount:.2f} 元已逾期 {rec.days_overdue} 天。若本周内仍未收到，我们需要暂停后续排期，请理解。",
    }
    return templates.get(rec.stage, templates[1])


def _llm_message(llm: LLMClient, client: Client, invoice: Invoice, rec: Recommendation) -> str:
    system = (PROMPT_DIR / "dunning.md").read_text(encoding="utf-8")
    facts = {
        "客户": client.name,
        "发票号": invoice.number,
        "到期日": invoice.due_on.isoformat(),
        "逾期天数": rec.days_overdue,
        "未收金额": f"{rec.outstanding_cents / 100:.2f}",
        "档位": rec.stage,
        "语气": rec.tone,
    }
    prompt = "台账事实（只能引用这些数字）：\n" + json.dumps(facts, ensure_ascii=False, indent=2)
    return llm.complete(system, prompt)


def scan(store: Store, llm: LLMClient | None, settings: Settings, today: date | None = None) -> ScanResult:
    today = today or date.today()
    run_id = store.start_run()
    items: list[ScanItem] = []
    skipped = 0

    for invoice in store.list_open_invoices():
        client = store.client(invoice.client_id)
        if client is None:
            continue
        rec = engine.evaluate(
            client,
            invoice,
            today,
            stage2=settings.stage2_days,
            stage3=settings.stage3_days,
        )
        if rec.stage == 0:
            skipped += 1
            continue

        source = "offline"
        message = _offline_message(client, invoice, rec)
        dropped: list[str] = []
        if llm is not None:
            try:
                raw = _llm_message(llm, client, invoice, rec)
                safe, dropped = engine.apply_guard(rec, invoice, raw)
                if safe:
                    message, source = safe, "llm"
            except Exception:
                pass  # 模型失败不阻塞，降级离线文案

        key = f"reminder:{invoice.id}:{rec.stage}:{today.isoformat()}"
        enqueued = store.enqueue(
            "reminder",
            {"invoice_id": invoice.id, "client": client.name, "message": message, "stage": rec.stage},
            key,
        )
        items.append(
            ScanItem(
                invoice=invoice,
                client=client,
                rec=rec,
                message=message,
                source=source,
                enqueued=enqueued,
                dropped_numbers=dropped,
            )
        )

    items.sort(key=lambda i: i.rec.score)
    store.finish_run(run_id, f"{len(items)} 条待催，{skipped} 条未到期，合计 {sum(i.rec.outstanding_cents for i in items) / 100:.2f} 元")
    return ScanResult(run_id=run_id, items=items, skipped=skipped)
