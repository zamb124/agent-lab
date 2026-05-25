"""
Per-session override таймаутов PostgreSQL для долгих воркер-задач.

Глобальные `statement_timeout` / `lock_timeout` /
`idle_in_transaction_session_timeout` задаются в `core/db/database.py` при
создании engine. Для отдельных запросов воркера (массовый scan, тяжёлый JOIN,
агрегация по компаниям) разрешено временно поднимать или отключать лимит
через `SET LOCAL`, действующий только внутри текущей транзакции.

Использование:

    async with session.begin():
        await override_session_timeouts(
            session,
            statement_timeout_ms=300_000,  # 5 минут
            lock_timeout_ms=60_000,
        )
        ...  # тяжёлая операция

Передача 0 в любой параметр отключает лимит для этой транзакции. None — не
менять. Все значения — в миллисекундах.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def override_session_timeouts(
    session: AsyncSession,
    *,
    statement_timeout_ms: int | None = None,
    lock_timeout_ms: int | None = None,
    idle_in_transaction_session_timeout_ms: int | None = None,
) -> None:
    """
    Меняет таймауты PostgreSQL только для текущей транзакции (`SET LOCAL`).

    Должно вызываться внутри открытой транзакции (после `session.begin()`),
    иначе `SET LOCAL` будет проигнорирован.
    """
    if statement_timeout_ms is not None:
        if statement_timeout_ms < 0:
            raise ValueError("statement_timeout_ms должен быть >= 0")
        await session.execute(text(f"SET LOCAL statement_timeout = {statement_timeout_ms}"))
    if lock_timeout_ms is not None:
        if lock_timeout_ms < 0:
            raise ValueError("lock_timeout_ms должен быть >= 0")
        await session.execute(text(f"SET LOCAL lock_timeout = {lock_timeout_ms}"))
    if idle_in_transaction_session_timeout_ms is not None:
        if idle_in_transaction_session_timeout_ms < 0:
            raise ValueError("idle_in_transaction_session_timeout_ms должен быть >= 0")
        await session.execute(
            text(
                "SET LOCAL idle_in_transaction_session_timeout = "
                f"{idle_in_transaction_session_timeout_ms}"
            )
        )
