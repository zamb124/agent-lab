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


@broker.on_event("startup")
async def recover_stale_pending_tasks() -> None:
    """
    При старте worker забираем зависшие pending задачи от мёртвых consumers.
    
    Если задача висит в pending > 2 минут, значит consumer скорее всего мёртв.
    XAUTOCLAIM переназначает такие задачи текущему consumer.
    """
    import logging
    import redis.asyncio as redis
    
    logger = logging.getLogger(__name__)
    
    try:
        r = redis.from_url(_redis_url)
        
        # Получаем имя текущего consumer (TaskIQ генерирует UUID)
        consumers = await r.xinfo_consumers("taskiq", "taskiq")
        if not consumers:
            await r.aclose()
            return
        
        # Берём самого свежего (наш)
        active = sorted(consumers, key=lambda c: c["idle"])
        if not active:
            await r.aclose()
            return
        
        current_consumer = active[0]["name"]
        
        # XAUTOCLAIM: забираем задачи которые висят > 2 минут
        result = await r.xautoclaim(
            "taskiq", 
            "taskiq", 
            current_consumer, 
            min_idle_time=120000,  # 2 минуты
            start_id="0-0",
            count=100
        )
        
        claimed_count = len(result[1]) if result and len(result) > 1 else 0
        if claimed_count > 0:
            logger.warning(f"Recovered {claimed_count} stale pending tasks from dead consumers")
        
        await r.aclose()
        
    except Exception as e:
        logger.debug(f"Could not recover pending tasks: {e}")
