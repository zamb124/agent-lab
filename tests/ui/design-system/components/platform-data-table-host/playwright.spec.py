"""pytest placeholder — backfill component; enable when status=production."""

import pytest


@pytest.mark.skip(reason="platform-data-table-host: backfill — Playwright L2 pending")
def test_backlog_placeholder() -> None:
    raise AssertionError("backlog")
