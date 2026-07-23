"""Flows Worker (очередь ``flows_worker``).

Запуск: taskiq worker apps.flows_worker.worker:worker_app
"""

# ruff: noqa: E402, I001

from apps.flows.config import FlowSettings
from apps.flows.config import set_settings as set_flow_settings
from core.config.loader import load_merged_config
from core.tasks.logging_init import setup_worker_logging_early

_merged_flows = load_merged_config(service_name="flows", silent=True)
_flow_worker_settings = FlowSettings.model_validate(_merged_flows)
setup_worker_logging_early("flows_worker", logging_config=_flow_worker_settings.logging)
set_flow_settings(_flow_worker_settings)

import os
import socket

from taskiq import TaskiqState

from apps.flows.config import get_settings
from apps.flows.src.container import get_container
from apps.platform_tasks.wiring import wire_worker
from core.billing import set_billing_service
from core.billing.cbr_rate_provider import refresh_loop_coro as _cbr_loop_coro
from core.billing.cbr_rate_provider import refresh_rate_once as _cbr_refresh_once
from core.clients.llm.mock import configure_mock_llm_redis, get_or_create_global_mock_llm
from core.config import set_settings as set_core_settings
from core.config.testing import is_testing
from core.files.create_spec import FileCreateSpec, FileSourceKind, FileSourceRef
from core.files.processors import initialize_default_processors
from core.files.registry import default_retention_for_source
from core.files.writer import FileWriter
from core.logging import get_logger
from core.tasks.worker_bootstrap import (
    build_worker,
    connect_redis_with_backoff,
    init_worker_tracing,
)
from core.utils.background import run_with_log_context

logger = get_logger(__name__)

broker = wire_worker("flows_worker")


async def _startup(state: TaskiqState) -> None:
    service_name = "flows_worker"
    settings = get_settings()
    set_core_settings(settings)

    container = get_container()
    state.container = container

    set_billing_service(container.billing_service)
    logger.info("worker.billing_initialized", service=service_name)

    _cbr_fallback = settings.billing.usd_to_rub_rate
    await _cbr_refresh_once(fallback=_cbr_fallback)
    _ = run_with_log_context(
        _cbr_loop_coro(fallback=_cbr_fallback),
        name="billing.cbr_rate_refresh",
        background_kind="startup",
    )
    logger.info("worker.cbr_rate_initialized", service=service_name)

    initialize_default_processors(container.file_repository)

    FileWriter.configure_process_upload(
        files_service=container.files_service,
        default_spec=FileCreateSpec(
            source_kind=FileSourceKind.FLOW_ASSET,
            source_ref=FileSourceRef(flow_id="runtime"),
            retention=default_retention_for_source(FileSourceKind.FLOW_ASSET),
        ),
    )

    container.use_worker = False

    await connect_redis_with_backoff(container.redis_client, service_name=service_name)

    init_worker_tracing(service_name, container)

    platform_events_consumer = container.platform_event_consumer_service.build_group_consumer(
        consumer_name=f"{socket.gethostname()}-{os.getpid()}",
    )
    _ = run_with_log_context(
        platform_events_consumer.run(),
        name="platform_events.flows_consumer",
        background_kind="startup",
    )
    logger.info("worker.platform_events_consumer_started", service=service_name)

    logger.info(
        "worker.testing_flag",
        service=service_name,
        testing=is_testing(),
        testing_env=os.environ.get("TESTING"),
        pytest_current_test=os.environ.get("PYTEST_CURRENT_TEST"),
    )
    if is_testing():
        _ = get_or_create_global_mock_llm("mock-gpt-4")
        _ = configure_mock_llm_redis(container.redis_client)
        logger.info("worker.mock_llm_configured", service=service_name)

    logger.info("worker.container_initialized", service=service_name)


async def _shutdown(state: TaskiqState) -> None:
    container = get_container()
    _ = state
    try:
        await container.redis_client.close()
        logger.info("worker.redis_disconnected")
    except Exception as exc:
        logger.exception(
            "worker.redis_close_failed",
            **{"exception.type": type(exc).__name__},
        )


worker_app = build_worker(
    broker,
    service_name="flows_worker",
    queue="flows_worker",
    on_startup=_startup,
    on_shutdown=_shutdown,
)

__all__ = ["worker_app"]
