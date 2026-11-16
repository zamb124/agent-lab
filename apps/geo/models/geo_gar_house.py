"""Дома ГАР региона (AS_HOUSES + materialized PATH иерархии).

Таблица ``geo_gar_houses`` (``__global_model__``) — персистентное
состояние домов региона: guid, номер, строения, PATH до корня,
``active``, ``version`` последнего тронувшего архива. Заменяет
``state_{region}.json`` и in-memory dict'ы разбора: импортёр льёт
строки чанками, матч читает keyset-страницами ``object_id`` — пиковая
память не зависит от миллионов строк Москвы.

``version`` — область матча архива (``version = $v AND active`` =
дома, тронутые этим архивом; у полного — все активные) и метка
свежести: после полного импорта протухшие строки сносятся
``delete_stale``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar, NamedTuple

from oxyde import Field as DbField
from oxyde import execute_raw

from core.models.platform_model import PlatformModel
from core.types import SqlParameterValue

_BATCH = 5000


class GarHouseRow(NamedTuple):
    """Дом из AS_HOUSES для разбора и матча; ``path`` доливает иерархия."""

    object_id: int
    guid: str
    housenum: str
    addnum1: str
    addnum2: str
    path: str = ""


class GeoGarHouse(PlatformModel):
    """Строка дома региона; ключ — ``(region, object_id)``."""

    __database_alias__: ClassVar[str | None] = "geo"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "geo_gar_houses"
        unique_together: list[tuple[str, str]] = [("region", "object_id")]

    id: int | None = DbField(default=None, db_pk=True)
    region: str = DbField(max_length=64)
    object_id: int = DbField(db_type="BIGINT")
    guid: str = DbField(default="", max_length=36)
    housenum: str = DbField(default="", db_type="TEXT")
    addnum1: str = DbField(default="", db_type="TEXT")
    addnum2: str = DbField(default="", db_type="TEXT")
    path: str = DbField(default="", db_type="TEXT")
    active: bool = DbField(default=True)
    version: int = DbField(default=0, db_type="BIGINT")

    @classmethod
    async def bulk_upsert_active(
        cls,
        *,
        region: str,
        version: int,
        rows: Sequence[GarHouseRow],
        chunk_size: int = _BATCH,
    ) -> int:
        """Батч-upsert активных домов; ``path`` на конфликте сохраняется.

        Полный импорт перед разбором сносит таблицу — конфликтов нет;
        дельта обновляет поля дома, не затирая PATH иерархии. ГАР эмитит
        повторные строки одного OBJECTID — дедуп внутри чанка,
        побеждает последняя.
        """
        if not rows:
            return 0
        written = 0
        cols = 8
        for offset in range(0, len(rows), chunk_size):
            deduped = {
                house.object_id: house for house in rows[offset : offset + chunk_size]
            }
            values = ",".join(
                "(" + ",".join(f"${j * cols + k}" for k in range(1, cols + 1)) + ")"
                for j in range(len(deduped))
            )
            params: list[SqlParameterValue] = []
            for house in deduped.values():
                params.extend(
                    [
                        region,
                        house.object_id,
                        house.guid,
                        house.housenum,
                        house.addnum1,
                        house.addnum2,
                        True,
                        version,
                    ]
                )
            _ = await execute_raw(
                f"""
                INSERT INTO geo_gar_houses
                    (region, object_id, guid, housenum, addnum1, addnum2,
                     active, version)
                VALUES {values}
                ON CONFLICT (region, object_id) DO UPDATE
                SET guid = EXCLUDED.guid,
                    housenum = EXCLUDED.housenum,
                    addnum1 = EXCLUDED.addnum1,
                    addnum2 = EXCLUDED.addnum2,
                    active = true,
                    version = EXCLUDED.version
                """,
                params,
                using="geo",
            )
            written += len(deduped)
        return written

    @classmethod
    async def bulk_deactivate(
        cls,
        *,
        region: str,
        version: int,
        object_ids: Sequence[int],
        chunk_size: int = _BATCH,
    ) -> int:
        """Деактивация домов дельты: active → false; возвращает число строк."""
        if not object_ids:
            return 0
        deactivated = 0
        for offset in range(0, len(object_ids), chunk_size):
            chunk = object_ids[offset : offset + chunk_size]
            rows = await execute_raw(
                """
                UPDATE geo_gar_houses
                SET active = false, version = $2
                WHERE region = $1 AND active
                  AND object_id = ANY(string_to_array($3, ',')::bigint[])
                RETURNING id
                """,
                [region, version, ",".join(str(object_id) for object_id in chunk)],
                using="geo",
            )
            deactivated += len(rows)
        return deactivated

    @classmethod
    async def bulk_set_paths(
        cls,
        *,
        region: str,
        rows: Sequence[tuple[int, str]],
        chunk_size: int = _BATCH,
    ) -> int:
        """Долив materialized PATH: UPDATE FROM VALUES по object_id.

        Рядки иерархии чужих объектов промахиваются мимо домов — это
        и есть фильтрация AS_ADM_HIERARCHY без house_ids в памяти.
        Один object_id встречается в иерархии повторно (несколько
        родительских веток) — дедуп внутри чанка, последняя ветка
        побеждает детерминированно.
        """
        if not rows:
            return 0
        applied = 0
        cols = 2
        for offset in range(0, len(rows), chunk_size):
            deduped = dict(rows[offset : offset + chunk_size])
            values = ",".join(
                "(" + ",".join(f"${j * cols + k}" for k in range(1, cols + 1)) + ")"
                for j in range(len(deduped))
            )
            params: list[SqlParameterValue] = []
            for object_id, path in deduped.items():
                params.extend([object_id, path])
            params.append(region)
            _ = await execute_raw(
                f"""
                UPDATE geo_gar_houses AS h
                SET path = t.path
                FROM (VALUES {values}) AS t(object_id, path)
                WHERE h.region = ${len(params)} AND h.object_id = t.object_id
                """,
                params,
                using="geo",
            )
            applied += len(deduped)
        return applied

    @classmethod
    async def match_page(
        cls, *, region: str, version: int, last_object_id: int, limit: int
    ) -> list[GarHouseRow]:
        """Keyset-страница домов архива для матча; пустой список — конец."""
        rows: list[dict[str, object]] = await execute_raw(
            """
            SELECT object_id, guid, housenum, addnum1, addnum2, path
            FROM geo_gar_houses
            WHERE region = $1 AND active AND version = $2
              AND object_id > $3
            ORDER BY object_id
            LIMIT $4
            """,
            [region, version, last_object_id, limit],
            using="geo",
        )
        return [
            GarHouseRow(
                object_id=int(str(row["object_id"])),
                guid=str(row["guid"]),
                housenum=str(row["housenum"]),
                addnum1=str(row["addnum1"]),
                addnum2=str(row["addnum2"]),
                path=str(row["path"]),
            )
            for row in rows
        ]

    @classmethod
    async def has_region_rows(cls, *, region: str) -> bool:
        """В состоянии региона есть строки — база для дельт/резюме матча."""
        rows = await execute_raw(
            "SELECT 1 AS one FROM geo_gar_houses WHERE region = $1 LIMIT 1",
            [region],
            using="geo",
        )
        return len(rows) > 0

    @classmethod
    async def delete_region(cls, *, region: str, chunk_size: int = _BATCH) -> int:
        """Снос домов региона перед полным импортом, чанками по ctid."""
        deleted = 0
        while True:
            rows = await execute_raw(
                """
                DELETE FROM geo_gar_houses
                WHERE ctid IN (
                    SELECT ctid FROM geo_gar_houses
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
