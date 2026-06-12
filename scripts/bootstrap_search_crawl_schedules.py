"""Bootstrap crawl orchestrator schedules in platform scheduler."""

from __future__ import annotations

import asyncio

from core.clients.scheduler_client import SchedulerClient
from core.scheduler.models import (
    PlatformScheduleCreateRequest,
    PlatformScheduleFilter,
    PlatformScheduleType,
)


async def main() -> None:
    client = SchedulerClient()
    existing_tick = await client.list_schedules(
        PlatformScheduleFilter(task_name="crawl_orchestrator_tick", limit=500)
    )
    has_tick = any(
        item.payload.get("crawl_profile_id") == "runet_platform" for item in existing_tick.items
    )
    if not has_tick:
        await client.create_schedule(
            PlatformScheduleCreateRequest(
                target_service="search",
                task_name="crawl_orchestrator_tick",
                queue_name="search",
                schedule_type=PlatformScheduleType.CRON,
                cron="0 */6 * * *",
                timezone="UTC",
                payload={"crawl_profile_id": "runet_platform"},
            )
        )

    existing_reclaim = await client.list_schedules(
        PlatformScheduleFilter(task_name="crawl_reclaim_stale_fetching", limit=500)
    )
    if not existing_reclaim.items:
        await client.create_schedule(
            PlatformScheduleCreateRequest(
                target_service="search",
                task_name="crawl_reclaim_stale_fetching",
                queue_name="search",
                schedule_type=PlatformScheduleType.CRON,
                cron="*/15 * * * *",
                timezone="UTC",
                payload={},
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
