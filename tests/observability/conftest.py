"""Fixtures for observability product-metric runtime tests."""

from __future__ import annotations

import sys
from collections.abc import Generator

import pytest
import pytest_asyncio

from core.context import set_context
from core.logging import get_logger
from core.models.context_models import Context
from core.models.identity_models import Company, User
from core.tracing import setup_tracing
from core.tracing.config import TracingConfig
from core.tracing.provider import set_tracing_enabled
from core.tracing.tracer import set_tracing_service_name
from core.utils.tokens import get_token_service

OBSERVABILITY_LOGGERS: tuple[str, ...] = (
    "core.tracing.operation_log_mirror",
    "core.tracing.tracer",
    "apps.flows.src.observability.flow_timing",
    "apps.flows.src.observability.handoff_timing",
    "apps.flows.src.observability.hitl_timing",
    "apps.flows.src.runtime.runners.llm_runner",
    "core.clients.llm.context_layer",
    "core.clients.llm.logging",
    "core.clients.voice_logging",
    "core.realtime.command_http",
    "core.tasks.logging_middleware",
    "platform.task",
    "apps.idle_worker.tasks.span_billing_settlement_tasks",
    "apps.rag.api.search",
    "core.rag.post_retrieval_rerank",
    "apps.flows.src.services.mcp_client",
)


def _rebind_observability_module_loggers() -> None:
    """structlog cache_logger_on_first_use: логгеры, импортированные до setup_logging, иначе молчат в caplog."""
    for module_name in OBSERVABILITY_LOGGERS:
        module = sys.modules.get(module_name)
        if module is None:
            continue
        fresh_logger = get_logger(module_name)
        if hasattr(module, "_logger"):
            setattr(module, "_logger", fresh_logger)
        if hasattr(module, "logger"):
            setattr(module, "logger", fresh_logger)


@pytest.fixture(scope="module", autouse=True)
def _observability_info_logging() -> Generator[None, None, None]:
    """structlog при LOGGING__LEVEL=WARNING не пишет INFO — для caplog поднимаем уровень."""
    from core.config import get_settings
    from core.logging.setup import reset_logging_for_tests, setup_logging

    settings = get_settings()
    warning_config = settings.logging
    info_config = warning_config.model_copy(update={"level": "INFO"})
    reset_logging_for_tests()
    setup_logging("pytest-observability", info_config)
    _rebind_observability_module_loggers()
    yield
    reset_logging_for_tests()
    setup_logging("pytest", warning_config)


@pytest.fixture
def observability_caplog(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    _rebind_observability_module_loggers()
    for logger_name in OBSERVABILITY_LOGGERS:
        caplog.set_level("INFO", logger=logger_name)
    return caplog


@pytest_asyncio.fixture
async def system_member_context(di, auth_token_system: str, mock_context: Context) -> Context:
    """Context с пользователем, который реально состоит в компании system."""
    token = get_token_service().validate_token(auth_token_system)
    if token is None:
        raise RuntimeError("auth_token_system невалиден")
    user = await User.get(token.user_id)
    if user is None:
        raise RuntimeError(f"пользователь {token.user_id} не найден")
    company = await Company.get("system")
    if company is None:
        raise RuntimeError("компания system не найдена")
    ctx = mock_context.model_copy(
        update={
            "user": user,
            "active_company": company,
            "auth_token": auth_token_system,
        }
    )
    set_context(ctx)
    return ctx


@pytest.fixture(autouse=True)
def enable_observability_tracing(di) -> Generator[None, None, None]:
    config = TracingConfig(
        enabled=True,
        postgres_enabled=True,
        tempo_enabled=False,
        service_name="platform-test",
    )
    setup_tracing(config)
    set_tracing_service_name("platform-test")
    set_tracing_enabled(True)
    yield
