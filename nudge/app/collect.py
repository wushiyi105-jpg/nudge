"""今日催款清单：优先级、回款口径、每个客户三条可复制消息。"""

from __future__ import annotations

from datetime import date

from ..domain.catalog import aging, collection_metrics, three_messages
from ..ports import Store
from .scan import ScanResult


def build_report(store: Store, result: ScanResult, clients, today: date) -> str:
    invoices = getattr(store, "list_invoices", store.list_open_invoices)()
    m = collection_metrics(invoices, clients)
    total = result.total_outstanding / 100
    lines = [
        f"# 今日催款清单 · {today.isoformat()}",
        "",
        f"> 待催 **{len(result.items)} 笔**，未收 **{total:,.2f} 元**；"
        f"台账回款率 **{m['rate']:.0%}**，客户历史平均拖延 **{m['avg_delay']:.1f} 天**。"
        " 文案按温和/明确/最后三档生成，复制即发。",
        "",
        "## 一、今天先催这 5 个",
        "",
        "| 优先级 | 客户 | 发票 | 逾期 | 未收 | 档位 |",
        "| ---: | --- | --- | ---: | ---: | --- |",
    ]
    ranked = sorted(result.items, key=lambda i: (-i.rec.days_overdue, -i.rec.outstanding_cents))
    for index, item in enumerate(ranked[:5], 1):
        lines.append(
            f"| {index} | {item.client.name} | {item.invoice.number} | {item.rec.days_overdue} 天 | "
            f"{item.rec.outstanding_cents / 100:,.2f} | {item.rec.stage} 档 |"
        )
    lines += ["", "## 二、每个客户三条消息（直接复制）", ""]
    for item in ranked:
        lines += [
            f"### {item.client.name} · {item.invoice.number} · {item.rec.outstanding_cents / 100:,.2f} 元",
            "",
            f"逾期 {item.rec.days_overdue} 天；联系人：{item.client.contact or '未填'}；"
            f"系统判定 {item.rec.stage} 档（{item.rec.tone}）。",
            "",
        ]
        for msg in three_messages(item.client, item.invoice, item.rec):
            lines += [f"**{msg['tone']}版**", "", "```text", msg["text"], "```", ""]
    lines += ["## 三、账龄分布", "", "| 账龄 | 未收金额 |", "| --- | ---: |"]
    for key, value in aging(invoices, today).items():
        lines.append(f"| {key} | {value:,.2f} |")
    lines += [
        "",
        "## 四、口径",
        "",
        "- 回款率 = 已收 / 全部台账金额；平均拖延取有历史记录客户的平均值。",
        "- 档位由逾期天数与客户历史拖延共同决定；历史拖得久的客户自动升一档。",
        "- 模型不参与默认报告；加 `--llm` 才会让模型改写，数字仍由本地守卫校验。",
        "",
    ]
    return "\n".join(lines)
