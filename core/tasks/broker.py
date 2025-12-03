"""
TaskIQ брокер для всей системы.

Использует Redis как backend для хранения задач и результатов.
Redis Streams обеспечивает блокирующую очередь - каждый воркер получает свою задачу.

Компоненты:
- broker: RedisStreamBroker с consumer groups
- result_backend: RedisAsyncResultBackend для хранения результатов
- schedule_source: ListRedisScheduleSource для отложенных задач
- scheduler: TaskiqScheduler для планирования
"""

from taskiq_redis import RedisStreamBroker, RedisAsyncResultBackend, ListRedisScheduleSource
from taskiq import TaskiqScheduler


def _get_redis_url() -> str:
    """Получить URL для Redis"""
    from core.config import get_settings
    settings = get_settings()
    return settings.database.redis_url


# Получаем URL сразу при импорте
_redis_url = _get_redis_url()

# Result backend для хранения результатов задач
result_backend = RedisAsyncResultBackend(
    redis_url=_redis_url,
    result_ex_time=3600,  # Результаты хранятся 1 час
)

# Broker с result backend и session lock middleware
# RedisStreamBroker использует consumer groups для блокирующего получения задач
# SessionLockMiddleware обеспечивает FIFO выполнение в рамках одной сессии
from core.tasks.session_lock import session_lock_middleware

broker = RedisStreamBroker(
    url=_redis_url,
).with_result_backend(result_backend).with_middlewares(session_lock_middleware)


@broker.on_event("startup")
async def setup_worker_logging() -> None:
    """Настройка логирования при запуске воркера"""
    from core.logging import setup_logging
    setup_logging("worker")


# Schedule source для отложенных задач (хранит расписания в Redis)
schedule_source = ListRedisScheduleSource(
    url=_redis_url,
    prefix="taskiq_schedules:",
)

# Scheduler для обработки отложенных задач
# Запускается отдельно: taskiq scheduler core.tasks.worker:scheduler
scheduler = TaskiqScheduler(broker, sources=[schedule_source])
