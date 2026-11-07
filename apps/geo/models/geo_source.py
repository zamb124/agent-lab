"""Реестр разрешённых источников геоданных (allowlist).

Таблица ``geo_sources`` (``__global_model__``): каждый источник несёт
лицензию и атрибуцию — обогащение разрешено только из открытых данных;
``enabled=False`` блокирует использование до подключения импортёра.
``_SEED_SOURCES`` — эталонный набор, сидится bootstrap'ом.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import ClassVar, Self

from oxyde import Field as DbField

from core.models.platform_model import PlatformModel


class GeoSourceKind(StrEnum):
    """Тип доступа источника."""

    EXTRACT = "extract"
    API = "api"
    REGISTRY = "registry"
    TELEMETRY = "telemetry"
    MANUAL = "manual"


class GeoSource(PlatformModel):
    """Строка allowlist-реестра источников."""

    __database_alias__: ClassVar[str | None] = "geo"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "geo_sources"

    id: int | None = DbField(default=None, db_pk=True)
    name: str = DbField(max_length=64, unique=True)
    title: str = DbField(default="", max_length=255)
    kind: GeoSourceKind = DbField(default=GeoSourceKind.EXTRACT, max_length=32)
    license: str = DbField(default="", max_length=255)
    attribution: str = DbField(default="", db_type="TEXT")
    url: str = DbField(default="", db_type="TEXT")
    enabled: bool = DbField(default=True)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def by_name(cls, name: str) -> Self | None:
        """Источник по slug-имени; ``None`` при отсутствии."""
        return await cls.objects.filter(name=name).first()

    @classmethod
    async def list_all_by_name_asc(cls) -> list[Self]:
        """Все источники по имени."""
        return await cls.objects.order_by("name").all()

    @classmethod
    async def list_enabled_by_name_asc(cls) -> list[Self]:
        """Источники, разрешённые к использованию."""
        return await cls.objects.filter(enabled=True).order_by("name").all()

    @classmethod
    async def upsert_by_name(cls, instance: Self) -> Self:
        """Merge по ``name``: эталонный seed перезаписывает все поля.

        ``enabled`` — тоже эталон: флаг флипается правкой SEED_SOURCES при
        готовности импортёра, а не руками в БД (ручной флаг перезатрётся).
        """
        existing = await cls.by_name(instance.name)
        if existing is None:
            return await cls.objects.create(instance=instance)
        existing.title = instance.title
        existing.kind = instance.kind
        existing.license = instance.license
        existing.attribution = instance.attribution
        existing.url = instance.url
        existing.enabled = instance.enabled
        existing.updated_at = instance.updated_at
        _ = await existing.save()
        return existing


SEED_SOURCES: tuple[tuple[str, str, GeoSourceKind, str, str, str, bool], ...] = (
    # name, title, kind, license, attribution, url, enabled
    (
        "osm",
        "OpenStreetMap",
        GeoSourceKind.EXTRACT,
        "ODbL 1.0",
        "© OpenStreetMap contributors",
        "https://www.openstreetmap.org",
        True,
    ),
    (
        "geofabrik",
        "Geofabrik daily diffs",
        GeoSourceKind.EXTRACT,
        "ODbL 1.0",
        "© OpenStreetMap contributors",
        "https://download.geofabrik.de",
        True,
    ),
    (
        "data_mos_ru",
        "Портал открытых данных Москвы",
        GeoSourceKind.API,
        "Открытые данные Москвы",
        "Портал открытых данных Правительства Москвы",
        "https://data.mos.ru",
        True,
    ),
    (
        "nspd",
        "НСПД — сведения ЕГРН",
        GeoSourceKind.API,
        "Общедоступные сведения ЕГРН",
        "Росреестр, НСПД",
        "https://nspd.gov.ru",
        True,
    ),
    (
        "overture",
        "Overture Maps Foundation",
        GeoSourceKind.EXTRACT,
        "CDLA-Permissive 2.0 / ODbL (buildings)",
        "Overture Maps Foundation",
        "https://overturemaps.org",
        True,
    ),
    (
        "gar",
        "ГАР / ФИАС (ФНС)",
        GeoSourceKind.REGISTRY,
        "Открытые данные ФНС",
        "ФНС России, ГАР",
        "https://fias.nalog.ru",
        True,
    ),
    (
        "manual",
        "Ручной ввод оператора",
        GeoSourceKind.MANUAL,
        "internal",
        "",
        "",
        True,
    ),
)
