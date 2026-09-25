"""Ручной bootstrap cron-расписаний crawl.

Канон: idempotent регистрация в ``ensure_platform_schedules`` процесса scheduler.
Скрипт оставлен для локальной отладки; на проде достаточно rollout scheduler-api.
"""

from __future__ import annotations

import asyncio

from apps.scheduler.config import get_scheduler_settings
from apps.scheduler.crawl_schedule_bootstrap import ensure_search_crawl_schedules
from apps.scheduler.di import SchedulerDi
from core.di import ProcessIdentity, open_di


async def main() -> None:
    settings = get_scheduler_settings()
    identity = ProcessIdentity(service_name="scheduler", files_route_segment="scheduler")
    async with open_di(
        SchedulerDi,
        settings=settings,
        identity=identity,
        database="shared_url",
    ) as di:
        await ensure_search_crawl_schedules(scheduler_service=di.scheduler_service)
    print("crawl schedules ensured")


if __name__ == "__main__":
    asyncio.run(main())
