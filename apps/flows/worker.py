"""Flows Worker (очередь ``flows_worker``).

Запуск: taskiq worker apps.flows.worker:worker_app
"""

# ruff: noqa: E402, I001

from apps.flows.config import FlowSettings
from apps.flows.config import set_settings as set_flow_settings
from core.config.loader import load_merged_config
from core.files.urls import resolve_files_route_segment, set_files_route_segment
from core.tasks.logging_init import setup_worker_logging_early

_merged_flows = load_merged_config(service_name="flows", silent=True)
_flow_worker_settings = FlowSettings.model_validate(_merged_flows)
setup_worker_logging_early("flows_worker", logging_config=_flow_worker_settings.logging)
set_flow_settings(_flow_worker_settings)
_segment = resolve_files_route_segment("flows_worker")
set_files_route_segment(_segment)

import os
import socket
from collections.abc import AsyncIterator

from apps.flows.di import FlowsDi
from apps.flows.src.services.platform_event_consumer import PlatformEventConsumerService
from apps.flows.src.tools.authz_gate import bound_tool_authz_gate
from apps.worker_manifest import wire_worker
from core.billing.cbr_rate_provider import refresh_loop_coro as _cbr_loop_coro
from core.billing.cbr_rate_provider import refresh_rate_once as _cbr_refresh_once
from core.clients.redis_client import RedisClient
from core.config.models import BillingConfig
from core.di import recipe
from core.files.create_spec import RUNTIME_FLOW_ID, FileCreateSpec, FileSourceKind, FileSourceRef
from core.files.registry import default_retention_for_source
from core.files.service import FilesService
from core.files.writer import FileWriter
from core.logging import get_logger
from core.tasks.worker_bootstrap import build_worker, connect_redis_with_backoff
from core.utils.background import finish_background_task, run_with_log_context

logger = get_logger(__name__)

broker = wire_worker("flows_worker")


async def connect_flows_worker_redis(redis_client: RedisClient) -> None:
    await connect_redis_with_backoff(redis_client, service_name="flows_worker")


async def configure_flows_worker_files(files_service: FilesService) -> None:
    FileWriter.configure_process_upload(
        files_service=files_service,
        default_spec=FileCreateSpec(
            source_kind=FileSourceKind.FLOW_ASSET,
            source_ref=FileSourceRef(flow_id=RUNTIME_FLOW_ID),
            retention=default_retention_for_source(FileSourceKind.FLOW_ASSET),
        ),
    )


async def refresh_flows_worker_cbr_rate(billing: BillingConfig) -> AsyncIterator[None]:
    fallback = billing.usd_to_rub_rate
    await _cbr_refresh_once(fallback=fallback)
    refresh_task = run_with_log_context(
        _cbr_loop_coro(fallback=fallback),
        name="billing.cbr_rate_refresh",
        background_kind="startup",
    )
    logger.info("worker.cbr_rate_initialized", service="flows_worker")
    yield
    await finish_background_task(refresh_task)


async def run_flows_platform_events(
    platform_event_consumer_service: PlatformEventConsumerService,
) -> AsyncIterator[None]:
    consumer = platform_event_consumer_service.build_group_consumer(
        consumer_name=f"{socket.gethostname()}-{os.getpid()}",
    )
    consumer_task = run_with_log_context(
        consumer.run(),
        name="platform_events.flows_consumer",
        background_kind="startup",
    )
    logger.info("worker.platform_events_consumer_started", service="flows_worker")
    yield
    await finish_background_task(consumer_task)


worker_app = build_worker(
    broker,
    service_name="flows_worker",
    queue="flows_worker",
    settings=_flow_worker_settings,
    di_class=FlowsDi,
    database="flows_url",
    lifecycle=(
        recipe(bound_tool_authz_gate),
        recipe(connect_flows_worker_redis),
        recipe(configure_flows_worker_files),
        recipe(refresh_flows_worker_cbr_rate),
        recipe(run_flows_platform_events),
    ),
)

__all__ = ["worker_app"]
