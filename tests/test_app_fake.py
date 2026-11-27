"""主用例只依赖 ports：用 MagicMock 内存假实现，不建 SQLite 文件。"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from nudge.app.scan import scan
from nudge.config import Settings
from nudge.ports import Store


def test_main_path_with_memory_store(tmp_path) -> None:
    store = MagicMock(spec=Store)
    store.start_run.return_value = 1
    out = scan(store, None, Settings(), today=date(2026, 1, 5))
    assert out is not None
    assert not (tmp_path / "app.db").exists()
