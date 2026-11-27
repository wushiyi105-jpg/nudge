"""SQLite 仓储：实现 ports.Store。"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from ...domain.models import Client, Invoice
from .models import ClientRow, InvoiceRow, JobRow, PaymentRow, RunRow


def _upgrade_schema(engine) -> None:
    root = next(p for p in Path(__file__).resolve().parents if (p / "alembic.ini").exists())
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{engine.url.database}")
    command.upgrade(cfg, "head")


class SqliteStore:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{db_path}", future=True)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)
        _upgrade_schema(self.engine)

    # ---------- 查询 ----------
    def list_clients(self) -> list[Client]:
        with self.session_factory() as s:
            rows = s.scalars(select(ClientRow)).all()
            return [
                Client(
                    id=r.id,
                    name=r.name,
                    contact=r.contact,
                    avg_delay_days=r.avg_delay_days,
                    tone=r.tone,
                )
                for r in rows
            ]

    def client(self, client_id: int) -> Client | None:
        with self.session_factory() as s:
            r = s.get(ClientRow, client_id)
            if not r:
                return None
            return Client(r.id, r.name, r.contact, r.avg_delay_days, r.tone)

    def list_open_invoices(self) -> list[Invoice]:
        with self.session_factory() as s:
            rows = s.scalars(select(InvoiceRow).where(InvoiceRow.paid_cents < InvoiceRow.amount_cents)).all()
            return [
                Invoice(
                    id=r.id,
                    client_id=r.client_id,
                    number=r.number,
                    amount_cents=r.amount_cents,
                    issued_on=r.issued_on,
                    due_on=r.due_on,
                    paid_cents=r.paid_cents,
                )
                for r in rows
            ]

    def invoice(self, invoice_id: int) -> Invoice | None:
        with self.session_factory() as s:
            r = s.get(InvoiceRow, invoice_id)
            if not r:
                return None
            return Invoice(r.id, r.client_id, r.number, r.amount_cents, r.issued_on, r.due_on, r.paid_cents)

    # ---------- 写入 ----------
    def add_client(self, name: str, contact: str = "", avg_delay_days: float | None = None) -> int:
        with self.session_factory() as s:
            row = ClientRow(name=name, contact=contact, avg_delay_days=avg_delay_days)
            s.add(row)
            s.commit()
            return row.id

    def add_invoice(self, client_id: int, number: str, amount_cents: int, issued_on: date, due_on: date) -> int:
        with self.session_factory() as s:
            row = InvoiceRow(
                client_id=client_id,
                number=number,
                amount_cents=amount_cents,
                issued_on=issued_on,
                due_on=due_on,
            )
            s.add(row)
            s.commit()
            return row.id

    def record_payment(self, invoice_id: int, amount_cents: int, paid_on: date) -> None:
        with self.session_factory() as s:
            inv = s.get(InvoiceRow, invoice_id)
            if not inv:
                raise ValueError(f"invoice {invoice_id} not found")
            inv.paid_cents = min(inv.paid_cents + amount_cents, inv.amount_cents)
            s.add(PaymentRow(invoice_id=invoice_id, amount_cents=amount_cents, paid_on=paid_on))
            s.commit()

    # ---------- 任务 ----------
    def enqueue(self, kind: str, payload: dict, idempotency_key: str) -> bool:
        with self.session_factory() as s:
            exists = s.scalar(select(JobRow).where(JobRow.idempotency_key == idempotency_key))
            if exists:
                return False
            s.add(JobRow(kind=kind, payload=json.dumps(payload, ensure_ascii=False), idempotency_key=idempotency_key))
            s.commit()
            return True

    def due_jobs(self, limit: int = 20) -> list[JobRow]:
        with self.session_factory() as s:
            now = datetime.now()
            return list(
                s.scalars(
                    select(JobRow)
                    .where(JobRow.state == "pending", JobRow.next_run_at <= now)
                    .order_by(JobRow.next_run_at)
                    .limit(limit)
                ).all()
            )

    def finish_job(self, job_id: int, ok: bool, error: str = "") -> None:
        with self.session_factory() as s:
            job = s.get(JobRow, job_id)
            if not job:
                return
            job.attempts += 1
            if ok:
                job.state = "done"
            elif job.attempts >= 3:
                job.state = "failed"
                job.last_error = error[:400]
            else:
                job.next_run_at = datetime.now() + timedelta(minutes=5 * job.attempts)
                job.last_error = error[:400]
            s.commit()

    def start_run(self) -> int:
        with self.session_factory() as s:
            row = RunRow()
            s.add(row)
            s.commit()
            return row.id

    def finish_run(self, run_id: int, summary: str) -> None:
        with self.session_factory() as s:
            row = s.get(RunRow, run_id)
            if row:
                row.finished_at = datetime.now()
                row.summary = summary[:400]
                s.commit()

    def count(self, table: str) -> int:
        mapping = {"clients": ClientRow, "invoices": InvoiceRow, "jobs": JobRow, "runs": RunRow}
        model = mapping[table]
        with self.session_factory() as s:
            return len(s.scalars(select(model)).all())


def session_scope(store: SqliteStore) -> Session:  # pragma: no cover - 便捷函数
    return store.session_factory()
