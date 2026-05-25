from sqlalchemy import CursorResult, Result


def get_rowcount(result: Result[tuple[()]]) -> int:
    """Получить rowcount из результата DML-запроса SQLAlchemy."""
    if not isinstance(result, CursorResult):
        raise TypeError("DML query result must be a SQLAlchemy CursorResult")
    return result.rowcount
