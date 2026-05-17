from typing import Any, cast

from sqlalchemy import CursorResult, Result


def get_rowcount(result: Result[Any]) -> int:
    """
    Типобезопасное получение rowcount из результата SQLAlchemy.

    В SQLAlchemy 2.0 интерфейс Result не содержит атрибута rowcount,
    так как он специфичен для DML-операций (CursorResult).
    Этот хелпер выполняет безопасное приведение типов.
    """
    if isinstance(result, CursorResult):
        return int(result.rowcount or 0)

    # Если это не CursorResult (например, при использовании asyncpg напрямую через text()),
    # пробуем получить атрибут через cast, так как в рантайме он там часто есть.
    return int(cast(CursorResult[Any], result).rowcount or 0)
