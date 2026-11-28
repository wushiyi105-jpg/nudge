"""FastAPI + Jinja2 服务端渲染。"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..adapters.llm.openai_compat import OpenAICompatClient
from ..adapters.store.sqlite import SqliteStore
from ..app.scan import scan
from ..config import Settings

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parents[2] / "templates"))


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="Nudge", version="1.0.0")
    app.mount(
        "/static",
        StaticFiles(directory=str(Path(__file__).resolve().parents[2] / "static")),
        name="static",
    )
    store = SqliteStore(settings.db_path)

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, scanned: str = "") -> HTMLResponse:
        today = date.today()
        rows: list[dict[str, Any]] = []
        for inv in store.list_open_invoices():
            client = store.client(inv.client_id)
            od = (today - inv.due_on).days
            rows.append(
                {
                    "id": inv.id,
                    "number": inv.number,
                    "client": client.name if client else "-",
                    "due": inv.due_on.isoformat(),
                    "overdue": od,
                    "outstanding": inv.outstanding_cents / 100,
                    "bucket": "current" if od <= 0 else "1-30" if od <= 30 else "31-60" if od <= 60 else "61-90" if od <= 90 else "90+",
                }
            )
        rows.sort(key=lambda r: int(r["overdue"]), reverse=True)
        total = sum(float(r["outstanding"]) for r in rows)
        return TEMPLATES.TemplateResponse(
            request, "index.html", {"rows": rows, "total": total, "scanned": scanned}
        )

    @app.post("/scan")
    def do_scan(offline: str = Form("")) -> RedirectResponse:
        llm = None
        if not offline and settings.llm_enabled:
            llm = OpenAICompatClient(settings.llm_base_url, settings.llm_api_key, settings.llm_model, settings.llm_timeout)
        result = scan(store, llm, settings)
        return RedirectResponse(url=f"/?scanned={len(result.items)}", status_code=303)

    @app.post("/pay/{invoice_id}")
    def do_pay(invoice_id: int, amount: float = Form(...)) -> RedirectResponse:
        store.record_payment(invoice_id, int(round(amount * 100)), date.today())
        return RedirectResponse(url="/", status_code=303)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def app_factory() -> FastAPI:
    """uvicorn 工厂入口：uvicorn nudge.iface.web:app_factory --factory"""
    from ..config import settings

    return create_app(settings)

