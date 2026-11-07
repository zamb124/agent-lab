"""Periodic WebSocket presence snapshot metrics for Grafana."""

from __future__ import annotations

import time

from apps.idle.di import Di
from apps.idle.tasks.task_names import TASK_REALTIME_PRESENCE_TICK
from core.internal_context_headers import build_internal_context_headers
from core.logging import get_logger
from core.logging.attributes import (
    EVENT_WS_PRESENCE_SNAPSHOT,
    LOG_WS_ACTIVE_CHANNELS,
    LOG_WS_ONLINE_USERS,
    LOG_WS_PRESENCE_DURATION_MS,
)
from core.models.identity_models.contracts import SYSTEM_COMPANY_ID
from core.realtime.models import PresenceStatsResponse
from core.tasks import platform_task

logger = get_logger("platform.realtime_presence")

PRESENCE_TICK_USER_ID = "platform.scheduler.presence_tick"


@platform_task(TASK_REALTIME_PRESENCE_TICK)
async def realtime_presence_tick(
    *,
    di: Di,
    schedule_task_id: str | None = None,
    company_id: str | None = None,
) -> dict[str, int]:
    """Снимок Centrifugo-каналов → событие ws_presence_snapshot для дашборда WebSocket."""
    _ = schedule_task_id
    started = time.perf_counter()
    stats = PresenceStatsResponse.model_validate(
        await di.service_client.get(
            "realtime",
            "/realtime/api/v1/internal/presence/stats",
            timeout=10.0,
            headers=build_internal_context_headers(
                company_id=company_id if company_id else SYSTEM_COMPANY_ID,
                user_id=PRESENCE_TICK_USER_ID,
            ),
        ),
    )
    online_users = stats.online_users
    active_channels = stats.active_channels
    duration_ms = round((time.perf_counter() - started) * 1000.0, 3)
    logger.info(
        EVENT_WS_PRESENCE_SNAPSHOT,
        **{
            LOG_WS_ONLINE_USERS: online_users,
            LOG_WS_ACTIVE_CHANNELS: active_channels,
            LOG_WS_PRESENCE_DURATION_MS: duration_ms,
        },
    )
    return {"online_users": online_users, "active_channels": active_channels}
