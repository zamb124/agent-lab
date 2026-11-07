"""Коррекция геоданных администратором — evergreen-правки поверх импортов.

Источник правды для правки — не строка поколения (она умрёт при свопе),
а таблицы оверлеев: ``geo_address_overrides`` (патч + тумбстоун адреса),
``geo_suppressions`` (тумбстоун барьера/светофора/запрета/ребра),
``geo_edge_overrides`` (закрытие режимов на way). Сервис пишет оверлей и
мгновенно применяет его к живому поколению; импортёр повторяет то же
применение на каждое новое поколение (``OsmImportService._apply_overlays``).

Ручные адреса — строки ``geo_addresses`` с ``generation=0``,
``osm_type='manual'`` и отрицательным ``osm_id`` из ``geo_manual_id_seq``:
чистка поколений их не трогает (``generation > 0`` в DELETE).

Точность координат правок проверяется диапазоном полей payload
(Pydantic ge/le); граница покрытия намеренно не ограничивает — админ
может править адреса вне bbox региона.
"""

from __future__ import annotations

from datetime import UTC, datetime

from oxyde import execute_raw

from apps.geo.config import GeoSettings
from apps.geo.models.api import (
    GeoAddressHit,
    GeoAddressUpdateRequest,
    GeoOverrideItem,
    GeoOverrideListResponse,
    RouteMode,
)
from apps.geo.models.geo_address_override import GeoAddressOverride
from apps.geo.models.geo_edge_override import GeoEdgeOverride
from apps.geo.models.geo_import_state import GeoImportState
from apps.geo.models.geo_stats import GeoStats
from apps.geo.models.geo_suppression import GeoSuppression
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.types import JsonObject, JsonScalar, JsonValue, SqlParameterValue

_ADDRESS_PATCH_FIELDS = (
    "display_name",
    "city",
    "street",
    "housenumber",
    "postcode",
    "lat",
    "lng",
)

_SUPPRESSION_TARGETS: dict[str, tuple[str, str]] = {
    "barrier": ("geo_barriers", "osm_node_id"),
    "signal": ("geo_traffic_signals", "osm_node_id"),
    "restriction": ("geo_turn_restrictions", "osm_relation_id"),
    "edge": ("geo_road_edges", "osm_way_id"),
}
# OSM-тип id в тумбстоуне — по id-колонке сущности; нужен аудиту для отката.
_SUPPRESSION_OSM_TYPE: dict[str, str] = {
    "barrier": "node",
    "signal": "node",
    "restriction": "relation",
    "edge": "way",
}


def _json_scalar(value: JsonValue | None, field: str) -> JsonScalar:
    """Скаляр из before-снапшота; составное значение — повреждённый снапшот."""
    if not isinstance(value, str | int | float | bool):
        raise PlatformConflictError(
            f"corrupted override snapshot field {field!r}",
            error_code="geo_override_not_found",
        )
    return value


class GeoAdminService:
    """Правки админа к геоданным: оверлеи + мгновенное применение к живому."""

    def __init__(self, settings: GeoSettings) -> None:
        self._settings: GeoSettings = settings

    async def create_address(
        self,
        *,
        display_name: str,
        city: str,
        street: str,
        housenumber: str,
        postcode: str,
        lat: float,
        lng: float,
        region: str,
        user_id: str,
    ) -> GeoAddressHit:
        """Ручной адрес: evergreen-строка gen0 с отрицательным osm_id."""
        _ = user_id  # аудит ручных адресов — строка справочника, не оверлей
        rows: list[dict[str, SqlParameterValue]] = await execute_raw(
            """
            INSERT INTO geo_addresses
                (osm_type, osm_id, display_name, city, street, housenumber,
                 postcode, lat, lng, region, generation, source, created_at)
            VALUES ('manual', -nextval('geo_manual_id_seq'), $1, $2, $3, $4,
                    $5, $6, $7, $8, 0, 'manual', $9)
            RETURNING id, osm_id
            """,
            [
                display_name,
                city,
                street,
                housenumber,
                postcode,
                lat,
                lng,
                region,
                datetime.now(UTC),
            ],
            using="geo",
        )
        row_id = int(str(rows[0]["id"]))
        osm_id = int(str(rows[0]["osm_id"]))
        await self._bump_manual_stats(region)
        return GeoAddressHit(
            id=row_id,
            osm_type="manual",
            osm_id=osm_id,
            display_name=display_name,
            city=city,
            street=street,
            housenumber=housenumber,
            postcode=postcode,
            lat=lat,
            lng=lng,
        )

    async def update_address(
        self, payload: GeoAddressUpdateRequest, *, user_id: str
    ) -> GeoAddressHit:
        """Патч адреса: override для OSM-строки, прямой UPDATE для manual."""
        row = await self._live_row(payload.osm_type, payload.osm_id)
        patch = {
            f: getattr(payload, f)
            for f in _ADDRESS_PATCH_FIELDS
            if getattr(payload, f) is not None
        }
        if payload.osm_type == "manual":
            if not patch:
                return self._hit(row)
            await self._apply_live_patch(int(str(row["id"])), patch)
            row.update(patch)
            return self._hit(row)

        override = GeoAddressOverride(
            osm_type=payload.osm_type,
            osm_id=payload.osm_id,
            display_name=payload.display_name,
            city=payload.city,
            street=payload.street,
            housenumber=payload.housenumber,
            postcode=payload.postcode,
            lat=payload.lat,
            lng=payload.lng,
            suppressed=False,
            reason=payload.reason,
            updated_by=user_id,
            before=self._before_snapshot(row),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        _ = await GeoAddressOverride.upsert_by_object(override)
        if patch:
            await self._apply_live_patch(int(str(row["id"])), patch)
            row.update(patch)
        return self._hit(row)

    async def remove_address(
        self, *, osm_type: str, osm_id: int, reason: str, user_id: str
    ) -> None:
        """Скрытие адреса: удаление manual-строки или тумбстоун на OSM."""
        row = await self._live_row(osm_type, osm_id)
        if osm_type == "manual":
            _ = await execute_raw(
                "DELETE FROM geo_addresses WHERE id = $1",
                [row["id"]],
                using="geo",
            )
            await self._bump_manual_stats(str(row["region"]))
            return
        override = GeoAddressOverride(
            osm_type=osm_type,
            osm_id=osm_id,
            suppressed=True,
            reason=reason,
            updated_by=user_id,
            before=self._before_snapshot(row),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        _ = await GeoAddressOverride.upsert_by_object(override)
        _ = await execute_raw(
            "DELETE FROM geo_addresses WHERE id = $1",
            [row["id"]],
            using="geo",
        )

    async def revert_override(self, *, osm_type: str, osm_id: int) -> GeoAddressHit | None:
        """Откат правки админа: восстановление по before + удаление оверлея."""
        override = await GeoAddressOverride.by_object(
            osm_type=osm_type, osm_id=osm_id
        )
        if override is None:
            raise PlatformNotFoundError(
                f"geo override {osm_type}/{osm_id} not found",
                error_code="geo_override_not_found",
            )
        _ = await GeoAddressOverride.delete_by_object(
            osm_type=osm_type, osm_id=osm_id
        )
        if override.before is None:
            return None
        return await self._restore_before(
            osm_type=osm_type, osm_id=osm_id, before=override.before
        )

    async def suppress_feature(
        self, *, entity: str, osm_id: int, reason: str, user_id: str
    ) -> None:
        """Тумбстоун на объект слоя + удаление из живого поколения."""
        table, key_col = _SUPPRESSION_TARGETS[entity]
        generation = await GeoImportState.active_generation()
        _ = await GeoSuppression.upsert_by_object(
            GeoSuppression(
                entity=entity,
                osm_id=osm_id,
                reason=reason,
                updated_by=user_id,
                updated_at=datetime.now(UTC),
            )
        )
        _ = await execute_raw(
            f"DELETE FROM {table} WHERE generation = $1 AND {key_col} = $2",
            [generation, osm_id],
            using="geo",
        )

    async def unsuppress_feature(self, *, entity: str, osm_id: int) -> None:
        """Снятие тумбстоуна; объект вернётся со следующим поколением."""
        deleted = await GeoSuppression.delete_by_object(
            entity=entity, osm_id=osm_id
        )
        if deleted == 0:
            raise PlatformNotFoundError(
                f"geo suppression {entity}/{osm_id} not found",
                error_code="geo_suppression_not_found",
            )

    async def close_way(
        self,
        *,
        osm_way_id: int,
        modes: list[RouteMode],
        reason: str,
        user_id: str,
    ) -> None:
        """Закрытие режимов движения на way: оверлей + живой патч costs."""
        masks: JsonObject = {mode: True for mode in modes}
        _ = await GeoEdgeOverride.upsert_by_way(
            GeoEdgeOverride(
                osm_way_id=osm_way_id,
                cost_masks=masks,
                reason=reason,
                updated_by=user_id,
                updated_at=datetime.now(UTC),
            )
        )
        generation = await GeoImportState.active_generation()
        sets = ", ".join(f"{m}_cost = -1, {m}_reverse_cost = -1" for m in modes)
        _ = await execute_raw(
            f"UPDATE geo_road_edges SET {sets}"
            + " WHERE generation = $1 AND osm_way_id = $2",
            [generation, osm_way_id],
            using="geo",
        )

    async def open_way(self, *, osm_way_id: int) -> None:
        """Снятие закрытия way; стоимости вернутся со следующим импортом."""
        deleted = await GeoEdgeOverride.delete_by_way(osm_way_id=osm_way_id)
        if deleted == 0:
            raise PlatformNotFoundError(
                f"geo edge override {osm_way_id} not found",
                error_code="geo_edge_override_not_found",
            )

    async def overrides_page_desc(
        self, *, limit: int, offset: int
    ) -> GeoOverrideListResponse:
        """Сводный аудит: патчи адресов, тумбстоуны, закрытия дорог."""
        span = limit + offset + 1
        items: list[GeoOverrideItem] = []
        for override in await GeoAddressOverride.list_recent_desc(
            limit=span, offset=0
        ):
            items.append(
                GeoOverrideItem(
                    kind="tombstone" if override.suppressed else "patch",
                    entity="address",
                    osm_type=override.osm_type,
                    osm_id=override.osm_id,
                    reason=override.reason,
                    updated_by=override.updated_by,
                    updated_at=override.updated_at.isoformat(),
                    suppressed=override.suppressed,
                )
            )
        for sup in await GeoSuppression.list_recent_desc(limit=span, offset=0):
            items.append(
                GeoOverrideItem(
                    kind="tombstone",
                    entity=sup.entity,
                    osm_type=_SUPPRESSION_OSM_TYPE[sup.entity],
                    osm_id=sup.osm_id,
                    reason=sup.reason,
                    updated_by=sup.updated_by,
                    updated_at=sup.updated_at.isoformat(),
                    suppressed=True,
                )
            )
        for edge in await GeoEdgeOverride.list_recent_desc(limit=span, offset=0):
            items.append(
                GeoOverrideItem(
                    kind="edge_mask",
                    entity="edge",
                    osm_type="way",
                    osm_id=edge.osm_way_id,
                    reason=edge.reason,
                    updated_by=edge.updated_by,
                    updated_at=edge.updated_at.isoformat(),
                )
            )
        items.sort(key=lambda item: item.updated_at, reverse=True)
        total = await GeoAddressOverride.count_overrides()
        return GeoOverrideListResponse(
            items=items[offset : offset + limit], total=total
        )

    async def _live_row(
        self, osm_type: str, osm_id: int
    ) -> dict[str, SqlParameterValue]:
        """Живая строка адреса: manual (gen0) или активное поколение."""
        generation = await GeoImportState.active_generation()
        rows: list[dict[str, SqlParameterValue]] = await execute_raw(
            """
            SELECT id, osm_type, osm_id, display_name, city, street,
                   housenumber, postcode, lat, lng, region, generation
            FROM geo_addresses
            WHERE osm_type = $1 AND osm_id = $2 AND generation IN (0, $3)
            """,
            [osm_type, osm_id, generation],
            using="geo",
        )
        if not rows:
            raise PlatformNotFoundError(
                f"geo address {osm_type}/{osm_id} not found",
                error_code="geo_address_not_found",
            )
        return rows[0]

    @staticmethod
    def _before_snapshot(row: dict[str, SqlParameterValue]) -> JsonObject:
        """Снапшот исходных значений до первой правки админа."""
        snapshot: JsonObject = {}
        for field in (
            "display_name",
            "city",
            "street",
            "housenumber",
            "postcode",
            "region",
        ):
            snapshot[field] = str(row[field])
        snapshot["lat"] = float(str(row["lat"]))
        snapshot["lng"] = float(str(row["lng"]))
        return snapshot

    async def _apply_live_patch(
        self, row_id: int, patch: dict[str, SqlParameterValue]
    ) -> None:
        """Динамический UPDATE живой строки по непустым полям патча."""
        sets = ", ".join(f"{f} = ${i + 2}" for i, f in enumerate(patch))
        _ = await execute_raw(
            f"UPDATE geo_addresses SET {sets} WHERE id = $1",
            [row_id, *patch.values()],
            using="geo",
        )

    async def _restore_before(
        self, *, osm_type: str, osm_id: int, before: JsonObject
    ) -> GeoAddressHit | None:
        """Возврат source-truth в живое поколение по снапшоту ``before``."""
        generation = await GeoImportState.active_generation()
        existing: list[dict[str, SqlParameterValue]] = await execute_raw(
            """
            SELECT id FROM geo_addresses
            WHERE osm_type = $1 AND osm_id = $2 AND generation IN (0, $3)
            """,
            [osm_type, osm_id, generation],
            using="geo",
        )
        cols = (
            "display_name", "city", "street", "housenumber",
            "postcode", "lat", "lng", "region",
        )
        values = {f: _json_scalar(before.get(f), f) for f in cols}
        if existing:
            sets = ", ".join(f"{f} = ${i + 2}" for i, f in enumerate(cols))
            _ = await execute_raw(
                f"UPDATE geo_addresses SET {sets} WHERE id = $1",
                [existing[0]["id"], *[values[f] for f in cols]],
                using="geo",
            )
            row_id = int(str(existing[0]["id"]))
        else:
            rows: list[dict[str, SqlParameterValue]] = await execute_raw(
                """
                INSERT INTO geo_addresses
                    (osm_type, osm_id, display_name, city, street, housenumber,
                     postcode, lat, lng, region, generation, source, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, 'osm', $12)
                RETURNING id
                """,
                [
                    osm_type,
                    osm_id,
                    values["display_name"],
                    values["city"],
                    values["street"],
                    values["housenumber"],
                    values["postcode"],
                    values["lat"],
                    values["lng"],
                    values["region"],
                    generation,
                    datetime.now(UTC),
                ],
                using="geo",
            )
            row_id = int(str(rows[0]["id"]))
        return GeoAddressHit.model_validate(
            {
                "id": row_id,
                "osm_type": osm_type,
                "osm_id": osm_id,
                **{f: values[f] for f in self._HIT_FIELDS if f in values},
            }
        )

    @staticmethod
    async def _bump_manual_stats(region: str) -> None:
        """Счётчик manual-адресов региона в geo_stats поколения 0."""
        rows: list[dict[str, SqlParameterValue]] = await execute_raw(
            "SELECT count(*)::bigint AS c FROM geo_addresses"
            + " WHERE generation = 0 AND source = 'manual' AND region = $1",
            [region],
            using="geo",
        )
        await GeoStats.set_rows(
            generation=0,
            source="manual",
            region=region,
            entity="addresses",
            rows=int(str(rows[0]["c"])),
        )

    _HIT_FIELDS: tuple[str, ...] = (
        "id",
        "osm_type",
        "osm_id",
        "display_name",
        "city",
        "street",
        "housenumber",
        "postcode",
        "lat",
        "lng",
    )

    @classmethod
    def _hit(cls, row: dict[str, SqlParameterValue]) -> GeoAddressHit:
        """Строка geo_addresses → GeoAddressHit (extra-колонки отсекаем)."""
        return GeoAddressHit.model_validate(
            {f: row[f] for f in cls._HIT_FIELDS}
        )
