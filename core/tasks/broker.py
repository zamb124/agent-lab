"""
TaskIQ брокер для всей системы.
"""

import os

from taskiq_redis import RedisStreamBroker, RedisAsyncResultBackend, ListRedisScheduleSource
from taskiq import TaskiqScheduler

from core.config.loader import load_merged_config
from core.tasks.session_lock import session_lock_middleware

# Загружаем конфиг: env var имеет приоритет над conf.json
_config = load_merged_config()
_redis_url = os.getenv("DATABASE__REDIS_URL") or _config.get("database", {}).get("redis_url", "redis://localhost:6379")

result_backend = RedisAsyncResultBackend(redis_url=_redis_url, result_ex_time=3600)
broker = RedisStreamBroker(url=_redis_url).with_result_backend(result_backend).with_middlewares(session_lock_middleware)

schedule_source = ListRedisScheduleSource(url=_redis_url, prefix="taskiq_schedules:")
scheduler = TaskiqScheduler(broker, sources=[schedule_source])


@broker.on_event("startup")
async def setup_worker_logging() -> None:
    from core.logging import setup_logging
    setup_logging("worker")
