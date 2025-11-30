"""
TaskIQ брокер для всей системы.

Использует PostgreSQL (Shared DB) как backend для хранения задач.
Broker создается при импорте, но соединение устанавливается только при startup().
"""

from taskiq_pg import AsyncpgBroker


def _get_dsn() -> str:
    """Получить DSN для PostgreSQL (вызывается при startup)"""
    from core.config import get_settings
    settings = get_settings()
    dsn = settings.database.shared_url
    # asyncpg требует postgresql:// а не postgresql+asyncpg://
    if dsn.startswith("postgresql+asyncpg://"):
        dsn = dsn.replace("postgresql+asyncpg://", "postgresql://", 1)
    return dsn


# Broker создается при импорте, но DSN резолвится только при startup()
broker = AsyncpgBroker(dsn=_get_dsn)
