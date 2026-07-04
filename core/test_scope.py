"""
Test scope — сквозная метка теста для маршрутизации MockLLM (только TESTING).

Каждый тест получает уникальный scope (`test_<hex>`), который едет по тем же
рельсам, что `request_id`/`trace_id`:

- HTTP: заголовок ``X-Test-Scope`` → лог-контекст (AccessLogMiddleware);
- исходящие HTTP: ServiceClient / A2AClient добавляют заголовок из лог-контекста;
- TaskIQ: label ``test_scope`` (kicker → LoggingMiddleware воркера);
- WebSocket: заголовок соединения → лог-контекст команд.

MockLLM читает scope из лог-контекста и работает строго со своей очередью
``mock_llm:responses:<scope>`` — никакого скана чужих ключей.

E2E-фазы (-n0: Playwright browser, Electron desktop) не могут поставить
заголовок на запросы из браузера/приложения — сервисы стека берут статический
scope из env ``TEST_SCOPE_DEFAULT`` (``TEST_SCOPE_STATIC_E2E``), а conftest'ы
этих фаз биндят тот же scope в тестовом процессе.

Вне TESTING слой мёртв: заголовок не читается, env не смотрится.
"""

from __future__ import annotations

import os

from core.config import is_testing
from core.logging import get_log_context

TEST_SCOPE_HEADER = "X-Test-Scope"
LOG_TEST_SCOPE = "test_scope"
TEST_SCOPE_DEFAULT_ENV = "TEST_SCOPE_DEFAULT"
TEST_SCOPE_STATIC_E2E = "test_e2e_static"


def resolve_test_scope() -> str | None:
    """Текущий test scope: лог-контекст запроса, затем env-дефолт E2E-фазы."""
    value = get_log_context().get(LOG_TEST_SCOPE)
    if isinstance(value, str) and value.strip():
        return value.strip()
    if not is_testing():
        return None
    default_scope = os.environ.get(TEST_SCOPE_DEFAULT_ENV)
    if default_scope and default_scope.strip():
        return default_scope.strip()
    return None
