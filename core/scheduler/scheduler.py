"""
TaskiqScheduler factory.
"""

from taskiq import TaskiqScheduler

from core.logging import get_logger
from core.scheduler.source import get_schedule_source
from apps.broker.broker import broker

logger = get_logger(__name__)


def create_scheduler(redis_url: str) -> TaskiqScheduler:
    """
    Создает TaskiqScheduler с RedisScheduleSource.
    
    Args:
        redis_url: URL Redis для schedule source
        
    Returns:
        TaskiqScheduler
    """
    source = get_schedule_source(redis_url)
    
    scheduler = TaskiqScheduler(
        broker=broker,
        sources=[source],
    )
    
    logger.info("TaskiqScheduler создан")
    return scheduler


__all__ = ["create_scheduler"]


