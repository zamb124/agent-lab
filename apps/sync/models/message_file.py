"""Таблица sync."""

from __future__ import annotations

from typing import ClassVar

from oxyde import Field as DbField

from core.models.platform_model import PlatformModel


class SyncMessageFile(PlatformModel):
    """Строка ``sync_message_files``, алиас ``sync``, ``__global_model__``.

    В базе ключ — пара ``(message_id, file_id)``. Oxyde помечает ``db_pk`` только
    ``message_id``. ``save`` и PK-CRUD ``get``/``set``/``delete_by_id`` для неё не вызываются.
    В ``0001`` ключ остаётся составным, оба внешних ключа ON DELETE CASCADE.
    """

    __database_alias__: ClassVar[str | None] = "sync"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "sync_message_files"
        unique_together: list[tuple[str, str]] = [("message_id", "file_id")]

    message_id: str = DbField(db_pk=True, max_length=64)
    file_id: str = DbField(max_length=64)
    role: str = DbField(max_length=32)
