import base64
import json
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class CursorPage(BaseModel, Generic[T]):
    """Страница результатов с cursor-навигацией (keyset по created_at + id).

    Применяется для коллекций >1K, realtime-лент, экспорта.
    Cursor непрозрачен для клиента — не парсить, только передавать обратно.
    """

    items: list[T]
    next_cursor: str | None = None
    has_more: bool


class OffsetPage(BaseModel, Generic[T]):
    """Страница результатов с offset-навигацией.

    Применяется для admin UI, поиска с прыжком по страницам, таблиц <10K.
    """

    items: list[T]
    total: int
    limit: int
    offset: int


def encode_cursor(created_at: datetime, entity_id: str) -> str:
    """Кодирует keyset-позицию (created_at, id) в opaque cursor."""
    payload = json.dumps({"ts": created_at.isoformat(), "id": entity_id}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    """Декодирует cursor обратно в (created_at, entity_id).

    Raises:
        ValueError: если cursor повреждён или имеет неверный формат.
    """
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(payload["ts"]), payload["id"]
    except Exception as exc:
        raise ValueError(f"Невалидный cursor: {cursor!r}") from exc
