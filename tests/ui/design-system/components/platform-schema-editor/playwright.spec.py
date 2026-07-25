"""pytest placeholder — backlog component; enable when status=production."""

import pytest


@pytest.mark.skip(reason="platform-schema-editor: backlog — Playwright L2 pending")
def test_backlog_placeholder() -> None:
    raise AssertionError("backlog")
