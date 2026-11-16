"""Справочник имён адресообразующих объектов ГАР (AS_ADDR_OBJ).

Таблица ``geo_gar_addr_objects`` (``__global_model__``) — персистентная
часть состояния импорта региона: имена объектов по OBJECTID для сборки
канонического имени дома из materialized PATH. Полная выгрузка заменяет
таблицу целиком (``delete_region`` + батч-upsert), дельта — upsert
изменённых имён. Замена ``state_{region}.json`` и in-memory dict:
память импортёра не зависит от размера региона.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from oxyde import Field as DbField
from oxyde import execute_raw

from core.models.platform_model import PlatformModel
from core.types import SqlParameterValue

_BATCH = 5000


class GeoGarAddrObject(PlatformModel):
    """Имя адресообразующего объекта региона: ``(region, object_id) → name``."""

    __database_alias__: ClassVar[str | None] = "geo"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "geo_gar_addr_objects"
        unique_together: list[tuple[str, str]] = [("region", "object_id")]

    id: int | None = DbField(default=None, db_pk=True)
    region: str = DbField(max_length=64)
    object_id: int = DbField(db_type="BIGINT")
    name: str = DbField(default="", db_type="TEXT")

    @classmethod
    async def bulk_upsert_names(
        cls,
        *,
        region: str,
        rows: Sequence[tuple[int, str]],
        chunk_size: int = _BATCH,
    ) -> int:
        """Батч-upsert имён ``(object_id, name)``; конфликт — новое имя."""
        if not rows:
            return 0
        written = 0
        cols = 3
        for offset in range(0, len(rows), chunk_size):
            chunk = rows[offset : offset + chunk_size]
            values = ",".join(
                "(" + ",".join(f"${j * cols + k}" for k in range(1, cols + 1)) + ")"
                for j in range(len(chunk))
            )
            params: list[SqlParameterValue] = []
            for object_id, name in chunk:
                params.extend([region, object_id, name])
            _ = await execute_raw(
                f"""
                INSERT INTO geo_gar_addr_objects (region, object_id, name)
                VALUES {values}
                ON CONFLICT (region, object_id) DO UPDATE
                SET name = EXCLUDED.name
                """,
                params,
                using="geo",
            )
            written += len(chunk)
        return written

    @classmethod
    async def names_for(
        cls, *, region: str, object_ids: Sequence[int]
    ) -> dict[int, str]:
        """Имена заданных объектов региона — контекст PATH для чанка домов."""
        if not object_ids:
            return {}
        rows: list[dict[str, object]] = await execute_raw(
            """
            SELECT object_id, name FROM geo_gar_addr_objects
            WHERE region = $1
              AND object_id = ANY(string_to_array($2, ',')::bigint[])
            """,
            [region, ",".join(str(object_id) for object_id in object_ids)],
            using="geo",
        )
        return {int(str(row["object_id"])): str(row["name"]) for row in rows}

    @classmethod
    async def delete_region(cls, *, region: str, chunk_size: int = _BATCH) -> int:
        """Снос справочника региона перед полным импортом, чанками по ctid."""
        deleted = 0
        while True:
            rows = await execute_raw(
                """
                DELETE FROM geo_gar_addr_objects
                WHERE ctid IN (
                    SELECT ctid FROM geo_gar_addr_objects
                    WHERE region = $1
                    LIMIT $2
                )
                RETURNING id
                """,
                [region, chunk_size],
                using="geo",
            )
            deleted += len(rows)
            if len(rows) < chunk_size:
                return deleted
