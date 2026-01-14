"""
Schedule source для TaskIQ.

Использует RedisScheduleSource для хранения scheduled tasks.
"""

from taskiq_redis import RedisScheduleSource

from core.logging import get_logger

logger = get_logger(__name__)


_schedule_source: RedisScheduleSource | None = None


def get_schedule_source(redis_url: str) -> RedisScheduleSource:
    """
    Получает или создает RedisScheduleSource.
    
    Args:
        redis_url: URL Redis
        
    Returns:
        RedisScheduleSource
    """
    global _schedule_source
    
    if _schedule_source is None:
        _schedule_source = RedisScheduleSource(redis_url)
        logger.info(f"RedisScheduleSource создан: {redis_url}")
    
    return _schedule_source


def reset_schedule_source() -> None:
    """Сбрасывает schedule source (для тестов)."""
    global _schedule_source
    _schedule_source = None


__all__ = ["get_schedule_source", "reset_schedule_source"]

