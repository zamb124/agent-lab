"""Строка таблицы ``storage``: ключ и JSON-значение."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index, execute_raw

from core.models.platform_model import PlatformModel
from core.types import JsonValue, parse_json_value, require_json_object

# Драйвер кэширует подготовленный запрос по тексту SQL вместе с типами параметров первого
# вызова: NULL, а затем datetime в том же $N портят значение (UTF8 0x00). Необязательная
# дата поэтому входит в текст запроса только когда она задана.

_INSERT_ROW = """
INSERT INTO storage (key, value, expired_at, created_at, updated_at)
VALUES ($1, $2::jsonb, {expired_at}, $3::timestamptz, $3::timestamptz)
"""

_UPSERT_CONFLICT = """
ON CONFLICT (key) DO UPDATE SET
    value = EXCLUDED.value,
    updated_at = EXCLUDED.updated_at,
    expired_at = EXCLUDED.expired_at
RETURNING key
"""

_INSERT_ONCE_CONFLICT = """
ON CONFLICT (key) DO NOTHING
RETURNING key
"""


def _row_insert(
    key: str,
    value: str,
    expired_at: datetime | None,
    conflict: str,
) -> tuple[str, list[str | datetime]]:
    params: list[str | datetime] = [key, json.dumps(parse_json_value(value)), datetime.now(timezone.utc)]
    expired_at_sql = "NULL"
    if expired_at is not None:
        if expired_at.tzinfo is None:
            raise ValueError("storage expired_at must be timezone-aware")
        params.append(expired_at)
        expired_at_sql = "$4::timestamptz"
    return _INSERT_ROW.format(expired_at=expired_at_sql) + conflict, params


class StorageEntry(PlatformModel):
    """KV-строка. Алиас базы задаёт клиент ``Storage`` на каждом запросе."""

    __global_model__: ClassVar[bool] = True
    __database_aliases__: ClassVar[tuple[str, ...]] = ("shared", "tracing")

    class Meta:
        is_table: bool = True
        table_name: str = "storage"
        indexes: list[Index] = [
            Index(["updated_at"]),
            Index(["expired_at"]),
        ]

    key: str = DbField(db_pk=True, db_type="TEXT")
    value: JsonValue = DbField(db_type="JSONB")
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    expired_at: datetime | None = DbField(default=None)

    @classmethod
    async def row(
        cls,
        key: str,
        *,
        alias: str,
        for_update: bool,
    ) -> Self | None:
        query = cls.objects.filter(key=key)
        if for_update:
            query = query.for_update()
        return await query.get_or_none(using=alias)

    @classmethod
    async def upsert_by_key(
        cls,
        key: str,
        value: str,
        expired_at: datetime | None,
        *,
        alias: str,
    ) -> None:
        sql, params = _row_insert(key, value, expired_at, _UPSERT_CONFLICT)
        _ = await execute_raw(sql, params, using=alias)

    @classmethod
    async def insert_once(
        cls,
        key: str,
        value: str,
        expired_at: datetime | None,
        *,
        alias: str,
    ) -> bool:
        sql, params = _row_insert(key, value, expired_at, _INSERT_ONCE_CONFLICT)
        rows = await execute_raw(sql, params, using=alias)
        return len(rows) > 0

    @classmethod
    async def list_unordered_by_key_prefix(
        cls,
        prefix: str,
        *,
        alias: str,
        limit: int,
    ) -> list[Self]:
        """Строки по префиксу ключа. Порядка нет. limit обязателен и в теле не проверяется."""
        return await (
            cls.objects.filter(key__startswith=prefix)
            .limit(limit)
            .all(using=alias)
        )

    @classmethod
    async def count_by_key_prefix(cls, prefix: str, *, alias: str) -> int:
        return await cls.objects.filter(key__startswith=prefix).count(using=alias)

    @classmethod
    async def delete_key(cls, key: str, *, alias: str) -> bool:
        deleted = await cls.objects.filter(key=key).delete(using=alias)
        return deleted > 0

    @classmethod
    async def json_text_values_by_prefix_equals_created_at_asc_or_desc(
        cls,
        prefix: str,
        *,
        field: str,
        equals: str,
        limit: int,
        newest_first: bool,
        alias: str,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> list[str]:
        """Тексты value по префиксу ключа и равенству поля JSON. newest_first — ORDER BY created_at DESC, иначе ASC. limit обязателен и в теле не проверяется. created_after и created_before равные None не фильтруют. Нестроковый value — TypeError."""
        params: list[str | int | datetime] = [f"{prefix}%", field, equals]
        conditions = ["key LIKE $1", "value ->> $2 = $3"]
        if created_after is not None:
            params.append(created_after)
            conditions.append(f"(value ->> 'created_at')::timestamptz >= ${len(params)}::timestamptz")
        if created_before is not None:
            params.append(created_before)
            conditions.append(f"(value ->> 'created_at')::timestamptz < ${len(params)}::timestamptz")
        params.append(limit)
        direction = "DESC" if newest_first else "ASC"
        where = " AND ".join(conditions)
        order = f"(value ->> 'created_at')::timestamptz {direction}"
        rows = await execute_raw(
            f"SELECT value::text AS value FROM storage WHERE {where} ORDER BY {order} LIMIT ${len(params)}",
            params,
            using=alias,
        )
        payloads: list[str] = []
        for row in rows:
            payload = require_json_object(row, "storage")
            raw_value = payload["value"]
            if not isinstance(raw_value, str):
                raise TypeError("storage.value must be text")
            payloads.append(raw_value)
        return payloads

    @classmethod
    async def list_by_key_prefix_updated_at_desc(
        cls,
        prefix: str,
        *,
        alias: str,
        limit: int,
        offset: int,
    ) -> list[Self]:
        """Строки по префиксу ключа, ORDER BY updated_at DESC. limit и offset обязательны и в теле не проверяются."""
        return await (
            cls.objects.filter(key__startswith=prefix)
            .order_by("-updated_at")
            .limit(limit)
            .offset(offset)
            .all(using=alias)
        )

    @classmethod
    async def list_unordered_by_keys(cls, keys: list[str], *, alias: str) -> list[Self]:
        """Строки по ключам. Порядка и предела нет. Пустой список ключей в теле не отсекается. Отсутствующие ключи не входят."""
        return await cls.objects.filter(key__in=keys).all(using=alias)
