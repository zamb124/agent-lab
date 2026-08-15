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

Event-driven side-effect (daily/period summary, note markdown format) при enqueue получает
``{parent_scope}:{kind}`` (см. ``side_effect_test_scope``), чтобы A2A/LLM
фона не снимал FIFO ``mock_llm:responses:<parent>``, который тест готовил
для note-analyze / flow.

E2E UI (Playwright): браузер шлёт ``X-Test-Scope`` per xdist-worker
(``test_e2e_gwN``, см. ``tests/ui/e2e_worker.py``); pytest биндит тот же scope
для ``flows_seed_mock_llm``. Desktop/agent E2E без заголовка — fallback
``TEST_SCOPE_DEFAULT`` / ``TEST_SCOPE_STATIC_E2E``.

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
MOCK_LLM_SIDE_EFFECT_CRM_SUMMARY = "crm_summary"
MOCK_LLM_SIDE_EFFECT_NOTE_MARKDOWN = "note_markdown"


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


def side_effect_test_scope(test_scope: str, kind: str) -> str:
    """Scope фона, отдельный от FIFO MockLLM породившего теста."""
    scope = test_scope.strip()
    effect_kind = kind.strip()
    if not scope:
        raise ValueError("side_effect_test_scope: test_scope не должен быть пустым")
    if not effect_kind:
        raise ValueError("side_effect_test_scope: kind не должен быть пустым")
    if ":" in effect_kind:
        raise ValueError("side_effect_test_scope: kind не должен содержать ':'")
    return f"{scope}:{effect_kind}"


def mock_llm_side_effect_enqueue_labels(kind: str) -> dict[str, str] | None:
    """TaskIQ label test_scope для side-effect, либо None вне теста."""
    scope = resolve_test_scope()
    if scope is None:
        return None
    return {LOG_TEST_SCOPE: side_effect_test_scope(scope, kind)}
