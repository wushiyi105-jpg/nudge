"""数字守卫：模型写的话里出现台账之外的数字，就丢掉那一句。

这是本仓最关键的一条约束——催款消息里的金额、天数、日期错一个，
就不是"语气不对"的问题，是把关系谈崩的问题。
"""

from __future__ import annotations

import re

NUMBER_RE = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
# 允许的通用数字（不是业务数据）：序号、比例分母等
IGNORE = {"0", "1", "2", "3", "5", "7", "10"}


def _normalize(token: str) -> str:
    return token.replace(",", "")


def extract_numbers(text: str) -> list[str]:
    return [_normalize(m) for m in NUMBER_RE.findall(text)]


def untrusted_numbers(text: str, allowed: set[str]) -> list[str]:
    allowed_norm = {_normalize(a) for a in allowed}
    bad = []
    for token in extract_numbers(text):
        if token in allowed_norm or token in IGNORE:
            continue
        bad.append(token)
    return bad


def guard(text: str, allowed: set[str]) -> tuple[str, list[str]]:
    """返回（过滤后的文本，被丢弃的数字列表）。

    以句为单位检查：某句里出现未授权数字，整句丢弃，
    宁可少说一句，也不能说错一个数。
    """
    dropped: list[str] = []
    kept: list[str] = []
    for sentence in re.split(r"(?<=[。！？!?\n])", text):
        if not sentence.strip():
            continue
        bad = untrusted_numbers(sentence, allowed)
        if bad:
            dropped.extend(bad)
            continue
        kept.append(sentence)
    return "".join(kept).strip(), dropped
