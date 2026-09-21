"""Хелперы bind_log_context для доменных полей лог-контекста."""

from __future__ import annotations

from core.logging.attributes import LOG_SESSION_AGENT, LOG_TEST_SCOPE
from core.logging.context import bind_log_context


def bind_session_agent(session_id: str) -> None:
    bind_log_context(**{LOG_SESSION_AGENT: session_id})


def bind_test_scope(test_scope: str) -> None:
    bind_log_context(**{LOG_TEST_SCOPE: test_scope})
