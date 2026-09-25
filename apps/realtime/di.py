"""DI процесса realtime: bus PlatformEvent и sweeper просроченных команд."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated

from apps.realtime.services.bus_service import RealtimeBusService
from core.config.models import RealtimeConfig
from core.di import http_di, recipe, task_di
from core.di.platform import PlatformDi
from core.logging import get_logger
from core.realtime.submit import bind_local_event_ingest, unbind_local_event_ingest
from core.utils.background import run_with_log_context

logger = get_logger(__name__)


async def _sweep_loop(bus_service: RealtimeBusService, interval_seconds: float) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            swept = await bus_service.sweep_expired_commands()
        except Exception:
            logger.exception("realtime.sweeper.failed")
            continue
        if swept:
            logger.info("realtime.sweeper.expired", count=swept)


@recipe
async def command_deadline_sweeper(
    bus_service: RealtimeBusService,
    realtime: RealtimeConfig,
) -> AsyncIterator[None]:
    """Фоновый sweeper и локальный ingest bus на время жизни процесса."""
    bind_local_event_ingest(bus_service.ingest)
    sweeper = run_with_log_context(
        _sweep_loop(bus_service, realtime.sweeper_interval_seconds),
        name="realtime.sweeper",
        background_kind="polling",
    )
    logger.info("realtime.bus")
    yield
    _ = sweeper.cancel()
    unbind_local_event_ingest()
    logger.info("realtime.bus")


class RealtimeDi(PlatformDi):
    bus_service: RealtimeBusService


Di = Annotated[RealtimeDi, http_di(RealtimeDi), task_di(RealtimeDi)]
