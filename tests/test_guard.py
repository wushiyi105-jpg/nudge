from __future__ import annotations

from nudge.domain.guard import extract_numbers, guard, untrusted_numbers

ALLOWED = {"1250.00", "1250", "23", "2026"}


def test_extract_handles_thousand_separator():
    assert extract_numbers("欠 1,250.00 元") == ["1250.00"]


def test_allowed_numbers_pass():
    text = "INV-1 的 1250.00 元已逾期 23 天。"
    safe, dropped = guard(text, ALLOWED)
    assert safe == text
    assert dropped == []


def test_invented_amount_drops_whole_sentence():
    text = "欠 1250.00 元。请支付违约金 300 元。"
    safe, dropped = guard(text, ALLOWED)
    assert "300" in dropped
    assert "违约金" not in safe
    assert "1250.00" in safe


def test_untrusted_numbers_lists_only_bad_ones():
    assert untrusted_numbers("1250.00 与 999", ALLOWED) == ["999"]


def test_empty_output_stays_empty():
    safe, dropped = guard("", ALLOWED)
    assert safe == "" and dropped == []
