"""Реестр разрешённых источников геоданных (allowlist).

Таблица ``geo_sources`` (``__global_model__``): каждый источник несёт
лицензию и атрибуцию — обогащение разрешено только из открытых данных;
``enabled=False`` блокирует использование до подключения импортёра.
``_SEED_SOURCES`` — эталонный набор, сидится bootstrap'ом.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import execute_raw

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
    async def list_all(cls) -> list[Self]:
        """Все источники по имени."""
        return await cls.objects.order_by("name").all()

    @classmethod
    async def list_enabled(cls) -> list[Self]:
        """Источники, разрешённые к использованию."""
        return await cls.objects.filter(enabled=True).order_by("name").all()

    @classmethod
    async def insert_once(cls, instance: Self) -> bool:
        """Вставка при отсутствии по ``name``; ``True`` — строка создана."""
        rows = await execute_raw(
            """
            INSERT INTO geo_sources
                (name, title, kind, license, attribution, url, enabled,
                 created_at, updated_at)
            VALUES ($1, $2, $3::geo_source_kind_enum, $4, $5, $6, $7, $8, $8)
            ON CONFLICT (name) DO NOTHING
            RETURNING id
            """,
            [
                instance.name,
                instance.title,
                instance.kind.value,
                instance.license,
                instance.attribution,
                instance.url,
                instance.enabled,
                datetime.now(UTC),
            ],
            using="geo",
        )
        return len(rows) > 0


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
        False,
    ),
    (
        "data_mos_ru",
        "Портал открытых данных Москвы",
        GeoSourceKind.API,
        "Открытые данные Москвы",
        "Портал открытых данных Правительства Москвы",
        "https://data.mos.ru",
        False,
    ),
    (
        "nspd",
        "НСПД — сведения ЕГРН",
        GeoSourceKind.API,
        "Общедоступные сведения ЕГРН",
        "Росреестр, НСПД",
        "https://nspd.gov.ru",
        False,
    ),
    (
        "overture",
        "Overture Maps Foundation",
        GeoSourceKind.EXTRACT,
        "CDLA-Permissive 2.0 / ODbL (buildings)",
        "Overture Maps Foundation",
        "https://overturemaps.org",
        False,
    ),
    (
        "gar",
        "ГАР / ФИАС (ФНС)",
        GeoSourceKind.REGISTRY,
        "Открытые данные ФНС",
        "ФНС России, ГАР",
        "https://fias.nalog.ru",
        False,
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
