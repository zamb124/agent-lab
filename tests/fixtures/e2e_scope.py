"""
Статический test scope для E2E-фаз без браузерного X-Test-Scope
(Electron desktop / agent e2e на ``-n0``).

UI E2E (`tests/ui/e2e`) использует per-worker scope через
``tests/ui/e2e_worker.bind_ui_e2e_worker_scope`` + Playwright
``extra_http_headers`` с ``X-Test-Scope``.

Desktop/agent conftest'ы переопределяют ``platform_test_scope``:

    @pytest.fixture(autouse=True)
    def platform_test_scope():
        with bind_static_e2e_scope() as scope:
            yield scope
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from core.logging import bind_log_context, unbind_log_context
from core.test_scope import LOG_TEST_SCOPE, TEST_SCOPE_STATIC_E2E


@contextmanager
def bind_static_e2e_scope() -> Iterator[str]:
    bind_log_context(**{LOG_TEST_SCOPE: TEST_SCOPE_STATIC_E2E})
    try:
        yield TEST_SCOPE_STATIC_E2E
    finally:
        unbind_log_context(LOG_TEST_SCOPE)
