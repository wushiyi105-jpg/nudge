"""任务处理：把队列里的催收消息发出去，失败重试。"""

from __future__ import annotations

import json

from ..ports import Notifier, Store


def process_jobs(store: Store, notifier: Notifier, limit: int = 20) -> tuple[int, int]:
    ok = failed = 0
    for job in store.due_jobs(limit=limit):
        payload = json.loads(job.payload or "{}")
        try:
            sent = notifier.send(
                f"催收 · {payload.get('client', '')} · 第 {payload.get('stage', 1)} 档",
                payload.get("message", ""),
            )
        except Exception as exc:  # noqa: BLE001
            sent = False
            store.finish_job(job.id, False, str(exc))
        else:
            store.finish_job(job.id, sent, "" if sent else "notifier returned False")
        if sent:
            ok += 1
        else:
            failed += 1
    return ok, failed
