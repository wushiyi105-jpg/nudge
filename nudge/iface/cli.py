"""CLI：Typer + rich。退出码 0 成功 / 1 运行错误 / 2 参数错误。"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from ..adapters.llm.openai_compat import OpenAICompatClient
from ..adapters.notify.webhook import WebhookNotifier
from ..adapters.store.sqlite import SqliteStore
from ..app.jobs import process_jobs
from ..app.scan import scan
from ..config import settings as base_settings
from ..doctor import run_doctor

app = typer.Typer(add_completion=False, help="Nudge —— 应收与催款台账")
console = Console()


def _store(db: Path | None) -> SqliteStore:
    s = base_settings.model_copy(update={"db_path": db}) if db else base_settings
    return SqliteStore(s.db_path)


def _settings(db: Path | None):
    return base_settings.model_copy(update={"db_path": db}) if db else base_settings


@app.command()
def seed(db: Path = typer.Option(None, help="数据库路径")) -> None:
    """写入示例数据（已存在则跳过）。"""
    store = _store(db)
    path = Path(__file__).resolve().parents[2] / "data" / "seed.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    ids = {c["name"]: store.add_client(c["name"], c.get("contact", ""), c.get("avg_delay_days")) for c in data["clients"]}
    for inv in data["invoices"]:
        store.add_invoice(
            ids[inv["client"]],
            inv["number"],
            inv["amount"],
            date.fromisoformat(inv["issued"]),
            date.fromisoformat(inv["due"]),
        )
    console.print(f"[green]已写入[/] {len(ids)} 个客户、{len(data['invoices'])} 张发票")


@app.command("scan")
def scan_cmd(
    db: Path = typer.Option(None, help="数据库路径"),
    as_json: bool = typer.Option(False, "--json", help="机器可读输出"),
    offline: bool = typer.Option(False, "--offline", help="不调用模型"),
) -> None:
    """扫描逾期，生成催收建议并排队。"""
    s = _settings(db)
    store = SqliteStore(s.db_path)
    llm = None if (offline or not s.llm_enabled) else OpenAICompatClient(
        s.llm_base_url, s.llm_api_key, s.llm_model, s.llm_timeout
    )
    result = scan(store, llm, s)

    if as_json:
        console.print_json(
            json.dumps(
                {
                    "run_id": result.run_id,
                    "skipped": result.skipped,
                    "items": [
                        {
                            "invoice": i.invoice.number,
                            "client": i.client.name,
                            "stage": i.rec.stage,
                            "days_overdue": i.rec.days_overdue,
                            "outstanding": i.rec.outstanding_cents / 100,
                            "score": i.rec.score,
                            "source": i.source,
                            "message": i.message,
                            "enqueued": i.enqueued,
                            "findings": [
                                {"rule": f.rule_id, "score": f.score, "message": f.message}
                                for f in i.rec.findings
                            ],
                        }
                        for i in result.items
                    ],
                },
                ensure_ascii=False,
            )
        )
        return

    if not result.items:
        console.print("[yellow]没有逾期应收[/]")
        return

    table = Table(title=f"待催 {len(result.items)} 笔 · 合计 {result.total_outstanding / 100:.2f} 元")
    table.add_column("发票")
    table.add_column("客户")
    table.add_column("逾期", justify="right")
    table.add_column("未收", justify="right")
    table.add_column("档位", justify="center")
    table.add_column("评分", justify="right")
    for item in result.items:
        table.add_row(
            item.invoice.number,
            item.client.name,
            f"{item.rec.days_overdue} 天",
            f"{item.rec.outstanding_cents / 100:.2f}",
            str(item.rec.stage),
            str(item.rec.score),
        )
    console.print(table)

    for item in result.items:
        console.print(f"\n[bold]{item.invoice.number}[/] → {item.message}")
        for f in item.rec.top_findings:
            console.print(f"  · [dim]{f.rule_id}[/] {f.message} ({f.score})")


@app.command()
def jobs(
    db: Path = typer.Option(None, help="数据库路径"),
    dry_run: bool = typer.Option(False, "--dry-run", help="只查看队列"),
) -> None:
    """发送队列里的催收消息。"""
    s = _settings(db)
    store = SqliteStore(s.db_path)
    pending = store.due_jobs()
    if dry_run:
        console.print(f"[yellow]{len(pending)} 条待发[/]")
        return
    ok, failed = process_jobs(store, WebhookNotifier(s.webhook_url))
    console.print(f"发送成功 {ok}，失败 {failed}")


@app.command()
def pay(
    invoice_id: int,
    amount: float = typer.Option(..., help="本次回款金额（元）"),
    db: Path = typer.Option(None, help="数据库路径"),
) -> None:
    """登记一笔回款。"""
    store = _store(db)
    store.record_payment(invoice_id, int(round(amount * 100)), date.today())
    console.print(f"[green]已登记[/] {amount:.2f} 元 → 发票 {invoice_id}")


@app.command()
def report(db: Path = typer.Option(None, help="数据库路径")) -> None:
    """账龄汇总。"""
    store = _store(db)
    today = date.today()
    buckets = {"current": 0, "1-30": 0, "31-60": 0, "61-90": 0, "90+": 0}
    for inv in store.list_open_invoices():
        od = (today - inv.due_on).days
        key = "current" if od <= 0 else "1-30" if od <= 30 else "31-60" if od <= 60 else "61-90" if od <= 90 else "90+"
        buckets[key] += inv.outstanding_cents
    table = Table(title="账龄分布")
    table.add_column("桶")
    table.add_column("金额", justify="right")
    for k, v in buckets.items():
        table.add_row(k, f"{v / 100:.2f}")
    console.print(table)


@app.command()
def serve(
    port: int = typer.Option(8000, help="端口"),
    db: Path = typer.Option(None, help="数据库路径"),
) -> None:
    """启动 Web 界面。"""
    import uvicorn

    from .web import create_app

    uvicorn.run(create_app(_settings(db)), host="127.0.0.1", port=port)


@app.command()
def doctor(db: Path = typer.Option(None, help="数据库路径")) -> None:
    """自检：配置、数据库、模型、webhook。"""
    s = _settings(db)
    results = run_doctor(s)
    bad = 0
    for name, ok, detail in results:
        mark = "[green]ok[/]" if ok else "[red]fail[/]"
        console.print(f"{mark}  {name:12} {detail}")
        bad += 0 if ok else 1
    raise typer.Exit(code=1 if bad else 0)


if __name__ == "__main__":  # pragma: no cover
    app()
