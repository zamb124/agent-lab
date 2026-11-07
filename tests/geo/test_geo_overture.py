"""Geo: импортёр Overture — parquet row-groups, bbox-фильтр, gap-fill.

Реальный путь: parquet-файлы в ``file://`` раскладке
``{release}/theme={theme}/type={type}/`` (как у Azure-mirror), реальный
Postgres. Тик читает row-groups с resume-курсором; адресные строки —
gap-fill gen-0 ``osm_type='overture'`` с дедупом ``ST_DWithin``, здания —
``geo_buildings`` upsert по GERS id.
"""

from __future__ import annotations

import struct
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from oxyde import execute_raw

from apps.geo.config import GeoSettings
from apps.geo.models.geo_building import GeoBuilding
from apps.geo.models.geo_import_state import GeoImportState
from apps.geo.models.geo_region import GeoRegion, GeoRegionKind
from apps.geo.models.geo_source import GeoSource, GeoSourceKind
from apps.geo.models.geo_source_cursor import GeoCursorStatus, GeoSourceCursor
from apps.geo.models.geo_stats import GeoStats
from apps.geo.services.overture_import_service import OvertureImportService
from core.types import SqlParameterValue

_GEN = 990_000_030
_REGION = "moscow"
_RELEASE = "2025-11-19.0"

pytestmark = pytest.mark.xdist_group("geo")


def _wkb_point(lng: float, lat: float) -> bytes:
    """Little-endian WKB Point (то же, что пишет Overture в geometry)."""
    return struct.pack("<BIdd", 1, 1, lng, lat)


def _wkb_polygon(ring: list[tuple[float, float]]) -> bytes:
    """Little-endian WKB Polygon, одно кольцо."""
    head = struct.pack("<BII", 1, 3, 1) + struct.pack("<I", len(ring))
    return head + b"".join(
        struct.pack("<dd", lng, lat) for lng, lat in ring
    )


def _write_fixture(root: Path) -> None:
    """Мини-релиз: 3 адреса (дубль/gap/вне bbox) + 1 здание."""
    bbox_t = pa.struct(
        [
            ("xmin", pa.float32()),
            ("xmax", pa.float32()),
            ("ymin", pa.float32()),
            ("ymin_", pa.float32()),
        ]
    )
    _ = bbox_t
    address_rows = [
        {
            "id": "a1dup0000000000000000000000dup",
            "xmin": 37.612, "xmax": 37.612, "ymin": 55.760, "ymax": 55.760,
            "geometry": _wkb_point(37.612, 55.760),
            "number": "1", "street": "Тверская улица",
            "postcode": "125009", "city": "Москва",
        },
        {
            "id": "a2gap0000000000000000000000gap",
            "xmin": 37.650, "xmax": 37.650, "ymin": 55.770, "ymax": 55.770,
            "geometry": _wkb_point(37.650, 55.770),
            "number": "99", "street": "Оверчуровская улица",
            "postcode": "", "city": "Москва",
        },
        {
            "id": "a3far0000000000000000000000far",
            "xmin": 30.0, "xmax": 30.0, "ymin": 50.0, "ymax": 50.0,
            "geometry": _wkb_point(30.0, 50.0),
            "number": "5", "street": "Внеbbox",
            "postcode": "", "city": "СПб",
        },
    ]
    address_schema = pa.schema(
        [
            ("id", pa.string()),
            (
                "bbox",
                pa.struct(
                    [
                        ("xmin", pa.float32()),
                        ("xmax", pa.float32()),
                        ("ymin", pa.float32()),
                        ("ymax", pa.float32()),
                    ]
                ),
            ),
            ("geometry", pa.binary()),
            ("number", pa.string()),
            ("street", pa.string()),
            ("postcode", pa.string()),
            ("city", pa.string()),
        ]
    )
    addresses = pa.table(
        {
            "id": [r["id"] for r in address_rows],
            "bbox": [
                {
                    "xmin": r["xmin"], "xmax": r["xmax"],
                    "ymin": r["ymin"], "ymax": r["ymax"],
                }
                for r in address_rows
            ],
            "geometry": [r["geometry"] for r in address_rows],
            "number": [r["number"] for r in address_rows],
            "street": [r["street"] for r in address_rows],
            "postcode": [r["postcode"] for r in address_rows],
            "city": [r["city"] for r in address_rows],
        },
        schema=address_schema,
    )
    addr_dir = root / _RELEASE / "theme=addresses" / "type=address"
    addr_dir.mkdir(parents=True)
    pq.write_table(addresses, addr_dir / "part-0.parquet")
    ring = [
        (37.605, 55.755), (37.615, 55.755), (37.615, 55.765),
        (37.605, 55.765), (37.605, 55.755),
    ]
    building_schema = pa.schema(
        [
            ("id", pa.string()),
            (
                "bbox",
                pa.struct(
                    [
                        ("xmin", pa.float32()),
                        ("xmax", pa.float32()),
                        ("ymin", pa.float32()),
                        ("ymax", pa.float32()),
                    ]
                ),
            ),
            ("geometry", pa.binary()),
        ]
    )
    buildings = pa.table(
        {
            "id": ["b1gers00000000000000000000000b1"],
            "bbox": [
                {"xmin": 37.605, "xmax": 37.615, "ymin": 55.755, "ymax": 55.765}
            ],
            "geometry": [_wkb_polygon(ring)],
        },
        schema=building_schema,
    )
    bld_dir = root / _RELEASE / "theme=buildings" / "type=building"
    bld_dir.mkdir(parents=True)
    pq.write_table(buildings, bld_dir / "part-0.parquet")


@pytest.fixture(autouse=True)
def _test_generation(monkeypatch: pytest.MonkeyPatch):
    """Сервисы читают тестовое поколение, глобальная строка не трогается."""

    async def _gen(cls) -> int:  # noqa: ANN001 — сигнатуру диктует classmethod
        return _GEN

    monkeypatch.setattr(GeoImportState, "active_generation", classmethod(_gen))


@pytest.fixture(autouse=True)
async def _clean():
    """Адреса/здания-фикстуры, курсор, статистика и реестр overture — чисты."""
    _ = await execute_raw(
        "DELETE FROM geo_addresses WHERE (generation = $1 AND osm_id >= 9300)"
        " OR source = 'overture'",
        [_GEN],
        using="geo",
    )
    _ = await execute_raw(
        "DELETE FROM geo_buildings WHERE source = 'overture'", using="geo"
    )
    _ = await execute_raw(
        "DELETE FROM geo_source_cursors WHERE source = 'overture'", using="geo"
    )
    _ = await execute_raw(
        "DELETE FROM geo_stats WHERE source = 'overture'", using="geo"
    )
    _ = await execute_raw(
        "DELETE FROM geo_sources WHERE name = 'overture'", using="geo"
    )
    _ = await execute_raw(
        "DELETE FROM geo_regions WHERE name = $1", [_REGION], using="geo"
    )


@pytest.fixture
def fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "overture"
    _write_fixture(root)
    return root


@pytest.fixture
def settings(fixture_root: Path) -> GeoSettings:
    return GeoSettings(
        overture_base_url=f"file://{fixture_root}",
        overture_release=_RELEASE,
        overture_themes=["addresses", "buildings"],
    )


@pytest.fixture
def service(settings: GeoSettings) -> OvertureImportService:
    return OvertureImportService(settings)


@pytest.fixture
async def _region() -> None:
    """Регион moscow — delete+create: одноимённые регионы других файлов сьюта."""
    _ = await execute_raw(
        "DELETE FROM geo_regions WHERE name = $1", [_REGION], using="geo"
    )
    now = datetime.now(UTC)
    _ = await GeoRegion.objects.create(
        instance=GeoRegion(
            name=_REGION,
            title="Overture e2e",
            kind=GeoRegionKind.CITY,
            bbox_south=55.3,
            bbox_west=37.3,
            bbox_north=56.0,
            bbox_east=37.9,
            enabled=True,
            created_at=now,
            updated_at=now,
        )
    )


@pytest.fixture
async def _seed_addresses() -> None:
    """Существующий адрес-фикстура — дубль для gap-fill дедупа."""
    now = datetime.now(UTC)
    _ = await execute_raw(
        """
        INSERT INTO geo_addresses
            (osm_type, osm_id, display_name, city, street, housenumber,
             postcode, lat, lng, region, generation, source, gar_guid,
             canonical_name, cadastral_number, created_at)
        VALUES ('node', 9301, 'Тверская улица, 1', 'Москва', 'Тверская улица',
                '1', '', 55.760, 37.612, $1, $2, 'osm', '', '', '', $3)
        """,
        [_REGION, _GEN, now],
        using="geo",
    )


async def test_overture_gap_fill_and_buildings(
    service: OvertureImportService, _region: None, _seed_addresses: None
) -> None:
    result = await service.run_sync()
    region = result.regions[_REGION]
    assert region["status"] == "done"
    assert region["row_groups"] == 2
    # Дубль «Тверская 1» отсечён ST_DWithin-дедупом; gap «99» — вставлен.
    assert region["inserted"] == 2
    rows: list[dict[str, SqlParameterValue]] = await execute_raw(
        "SELECT osm_type, osm_id, street, housenumber, source, generation"
        " FROM geo_addresses WHERE source = 'overture'",
        using="geo",
    )
    assert len(rows) == 1
    assert rows[0]["osm_type"] == "overture"
    assert rows[0]["housenumber"] == "99"
    assert rows[0]["generation"] == 0
    assert int(str(rows[0]["osm_id"])) < 0
    building = await GeoBuilding.by_cadastral_number(
        cadastral_number="b1gers00000000000000000000000b1"
    )
    assert building is not None
    assert building.source == "overture"
    cursor = await GeoSourceCursor.by_source_region("overture", _REGION)
    assert cursor is not None
    assert cursor.status == GeoCursorStatus.DONE
    stats = await GeoStats.objects.filter(
        source="overture", region=_REGION, entity="addresses"
    ).all()
    assert stats[0].rows == 1


async def test_overture_resume_across_ticks(
    _region: None, _seed_addresses: None, fixture_root: Path
) -> None:
    service = OvertureImportService(
        GeoSettings(
            overture_base_url=f"file://{fixture_root}",
            overture_release=_RELEASE,
            overture_themes=["addresses", "buildings"],
            overture_tick_rowgroups=1,
        )
    )
    first = await service.run_sync()
    assert first.regions[_REGION]["status"] == "running"
    cursor = await GeoSourceCursor.by_source_region("overture", _REGION)
    assert cursor is not None
    assert cursor.status == GeoCursorStatus.RUNNING
    assert cursor.cursor == f"{_RELEASE}|0|0:1"
    # Тик 2 — buildings rg0 (бюджет 1 row-group) → снова running; тик 3 — done.
    second = await service.run_sync()
    assert second.regions[_REGION]["status"] == "running"
    third = await service.run_sync()
    assert third.regions[_REGION]["status"] == "done"


async def test_overture_release_change_resets_cursor(
    service: OvertureImportService, _region: None
) -> None:
    _ = await GeoSourceCursor.upsert_progress(
        source="overture",
        region=_REGION,
        cursor="1999-01-01.0|1|0:0",
        rows_done=0,
        status=GeoCursorStatus.RUNNING,
    )
    result = await service.run_sync()
    assert result.regions[_REGION]["status"] == "done"


async def test_overture_source_disabled_skips(
    service: OvertureImportService,
) -> None:
    now = datetime.now(UTC)
    _ = await GeoSource.objects.create(
        instance=GeoSource(
            name="overture",
            title="Overture",
            kind=GeoSourceKind.EXTRACT,
            enabled=False,
            created_at=now,
            updated_at=now,
        )
    )
    result = await service.run_sync()
    assert result.skipped == "source_disabled"


async def test_overture_sync_disabled_skips() -> None:
    service = OvertureImportService(GeoSettings(overture_sync_enabled=False))
    result = await service.run_sync()
    assert result.skipped == "overture_sync_disabled"
