"""
Статический test scope для E2E-фаз (-n0: Playwright browser, Electron desktop).

Запросы из браузера/desktop-приложения не несут ``X-Test-Scope`` — сервисы
стека берут scope из env ``TEST_SCOPE_DEFAULT`` (см. `scripts/test_stack.py`).
Тестовый процесс этих фаз биндит тот же статический scope, чтобы очереди
MockLLM (`mock_llm:responses:<scope>`) совпадали с service-side резолвом.

conftest E2E-фазы переопределяет фикстуру ``platform_test_scope``:

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
