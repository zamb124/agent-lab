import base64
import binascii
from datetime import datetime
from typing import ClassVar, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

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


class ListResponse(BaseModel, Generic[T]):
    """Обертка для списков без пагинации (взамен голых List[]).

    Применяется для небольших коллекций, где пагинация пока избыточна.
    """
    items: list[T]


class CursorToken(BaseModel):
    """Внутреннее содержимое opaque cursor."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", populate_by_name=True)

    ts: datetime
    entity_id: str = Field(alias="id")


def encode_cursor(created_at: datetime, entity_id: str) -> str:
    """Кодирует keyset-позицию (created_at, id) в opaque cursor."""
    payload = CursorToken(ts=created_at, id=entity_id).model_dump_json(by_alias=True)
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    """Декодирует cursor обратно в (created_at, entity_id).

    Исключения:
        ValueError: если cursor повреждён или имеет неверный формат.
    """
    try:
        payload = base64.urlsafe_b64decode(cursor.encode())
        decoded = CursorToken.model_validate_json(payload)
        return decoded.ts, decoded.entity_id
    except (binascii.Error, ValueError, ValidationError) as exc:
        raise ValueError(f"Невалидный cursor: {cursor!r}") from exc
