"""
Точка входа для TaskIQ flows worker.

Запуск: taskiq worker apps.flows_worker.worker:worker_app

Этот модуль:
1. Инициализирует settings сервисов
2. Импортирует worker app из apps.flows_worker.broker
3. Регистрирует startup/shutdown события
4. Регистрирует tasks всех сервисов
"""

# ruff: noqa: E402, I001

from apps.flows.config import FlowSettings
from apps.flows.config import set_settings as set_flow_settings
from core.config.loader import load_merged_config
from core.tasks.logging_init import setup_worker_logging_early

_merged_flows = load_merged_config(service_name="flows", silent=True)
_flow_worker_settings = FlowSettings(**_merged_flows)
setup_worker_logging_early("flows_worker", logging_config=_flow_worker_settings.logging)
set_flow_settings(_flow_worker_settings)

import asyncio  # noqa: E402

from taskiq import TaskiqState  # noqa: E402

from apps.flows.config import get_settings  # noqa: E402
from apps.flows.src.container import get_container  # noqa: E402
from apps.flows_worker.broker import broker as worker_app, recovery_handler  # noqa: E402
from core.billing import set_billing_service  # noqa: E402
from core.billing.cbr_rate_provider import refresh_loop_coro as _cbr_loop_coro  # noqa: E402
from core.billing.cbr_rate_provider import refresh_rate_once as _cbr_refresh_once  # noqa: E402
from core.clients.llm.factory import get_llm  # noqa: E402
from core.clients.llm.mock import configure_mock_llm_redis  # noqa: E402
from core.config import set_settings as set_core_settings  # noqa: E402
from core.config.testing import is_testing  # noqa: E402
from core.files.processors import initialize_default_processors  # noqa: E402
from core.files.writer import FileWriter  # noqa: E402
from core.logging import get_logger  # noqa: E402
from core.tasks.broker import register_worker_events  # noqa: E402
from core.tracing import setup_tracing  # noqa: E402
from core.tracing.tracer import set_span_repository, set_tracing_service_name  # noqa: E402
from core.utils.background import run_with_log_context  # noqa: E402

logger = get_logger(__name__)


async def _initialize_worker_state(state: TaskiqState, service_name: str) -> None:
    """Инициализация контейнера при старте worker."""
    settings = get_settings()
    set_core_settings(settings)

    container = get_container()
    state.container = container

    await recovery_handler()

    set_billing_service(container.billing_service)
    logger.info("worker.billing_initialized", service=service_name)

    _cbr_fallback = settings.billing.usd_to_rub_rate
    await _cbr_refresh_once(fallback=_cbr_fallback)
    run_with_log_context(
        _cbr_loop_coro(fallback=_cbr_fallback),
        name="billing.cbr_rate_refresh",
        background_kind="startup",
    )
    logger.info("worker.cbr_rate_initialized", service=service_name)

    initialize_default_processors(container.file_repository)

    s = get_settings()
    FileWriter.configure_process_upload(
        file_processor=container.file_processor,
        download_url_prefix=f"/{s.server.name}/api/v1/files/download",
    )

    container.use_worker = False

    logger.info("worker.redis_connecting", service=service_name)
    max_retries = 5
    for attempt in range(max_retries):
        try:
            await container.redis_client.connect()
            logger.info("worker.redis_connected", service=service_name)
            break
        except Exception:
            if attempt < max_retries - 1:
                wait_seconds = 2**attempt
                logger.warning(
                    "worker.redis_connect_retry",
                    service=service_name,
                    attempt=attempt + 1,
                    wait_seconds=wait_seconds,
                )
                await asyncio.sleep(wait_seconds)
            else:
                logger.error("worker.redis_connect_failed", service=service_name)
                raise

    if settings.tracing.enabled:
        setup_tracing(settings.tracing)
        if settings.tracing.postgres_enabled and hasattr(container, "span_repository"):
            if not settings.database.tracing_url:
                raise ValueError(
                    "tracing.postgres_enabled требует database.tracing_url (DATABASE__TRACING_URL)"
                )
            set_tracing_service_name("flows_worker")
            set_span_repository(container.span_repository)
        logger.info("worker.tracing_initialized", service=service_name)

    if is_testing():
        get_llm("mock-gpt-4")
        configure_mock_llm_redis(container.redis_client)
        logger.info("worker.mock_llm_configured", service=service_name)

    logger.info("worker.container_initialized", service=service_name)


async def worker_startup(state: TaskiqState) -> None:
    """Инициализация контейнера при старте platform worker."""
    await _initialize_worker_state(state=state, service_name="flows_worker")


async def worker_shutdown(state: TaskiqState) -> None:
    """Закрытие контейнера при остановке worker."""
    if hasattr(state, "container"):
        try:
            await state.container.redis_client.close()
            logger.info("worker.redis_disconnected")
        except Exception as exc:
            logger.exception(
                "worker.redis_close_failed",
                **{"exception.type": type(exc).__name__},
            )
    logger.info("worker.container_closed")


register_worker_events(
    worker_app,
    worker_startup,
    worker_shutdown,
    service_name="flows_worker",
)

import apps.flows.src.tasks.company_init_tasks as _company_init_tasks  # noqa: E402
import apps.flows.src.tasks.flow_tasks as _flow_tasks  # noqa: E402
import apps.flows.src.tasks.llm_tasks as _llm_tasks  # noqa: E402
import apps.flows.src.tasks.node_tasks as _node_tasks  # noqa: E402
import apps.flows.src.tasks.scheduled_tasks as _scheduled_tasks  # noqa: E402
import apps.flows.src.tasks.tool_tasks as _tool_tasks  # noqa: E402

_TASK_REGISTRATION_MODULES = (
    _company_init_tasks,
    _flow_tasks,
    _llm_tasks,
    _node_tasks,
    _scheduled_tasks,
    _tool_tasks,
)

# CRM attachment tasks теперь в rag worker (apps/rag_worker/worker.py)
# import apps.crm.tasks.attachment_tasks  # noqa: F401

__all__ = ["worker_app"]
