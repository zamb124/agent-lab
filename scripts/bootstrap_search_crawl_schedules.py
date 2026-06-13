"""Legacy manual bootstrap for crawl cron schedules.

Канон: idempotent регистрация в apps/scheduler/main.py::on_startup.
Скрипт оставлен для локальной отладки; на проде достаточно rollout scheduler-api.
"""

from __future__ import annotations

import asyncio

from apps.scheduler.container import get_scheduler_container
from apps.scheduler.crawl_schedule_bootstrap import ensure_search_crawl_schedules


async def main() -> None:
    await ensure_search_crawl_schedules(container=get_scheduler_container())
    print("crawl schedules ensured")


if __name__ == "__main__":
    asyncio.run(main())
