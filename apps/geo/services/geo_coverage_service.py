"""Реестр покрытия: регионы, источники, статистика, курсоры, очередь обогащения.

``ensure_seeded`` — идемпотентный сид: дефолтный регион из настроек
(``coverage_bbox`` + ``osm_extract_urls``) и allowlist ``geo_sources``.
Вызывается bootstrap'ом воркера и ``run_sync`` до чтения регионов —
«пустая директория» платформы сама получает один регион покрытия.
"""

from __future__ import annotations

from datetime import UTC, datetime

from apps.geo.config import GeoSettings
from apps.geo.models.api import (
    GeoBbox,
    GeoCursorItem,
    GeoCursorListResponse,
    GeoEnrichItemResponse,
    GeoEnrichListResponse,
    GeoRegionItem,
    GeoRegionListResponse,
    GeoRegionUpsertRequest,
    GeoSourceItem,
    GeoSourceListResponse,
    GeoStatsOverview,
    GeoStatsRow,
)
from apps.geo.models.geo_enrich_item import GeoEnrichItem, GeoEnrichStatus
from apps.geo.models.geo_import_state import GeoImportState
from apps.geo.models.geo_region import GeoRegion, GeoRegionKind
from apps.geo.models.geo_source import SEED_SOURCES, GeoSource
from apps.geo.models.geo_source_cursor import GeoSourceCursor
from apps.geo.models.geo_stats import GeoStats
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError


class GeoCoverageError(Exception):
    """Ошибка ввода операций покрытия; ``code`` — platform error_code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code: str = code


class GeoCoverageService:
    """Управление реестром покрытия и его наблюдаемостью."""

    def __init__(self, settings: GeoSettings) -> None:
        self._settings: GeoSettings = settings

    async def ensure_seeded(self) -> None:
        """Сид дефолтного региона в пустой реестр и реестра источников.

        ``geo_regions`` сидится только когда пуст: после первого bootstrap'а
        источником истины становится таблица, а не настройки — правки региона
        через UI/REST не перезаписываются очередным тиком импорта.
        """
        lat_min, lng_min, lat_max, lng_max = self._settings.coverage_bbox
        now = datetime.now(UTC)
        if self._settings.osm_extract_urls and await GeoRegion.count_all() == 0:
            _ = await GeoRegion.insert_once(
                instance=GeoRegion(
                    name=self._settings.default_region_name,
                    title=self._settings.default_region_title,
                    kind=GeoRegionKind.CITY,
                    bbox_south=lat_min,
                    bbox_west=lng_min,
                    bbox_north=lat_max,
                    bbox_east=lng_max,
                    extract_urls=list(self._settings.osm_extract_urls),
                    enabled=True,
                    created_at=now,
                    updated_at=now,
                )
            )
        for name, title, kind, license_, attribution, url, enabled in SEED_SOURCES:
            _ = await GeoSource.insert_once(
                instance=GeoSource(
                    name=name,
                    title=title,
                    kind=kind,
                    license=license_,
                    attribution=attribution,
                    url=url,
                    enabled=enabled,
                    created_at=now,
                    updated_at=now,
                )
            )

    async def regions_response(self) -> GeoRegionListResponse:
        """Регионы со счётчиками данных активного поколения."""
        generation = await GeoImportState.active_generation()
        stats = await GeoStats.list_for_generation(generation)
        counts: dict[str, dict[str, int]] = {}
        for row in stats:
            counts.setdefault(row.region, {})[row.entity] = row.rows
        items = [
            self._region_item(region, counts.get(region.name, {}))
            for region in await GeoRegion.list_all()
        ]
        return GeoRegionListResponse(items=items, generation=generation)

    async def create_region(self, payload: GeoRegionUpsertRequest) -> GeoRegionItem:
        """Новый регион покрытия; конфликт по ``name``."""
        self._validate_bbox(payload)
        if await GeoRegion.by_name(payload.name) is not None:
            raise PlatformConflictError(
                f"geo region {payload.name!r} already exists",
                error_code="geo_region_exists",
            )
        now = datetime.now(UTC)
        region = await GeoRegion.objects.create(
            instance=GeoRegion(
                name=payload.name,
                title=payload.title,
                kind=GeoRegionKind(payload.kind),
                bbox_south=payload.bbox.south,
                bbox_west=payload.bbox.west,
                bbox_north=payload.bbox.north,
                bbox_east=payload.bbox.east,
                extract_urls=payload.extract_urls,
                replication_url=payload.replication_url,
                enabled=payload.enabled,
                created_at=now,
                updated_at=now,
            )
        )
        return self._region_item(region, {})

    async def update_region(self, payload: GeoRegionUpsertRequest) -> GeoRegionItem:
        """Полная замена полей региона по ``name``."""
        self._validate_bbox(payload)
        region = await self._require_region(payload.name)
        region.title = payload.title
        region.kind = GeoRegionKind(payload.kind)
        region.bbox_south = payload.bbox.south
        region.bbox_west = payload.bbox.west
        region.bbox_north = payload.bbox.north
        region.bbox_east = payload.bbox.east
        region.extract_urls = payload.extract_urls
        region.replication_url = payload.replication_url
        region.enabled = payload.enabled
        region.updated_at = datetime.now(UTC)
        _ = await region.save()
        stats = {
            row.entity: row.rows
            for row in await GeoStats.list_for_generation(
                await GeoImportState.active_generation()
            )
            if row.region == region.name
        }
        return self._region_item(region, stats)

    async def delete_region(self, name: str) -> None:
        """Удаление строки реестра; данные поколения трёт чистка импорта."""
        region = await self._require_region(name)
        assert region.id is not None
        _ = await GeoRegion.delete_by_pk(region.id)

    async def sources_response(self) -> GeoSourceListResponse:
        """Реестр источников с лицензиями."""
        items: list[GeoSourceItem] = []
        for source in await GeoSource.list_all():
            assert source.id is not None
            items.append(
                GeoSourceItem(
                    id=source.id,
                    name=source.name,
                    title=source.title,
                    kind=source.kind.value,
                    license=source.license,
                    attribution=source.attribution,
                    url=source.url,
                    enabled=source.enabled,
                )
            )
        return GeoSourceListResponse(items=items)

    async def stats_overview(self) -> GeoStatsOverview:
        """Сводка загруженных данных активного поколения."""
        generation = await GeoImportState.active_generation()
        stats = await GeoStats.list_for_generation(generation)
        totals: dict[str, int] = {}
        for row in stats:
            totals[row.entity] = totals.get(row.entity, 0) + row.rows
        return GeoStatsOverview(
            generation=generation,
            rows=[
                GeoStatsRow(
                    source=row.source,
                    region=row.region,
                    entity=row.entity,
                    rows=row.rows,
                )
                for row in stats
            ],
            totals=totals,
        )

    async def cursors_response(self) -> GeoCursorListResponse:
        """Позиции чанковых потоков источников."""
        items = [
            GeoCursorItem(
                source=cursor.source,
                region=cursor.region,
                cursor=cursor.cursor,
                status=cursor.status.value,
                rows_done=cursor.rows_done,
                last_error=cursor.last_error,
                updated_at=cursor.updated_at.isoformat(),
            )
            for cursor in await GeoSourceCursor.list_all()
        ]
        return GeoCursorListResponse(items=items)

    async def enrich_list_response(
        self,
        *,
        status: GeoEnrichStatus | None,
        limit: int,
        offset: int,
    ) -> GeoEnrichListResponse:
        """Страница очереди обогащения по приоритету."""
        items = await GeoEnrichItem.list_by_priority_desc(
            status=status, limit=limit, offset=offset
        )
        pending = await GeoEnrichItem.count_for_status(GeoEnrichStatus.PENDING)
        out: list[GeoEnrichItemResponse] = []
        for item in items:
            assert item.id is not None
            out.append(
                GeoEnrichItemResponse(
                    id=item.id,
                    kind=item.kind,
                    payload=item.payload,
                    priority=item.priority,
                    status=item.status.value,
                    attempts=item.attempts,
                    last_error=item.last_error,
                    created_at=item.created_at.isoformat(),
                    done_at=item.done_at.isoformat() if item.done_at else None,
                )
            )
        return GeoEnrichListResponse(items=out, pending=pending)

    async def _require_region(self, name: str) -> GeoRegion:
        region = await GeoRegion.by_name(name)
        if region is None:
            raise PlatformNotFoundError(
                f"geo region {name!r} not found", error_code="geo_region_not_found"
            )
        return region

    @staticmethod
    def _validate_bbox(payload: GeoRegionUpsertRequest) -> None:
        bbox = payload.bbox
        if bbox.south >= bbox.north or bbox.west >= bbox.east:
            raise GeoCoverageError(
                "geo_bbox_invalid",
                f"invalid bbox {bbox.south},{bbox.west},{bbox.north},{bbox.east}",
            )

    @staticmethod
    def _region_item(
        region: GeoRegion, stats: dict[str, int]
    ) -> GeoRegionItem:
        assert region.id is not None
        return GeoRegionItem(
            id=region.id,
            name=region.name,
            title=region.title,
            kind=region.kind.value,
            bbox=GeoBbox(
                south=region.bbox_south,
                west=region.bbox_west,
                north=region.bbox_north,
                east=region.bbox_east,
            ),
            extract_urls=region.extract_urls,
            replication_url=region.replication_url,
            enabled=region.enabled,
            last_imported_at=(
                region.last_imported_at.isoformat()
                if region.last_imported_at
                else None
            ),
            addresses=stats.get("addresses", 0),
            vertices=stats.get("vertices", 0),
            edges=stats.get("edges", 0),
        )
