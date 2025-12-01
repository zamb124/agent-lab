"""
TaskIQ брокер для всей системы.

Использует PostgreSQL (Shared DB) как backend для хранения задач и результатов.
Broker создается при импорте, но соединение устанавливается только при startup().

Компоненты:
- broker: Основной брокер для задач
- result_backend: Хранение результатов выполнения
- schedule_source: Источник расписаний для отложенных задач
- scheduler: Планировщик для обработки отложенных задач
"""

from taskiq_pg.asyncpg import AsyncpgBroker, AsyncpgResultBackend, AsyncpgScheduleSource
from taskiq.serializers import JSONSerializer
from taskiq import TaskiqScheduler


def _get_dsn() -> str:
    """Получить DSN для PostgreSQL (вызывается при startup)"""
    from core.config import get_settings
    settings = get_settings()
    dsn = settings.database.shared_url
    # asyncpg требует postgresql:// а не postgresql+asyncpg://
    if dsn.startswith("postgresql+asyncpg://"):
        dsn = dsn.replace("postgresql+asyncpg://", "postgresql://", 1)
    return dsn


# Result backend для хранения результатов задач
result_backend = AsyncpgResultBackend(
    dsn=_get_dsn,
    serializer=JSONSerializer(),
)

# Broker с result backend
broker = AsyncpgBroker(dsn=_get_dsn).with_result_backend(result_backend)

# Schedule source для отложенных задач (хранит расписания в PostgreSQL)
# Требует broker как первый аргумент
schedule_source = AsyncpgScheduleSource(broker=broker, dsn=_get_dsn)

# Scheduler для обработки отложенных задач
# Запускается отдельно: taskiq scheduler core.tasks.worker:scheduler
scheduler = TaskiqScheduler(broker, sources=[schedule_source])
