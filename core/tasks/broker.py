"""
Фабрика для создания TaskIQ brokers с общими настройками.

Конкретные brokers создаются в:
- apps/broker/broker.py - для платформенных задач (agents, crm)
- apps/rag_worker/broker.py - для RAG задач
"""

import asyncio
import os
from typing import Optional
from taskiq_redis import RedisStreamBroker, RedisAsyncResultBackend, ListRedisScheduleSource
from taskiq import TaskiqScheduler, TaskiqState
from taskiq.events import TaskiqEvents

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

from core.config import get_settings
from core.tasks.session_lock import session_lock_middleware
from core.logging import get_logger, setup_logging

logger = get_logger(__name__)


def create_broker(queue_name: Optional[str] = None) -> RedisStreamBroker:
    """
    Создает TaskIQ broker с общими настройками.
    
    Args:
        queue_name: Имя очереди (Redis Stream). Если None, использует "taskiq" (default).
        
    Returns:
        Настроенный RedisStreamBroker с result_backend и middlewares
    """
    settings = get_settings()
    broker_url = settings.tasks.broker_url
    
    queue_display = queue_name or "taskiq (default)"
    logger.info(f"🔧 Creating TaskIQ broker: queue={queue_display}, url={broker_url}")
    
    result_backend = RedisAsyncResultBackend(redis_url=broker_url, result_ex_time=3600)
    
    broker_kwargs = {"url": broker_url}
    if queue_name:
        broker_kwargs["queue_name"] = queue_name
    
    broker = RedisStreamBroker(**broker_kwargs).with_result_backend(result_backend).with_middlewares(session_lock_middleware)
    
    return broker


def create_scheduler(broker: RedisStreamBroker) -> TaskiqScheduler:
    """
    Создает scheduler для broker.
    
    Args:
        broker: TaskIQ broker
        
    Returns:
        TaskiqScheduler с Redis source
    """
    settings = get_settings()
    broker_url = settings.tasks.broker_url
    
    schedule_source = ListRedisScheduleSource(url=broker_url, prefix="taskiq_schedules:")
    scheduler = TaskiqScheduler(broker, sources=[schedule_source])
    
    return scheduler


def create_stale_tasks_recovery(queue_name: str = "taskiq"):
    """
    Возвращает функцию для восстановления зависших задач.
    
    Args:
        queue_name: Имя очереди (Redis Stream) для recovery
        
    Returns:
        Async функция для использования в @broker.on_event("startup")
    """
    async def recover_stale_pending_tasks() -> None:
        """
        При старте worker забираем зависшие pending задачи от мёртвых consumers.
        
        Если задача висит в pending > 2 минут, значит consumer скорее всего мёртв.
        XAUTOCLAIM переназначает такие задачи текущему consumer.
        """
        if not REDIS_AVAILABLE:
            logger.warning("redis не установлен, пропускаем recover_stale_pending_tasks")
            return
        
        settings = get_settings()
        broker_url = settings.tasks.broker_url
        
        logger.info(f"Starting recover_stale_pending_tasks for queue '{queue_name}'...")
        
        try:
            r = redis.from_url(broker_url)
            
            consumers = await r.xinfo_consumers(queue_name, queue_name)
            if not consumers:
                await r.aclose()
                return
            
            active = sorted(consumers, key=lambda c: c["idle"])
            if not active:
                await r.aclose()
                return
            
            current_consumer = active[0]["name"]
            
            result = await r.xautoclaim(
                queue_name, 
                queue_name, 
                current_consumer, 
                min_idle_time=120000,
                start_id="0-0",
                count=100
            )
            
            claimed_count = len(result[1]) if result and len(result) > 1 else 0
            if claimed_count > 0:
                logger.warning(f"Recovered {claimed_count} stale pending tasks from dead consumers (queue={queue_name})")
            else:
                logger.info(f"No stale tasks to recover (queue={queue_name})")
            
            await r.aclose()
            logger.info(f"recover_stale_pending_tasks completed successfully (queue={queue_name})")
            
        except Exception as e:
            logger.error(f"Could not recover pending tasks (queue={queue_name}): {e}", exc_info=True)
    
    return recover_stale_pending_tasks


def register_worker_events(
    broker: RedisStreamBroker, 
    startup_handler,
    shutdown_handler
) -> None:
    """
    Регистрирует кастомные startup/shutdown события для worker.
    
    Args:
        broker: TaskIQ broker
        startup_handler: Async функция (state: TaskiqState) -> None для startup
        shutdown_handler: Async функция (state: TaskiqState) -> None для shutdown
    """
    broker.on_event(TaskiqEvents.WORKER_STARTUP)(startup_handler)
    broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)(shutdown_handler)
    
    logger.info("✅ Worker events registered")


