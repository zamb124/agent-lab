"""
Точка входа для Idle Worker.

Запуск: taskiq worker apps.idle_worker.worker:worker_app
"""

# ruff: noqa: E402, I001

from apps.flows.config import FlowSettings
from apps.flows.config import set_settings as set_flow_settings
from core.config.loader import load_merged_config
from core.tasks.logging_init import setup_worker_logging_early

_merged_flows = load_merged_config(service_name="flows", silent=True)
_idle_worker_flow_settings = FlowSettings.model_validate(_merged_flows)
setup_worker_logging_early("idle_worker", logging_config=_idle_worker_flow_settings.logging)
set_flow_settings(_idle_worker_flow_settings)

import asyncio  # noqa: E402

from taskiq import TaskiqState  # noqa: E402

from apps.flows.config import get_settings  # noqa: E402
from apps.idle_worker.broker import broker as worker_app, recovery_handler  # noqa: E402
from apps.idle_worker.container import IdleWorkerContainer, get_container  # noqa: E402
from core.clients.llm.mock import configure_mock_llm_redis, get_or_create_global_mock_llm  # noqa: E402
from core.config.testing import is_testing  # noqa: E402
from core.logging import get_logger  # noqa: E402
from core.tasks.broker import register_worker_events  # noqa: E402
from core.tracing import setup_tracing  # noqa: E402
from core.tracing.tracer import set_span_repository, set_tracing_service_name  # noqa: E402

logger = get_logger(__name__)
_idle_worker_container: IdleWorkerContainer | None = None


async def idle_worker_startup(state: TaskiqState) -> None:
    """Инициализация контейнера при старте idle worker."""
    global _idle_worker_container
    settings = get_settings()

    container = get_container()
    _idle_worker_container = container
    state.container = container

    await recovery_handler()

    logger.info("worker.redis_connecting", service="idle_worker")
    retry_delays: tuple[int, ...] = (1, 2, 4, 8)
    max_retries = len(retry_delays) + 1
    for attempt in range(max_retries):
        try:
            await container.redis_client.connect()
            logger.info("worker.redis_connected", service="idle_worker")
            break
        except Exception:
            if attempt < max_retries - 1:
                wait_seconds = retry_delays[attempt]
                logger.warning(
                    "worker.redis_connect_retry",
                    service="idle_worker",
                    attempt=attempt + 1,
                    wait_seconds=wait_seconds,
                )
                await asyncio.sleep(wait_seconds)
            else:
                logger.error("worker.redis_connect_failed", service="idle_worker")
                raise

    if settings.tracing.enabled:
        setup_tracing(settings.tracing)
        if settings.tracing.postgres_enabled and hasattr(container, "span_repository"):
            if not settings.database.tracing_url:
                raise ValueError(
                    "tracing.postgres_enabled требует database.tracing_url (DATABASE__TRACING_URL)"
                )
            set_tracing_service_name("idle_worker")
            set_span_repository(container.span_repository)
        logger.info("worker.tracing_initialized", service="idle_worker")

    if is_testing():
        _ = get_or_create_global_mock_llm("mock-gpt-4")
        _ = configure_mock_llm_redis(container.redis_client)
        logger.info("worker.mock_llm_configured", service="idle_worker")

    logger.info("worker.container_initialized", service="idle_worker")


async def idle_worker_shutdown(state: TaskiqState) -> None:
    """Закрытие контейнера при остановке idle worker."""
    _ = state
    container = _idle_worker_container
    if container is not None:
        try:
            await container.redis_client.close()
            logger.info("worker.redis_disconnected", service="idle_worker")
        except Exception as exc:
            logger.exception(
                "worker.redis_close_failed",
                service="idle_worker",
                **{"exception.type": type(exc).__name__},
            )
    logger.info("worker.container_closed", service="idle_worker")


register_worker_events(
    worker_app,
    idle_worker_startup,
    idle_worker_shutdown,
    service_name="idle_worker",
)

import apps.idle_worker.tasks.mcp_catalog_tasks as _mcp_catalog_tasks  # noqa: E402
import apps.idle_worker.tasks.file_retention_tasks as _file_retention_tasks  # noqa: E402
import apps.idle_worker.tasks.calendar_sync_tasks as _calendar_sync_tasks  # noqa: E402
import apps.idle_worker.tasks.company_init_tasks as _company_init_tasks  # noqa: E402
import apps.idle_worker.tasks.llm_models_tasks as _llm_models_tasks  # noqa: E402
import apps.idle_worker.tasks.platform_free_models_tasks as _platform_free_models_tasks  # noqa: E402
import apps.idle_worker.tasks.payment_sync_tasks as _payment_sync_tasks  # noqa: E402
import apps.idle_worker.tasks.push_notification_tasks as _push_notification_tasks  # noqa: E402
import apps.idle_worker.tasks.span_billing_settlement_tasks as _span_billing_settlement_tasks  # noqa: E402

_TASK_REGISTRATION_MODULES = (
    _file_retention_tasks,
    _mcp_catalog_tasks,
    _calendar_sync_tasks,
    _company_init_tasks,
    _llm_models_tasks,
    _platform_free_models_tasks,
    _payment_sync_tasks,
    _push_notification_tasks,
    _span_billing_settlement_tasks,
)

__all__ = ["worker_app"]
