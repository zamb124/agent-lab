"""
TaskIQ брокер для всей системы.

Использует PostgreSQL (Shared DB) как backend для хранения задач и результатов.
Broker создается при импорте, но соединение устанавливается только при startup().
"""

from taskiq_pg import AsyncpgBroker, AsyncpgResultBackend
from taskiq.serializers import JSONSerializer


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
