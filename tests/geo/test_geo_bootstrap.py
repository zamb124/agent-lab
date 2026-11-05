"""Bootstrap и регулярный resync OSM-импорта geo.

Прод-цепочка без моков и манкипатчей:

- ``ensure_bootstrapped`` и lifecycle-рецепт ``ensure_import_bootstrapped``
  (та самая функция, что зовёт ``geo_worker`` при старте) → ``enqueue`` в
  реальный Redis-стрим → живой ``geo_worker`` стека (env
  ``OSM_EXTRACT_URLS=file://micro.osm``) → ``run_sync`` → атомарный publish.
- ``run_sync`` in-process — тот же код, что вызывает ``@platform_task``:
  ``file://`` ``.osm``/``.osm.pbf``, ``http://`` через эмулятор зеркала
  на 18099 (реальные HEAD/GET + ``Last-Modified``), If-Modified-Since,
  ошибки источника, очистка поколений, мульти-батч.
- Регистрация ``GEO_OSM_SYNC_TICK`` на брокере очереди ``geo``.

Весь модуль — ``xdist_group("geo")``: синглтон ``geo_import_state``
и поколения общие с ``test_geo_services`` и shop ETA-тестами.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from oxyde import execute_raw

from apps.geo.config import GeoSettings
from apps.geo.models.api import GeoBbox, GeoRegionUpsertRequest
from apps.geo.models.geo_enrich_item import GeoEnrichItem
from apps.geo.models.geo_import_state import GeoImportState, GeoImportStatus
from apps.geo.models.geo_region import GeoRegion, GeoRegionKind
from apps.geo.models.geo_source_cursor import GeoCursorStatus, GeoSourceCursor
from apps.geo.models.geo_stats import GeoStats
from apps.geo.services.geo_coverage_service import (
    GeoCoverageError,
    GeoCoverageService,
)
from apps.geo.services.geo_layer_service import GeoLayerService
from apps.geo.services.osm_import_service import OsmImportService
from apps.geo.tasks.task_names import GEO_OSM_SYNC_TICK
from apps.geo.worker import ensure_import_bootstrapped
from apps.scheduler.dispatch import require_scheduled_tasks_registered
from apps.worker_manifest import wire_all
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.tasks import enqueue
from core.tasks.registry import registered_queue_brokers, scheduled_task_specs

_MICRO = Path(__file__).parent / "fixtures" / "micro.osm"
_MICRO_PBF = Path(__file__).parent / "fixtures" / "micro.osm.pbf"
_EMU_URL = "http://127.0.0.1:18099/extracts/micro.osm.pbf"
_EMU_NO_LM_URL = "http://127.0.0.1:18099/extracts/no-last-modified.osm.pbf"

pytestmark = pytest.mark.xdist_group("geo")

# Поколения ниже порога — продукт импортов (тестовые сиды живут выше:
# 880M ETA-граф, 990M — test_geo_services). Чистка даёт каждому тесту
# детерминированную «пустую директорию», не трогая сиды.
_SEED_FLOOR = 500_000_000


def _import_svc(settings: GeoSettings) -> OsmImportService:
    """Прод-конструктор импортёра: настройки + реестр покрытия."""
    return OsmImportService(settings, GeoCoverageService(settings))


@pytest.fixture(autouse=True)
async def _clean_import_generations() -> None:
    for table in (
        "geo_addresses",
        "geo_road_vertices",
        "geo_road_edges",
        "geo_turn_restrictions",
        "geo_barriers",
        "geo_traffic_signals",
    ):
        _ = await execute_raw(
            f"DELETE FROM {table} WHERE generation < $1",
            [_SEED_FLOOR],
            using="geo",
        )
    for table in (
        "geo_regions",
        "geo_stats",
        "geo_source_cursors",
        "geo_enrich_queue",
    ):
        _ = await execute_raw(f"DELETE FROM {table}", using="geo")


async def _set_state(
    *,
    generation: int,
    source_modified_at: datetime | None = None,
    status: GeoImportStatus = GeoImportStatus.IDLE,
) -> None:
    """Синглтон в известное состояние (создаёт строку при холодном старте)."""
    state = await GeoImportState.get_state()
    if state is None:
        state = await GeoImportState.objects.create(
            instance=GeoImportState(id=1, updated_at=datetime.now(UTC))
        )
    state.current_generation = generation
    state.status = status
    state.source_modified_at = source_modified_at
    state.last_error = ""
    state.updated_at = datetime.now(UTC)
    _ = await state.save()


async def _state() -> GeoImportState:
    state = await GeoImportState.get_state()
    assert state is not None
    return state


async def _count(table: str, generation: int) -> int:
    rows = await execute_raw(
        f"SELECT count(*) AS c FROM {table} WHERE generation = $1",
        [generation],
        using="geo",
    )
    return cast(int, rows[0]["c"])


async def _wait_generation_at_least(
    target: int, *, timeout: float = 90.0
) -> GeoImportState:
    """Поллинг публикации поколения живым воркером; FAILED — фейл сразу."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = await GeoImportState.get_state()
        if state is not None:
            if state.status == GeoImportStatus.FAILED:
                pytest.fail(f"geo импорт упал на воркере: {state.last_error}")
            if (
                state.current_generation >= target
                and state.status == GeoImportStatus.IDLE
            ):
                return state
        await asyncio.sleep(0.25)
    pytest.fail(
        f"geo_worker не опубликовал поколение >= {target} за {timeout:.0f}s",
        pytrace=False,
    )


async def _snapshot_state() -> tuple[int, datetime | None]:
    state = await _state()
    return state.current_generation, state.source_modified_at


async def _restore_state(snapshot: tuple[int, datetime | None]) -> None:
    """Указатель на живое поколение: сохранённое, а если его строки уже
    удалены новым publish — на свежее присутствующее (как в проде после
    очередного импорта)."""
    gen, modified = snapshot
    rows = await execute_raw(
        """
        SELECT max(generation) AS m FROM (
            SELECT generation FROM geo_addresses
            UNION ALL SELECT generation FROM geo_road_edges
        ) t
        """,
        using="geo",
    )
    max_present = cast(int, rows[0]["m"]) or 0
    live = await _count("geo_addresses", gen) + await _count(
        "geo_road_edges", gen
    )
    await _set_state(
        generation=gen if live > 0 else max_present,
        source_modified_at=modified,
    )


def _osm_with_addresses(count: int, *, base_lat: float = 55.75) -> str:
    """XML-экстракт с ``count`` адресных нод (генерация в тесте, не фикстура)."""
    node_tpl = (
        '<node id="{id}" lat="{lat:.5f}" lon="37.61700">'
        + '<tag k="addr:city" v="Москва"/><tag k="addr:street" v="Тестовая"/>'
        + '<tag k="addr:housenumber" v="{num}"/></node>'
    )
    nodes = "\n".join(
        node_tpl.format(id=10_000 + i, lat=base_lat + i * 0.0001, num=i + 1)
        for i in range(count)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<osm version="0.6" generator="geo-test">\n'
        f"{nodes}\n</osm>\n"
    )


class TestEnsureBootstrapped:
    """Пустой справочник → первый импорт стартует немедленно, без cron-тика."""

    async def test_empty_directory_fires_import_via_real_worker(
        self, geo_worker: None
    ) -> None:
        """Lifecycle воркера: поколение 0 → enqueue → живой импорт → publish."""
        _ = geo_worker
        await _set_state(generation=0, source_modified_at=None)
        svc = _import_svc(GeoSettings())
        # Сама рецепт-функция из worker.py — ровно то, что зовёт startup.
        await ensure_import_bootstrapped(svc)

        state = await _wait_generation_at_least(1)
        # Воркер импортировал micro.osm из своего env — полный прод-парс.
        assert state.rows_addresses == 4
        assert state.rows_vertices == 8
        assert state.rows_edges == 9
        assert state.rows_restrictions == 2
        assert state.rows_barriers == 1
        assert state.rows_signals == 1
        assert state.source_modified_at is not None
        assert state.last_error == ""
        gen = state.current_generation
        assert await _count("geo_addresses", gen) == 4
        assert await _count("geo_road_vertices", gen) == 8
        assert await _count("geo_road_edges", gen) == 9

    async def test_no_state_row_also_bootstraps(self, geo_worker: None) -> None:
        """Холодный старт до первой строки state: строка создаётся, тик уходит."""
        _ = geo_worker
        snapshot = await _snapshot_state()
        _ = await execute_raw("DELETE FROM geo_import_state WHERE id = 1", using="geo")
        try:
            svc = _import_svc(GeoSettings())
            assert await svc.ensure_bootstrapped() is True
            state = await _wait_generation_at_least(1)
            assert state.rows_addresses == 4
        finally:
            await _restore_state(snapshot)

    async def test_noop_when_generation_published(self, geo_service: None) -> None:
        """Справочник уже наполнен — bootstrap не ставит лишний тик."""
        _ = geo_service
        snapshot = await _snapshot_state()
        try:
            await _set_state(generation=max(snapshot[0], 5))
            svc = _import_svc(GeoSettings())
            assert await svc.ensure_bootstrapped() is False
            # Состояние не тронуто — enqueue не произошёл.
            assert (await _state()).current_generation == max(snapshot[0], 5)
        finally:
            await _restore_state(snapshot)

    async def test_noop_when_disabled_or_no_sources(
        self, geo_service: None
    ) -> None:
        """sync_enabled=False и пустой список источников — тихий no-op."""
        _ = geo_service
        snapshot = await _snapshot_state()
        try:
            await _set_state(generation=0, source_modified_at=None)
            disabled = _import_svc(GeoSettings(sync_enabled=False))
            no_urls = _import_svc(GeoSettings(osm_extract_urls=[]))
            assert await disabled.ensure_bootstrapped() is False
            assert await no_urls.ensure_bootstrapped() is False
            assert (await _state()).current_generation == 0
        finally:
            await _restore_state(snapshot)


class TestRunSyncFile:
    """``run_sync`` in-process — тот же код, что исполняет таск на воркере."""

    async def test_file_import_publishes_and_preserves_source(
        self, geo_service: None, tmp_path: Path
    ) -> None:
        """file:// .osm → publish; источник на диске не удаляется."""
        _ = geo_service
        snapshot = await _snapshot_state()
        src = tmp_path / "extract.osm"
        _ = src.write_bytes(_MICRO.read_bytes())
        try:
            await _set_state(generation=0, source_modified_at=None)
            svc = _import_svc(
                GeoSettings(osm_extract_urls=[f"file://{src}"])
            )
            result = await svc.run_sync()
            assert result["imported"] is True
            assert result["rows_addresses"] == 4
            assert result["rows_vertices"] == 8
            assert result["rows_edges"] == 9
            assert result["rows_restrictions"] == 2
            assert result["rows_barriers"] == 1
            assert result["rows_signals"] == 1
            assert src.is_file()

            state = await _state()
            assert state.current_generation == 1
            assert state.status == GeoImportStatus.IDLE
            assert state.source_modified_at is not None
            assert state.finished_at is not None
            assert state.last_error == ""
        finally:
            await _restore_state(snapshot)

    async def test_pbf_file_import_same_counts(self, geo_service: None) -> None:
        """file:// .osm.pbf — бинарный формат парсится тем же конвейером."""
        _ = geo_service
        snapshot = await _snapshot_state()
        try:
            await _set_state(generation=0, source_modified_at=None)
            svc = _import_svc(
                GeoSettings(osm_extract_urls=[f"file://{_MICRO_PBF}"])
            )
            result = await svc.run_sync()
            assert result["imported"] is True
            assert result["rows_addresses"] == 4
            assert result["rows_edges"] == 9
            assert result["rows_restrictions"] == 2
            assert result["rows_barriers"] == 1
            assert result["rows_signals"] == 1
            assert _MICRO_PBF.is_file()
        finally:
            await _restore_state(snapshot)

    async def test_second_run_not_modified(self, geo_service: None) -> None:
        """Та же mtime → If-Modified-Since → skip без нового поколения."""
        _ = geo_service
        snapshot = await _snapshot_state()
        try:
            await _set_state(generation=0, source_modified_at=None)
            svc = _import_svc(
                GeoSettings(osm_extract_urls=[f"file://{_MICRO}"])
            )
            first = await svc.run_sync()
            assert first["imported"] is True
            second = await svc.run_sync()
            assert second == {"skipped": True, "reason": "not_modified"}
            assert (await _state()).current_generation == 1
        finally:
            await _restore_state(snapshot)

    async def test_reimport_on_newer_source_and_cleanup(
        self, geo_service: None, tmp_path: Path
    ) -> None:
        """mtime вырос → переимпорт; строки старого поколения удалены."""
        _ = geo_service
        snapshot = await _snapshot_state()
        src = tmp_path / "extract.osm"
        _ = src.write_bytes(_MICRO.read_bytes())
        try:
            await _set_state(generation=0, source_modified_at=None)
            svc = _import_svc(
                GeoSettings(osm_extract_urls=[f"file://{src}"])
            )
            _ = await svc.run_sync()
            gen_old = (await _state()).current_generation

            future = datetime.now(UTC).timestamp() + 10
            src.touch()
            os.utime(src, (future, future))
            _ = await svc.run_sync()

            state = await _state()
            gen_new = state.current_generation
            assert gen_new == gen_old + 1
            assert await _count("geo_addresses", gen_new) == 4
            assert await _count("geo_addresses", gen_old) == 0
            assert await _count("geo_road_edges", gen_old) == 0
        finally:
            await _restore_state(snapshot)

    async def test_failure_preserves_published_generation(
        self, geo_service: None, tmp_path: Path
    ) -> None:
        """Источник исчез → FAILED + last_error; старое поколение обслуживает."""
        _ = geo_service
        snapshot = await _snapshot_state()
        src = tmp_path / "extract.osm"
        _ = src.write_bytes(_MICRO.read_bytes())
        try:
            await _set_state(generation=0, source_modified_at=None)
            svc = _import_svc(
                GeoSettings(osm_extract_urls=[f"file://{src}"])
            )
            _ = await svc.run_sync()
            gen_live = (await _state()).current_generation
            assert await _count("geo_addresses", gen_live) == 4

            src.unlink()
            with pytest.raises(OSError):
                _ = await svc.run_sync()

            state = await _state()
            assert state.status == GeoImportStatus.FAILED
            assert state.last_error != ""
            assert state.current_generation == gen_live
            # Опубликованные данные не пострадали — geo продолжает отвечать.
            assert await _count("geo_addresses", gen_live) == 4
            assert await _count("geo_road_edges", gen_live) == 9
        finally:
            await _restore_state(snapshot)

    async def test_malformed_osm_fails_and_preserves_generation(
        self, geo_service: None, tmp_path: Path
    ) -> None:
        """Битый XML → pyosmium-ошибка → FAILED, поколение не двигается."""
        _ = geo_service
        snapshot = await _snapshot_state()
        bad = tmp_path / "broken.osm"
        _ = bad.write_text("<osm><node", encoding="utf-8")
        try:
            await _set_state(generation=7, source_modified_at=None)
            svc = _import_svc(
                GeoSettings(osm_extract_urls=[f"file://{bad}"])
            )
            with pytest.raises(Exception):
                _ = await svc.run_sync()
            state = await _state()
            assert state.status == GeoImportStatus.FAILED
            assert state.current_generation == 7
        finally:
            await _restore_state(snapshot)

    async def test_empty_extract_publishes_empty_generation(
        self, geo_service: None, tmp_path: Path
    ) -> None:
        """Валидный, но пустой экстракт → нулевые счётчики, publish честный."""
        _ = geo_service
        snapshot = await _snapshot_state()
        empty = tmp_path / "empty.osm"
        _ = empty.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>'
            + '<osm version="0.6" generator="t"/>',
            encoding="utf-8",
        )
        try:
            await _set_state(generation=0, source_modified_at=None)
            svc = _import_svc(
                GeoSettings(osm_extract_urls=[f"file://{empty}"])
            )
            result = await svc.run_sync()
            assert result["imported"] is True
            assert result["rows_addresses"] == 0
            state = await _state()
            assert state.current_generation == 1
            assert state.rows_addresses == 0
        finally:
            await _restore_state(snapshot)

    async def test_multi_batch_import(self, geo_service: None, tmp_path: Path) -> None:
        """import_batch_size < числа строк → цикл батчей, все строки на месте."""
        _ = geo_service
        snapshot = await _snapshot_state()
        big = tmp_path / "many.osm"
        _ = big.write_text(_osm_with_addresses(150), encoding="utf-8")
        try:
            await _set_state(generation=0, source_modified_at=None)
            svc = _import_svc(
                GeoSettings(
                    osm_extract_urls=[f"file://{big}"],
                    import_batch_size=100,
                )
            )
            result = await svc.run_sync()
            assert result["imported"] is True
            assert result["rows_addresses"] == 150
            gen = (await _state()).current_generation
            assert await _count("geo_addresses", gen) == 150
        finally:
            await _restore_state(snapshot)

    async def test_retry_into_same_generation_no_duplicates(
        self, geo_service: None
    ) -> None:
        """Retry задачи в то же поколение: ON CONFLICT, строк не дублирует."""
        _ = geo_service
        snapshot = await _snapshot_state()
        try:
            await _set_state(generation=0, source_modified_at=None)
            svc = _import_svc(
                GeoSettings(osm_extract_urls=[f"file://{_MICRO}"])
            )
            _ = await svc.run_sync()
            gen = (await _state()).current_generation

            # Воркер убит после публикации? Откат указателя → тот же gen.
            await _set_state(generation=gen - 1, source_modified_at=None)
            _ = await svc.run_sync()

            assert await _count("geo_addresses", gen) == 4
            assert await _count("geo_road_vertices", gen) == 8
            assert await _count("geo_road_edges", gen) == 9
        finally:
            await _restore_state(snapshot)

    async def test_sync_disabled_noop(self, geo_service: None) -> None:
        """sync_enabled=False → skip, состояние и данные не тронуты."""
        _ = geo_service
        snapshot = await _snapshot_state()
        try:
            await _set_state(generation=3, source_modified_at=None)
            svc = _import_svc(GeoSettings(sync_enabled=False))
            result = await svc.run_sync()
            assert result == {"skipped": True, "reason": "sync_disabled"}
            state = await _state()
            assert state.current_generation == 3
            assert state.status == GeoImportStatus.IDLE
        finally:
            await _restore_state(snapshot)


class TestRunSyncHttp:
    """http://-источник: реальный HEAD/GET против эмулятора зеркала на 18099."""

    async def test_http_download_import_and_not_modified(
        self, osm_extract_service: None
    ) -> None:
        """HEAD Last-Modified → GET-стриминг → publish; повтор → skip."""
        _ = osm_extract_service
        snapshot = await _snapshot_state()
        try:
            await _set_state(generation=0, source_modified_at=None)
            svc = _import_svc(
                GeoSettings(osm_extract_urls=[_EMU_URL])
            )
            before_tmps = set(Path(tempfile.gettempdir()).glob("tmp*.osm.pbf"))
            result = await svc.run_sync()
            assert result["imported"] is True
            assert result["rows_addresses"] == 4
            assert result["rows_edges"] == 9
            assert result["rows_restrictions"] == 2
            assert result["rows_barriers"] == 1
            assert result["rows_signals"] == 1
            state = await _state()
            assert state.current_generation == 1
            assert state.source_modified_at is not None
            # Скачанный tmp-файл удалён после парсинга.
            assert set(Path(tempfile.gettempdir()).glob("tmp*.osm.pbf")) == before_tmps

            second = await svc.run_sync()
            assert second == {"skipped": True, "reason": "not_modified"}
            assert (await _state()).current_generation == 1
        finally:
            await _restore_state(snapshot)

    async def test_http_no_last_modified_reimports(
        self, osm_extract_service: None
    ) -> None:
        """Зеркало без Last-Modified → источник «всегда свежий», реимпорт."""
        _ = osm_extract_service
        snapshot = await _snapshot_state()
        try:
            await _set_state(generation=0, source_modified_at=None)
            svc = _import_svc(
                GeoSettings(osm_extract_urls=[_EMU_NO_LM_URL])
            )
            first = await svc.run_sync()
            assert first["imported"] is True
            # modified=now() на каждый запуск → второй проход тоже импортирует.
            second = await svc.run_sync()
            assert second["imported"] is True
            assert (await _state()).current_generation == 2
        finally:
            await _restore_state(snapshot)

    async def test_http_404_fails_and_preserves_generation(
        self, osm_extract_service: None
    ) -> None:
        """404 на HEAD → FAILED; опубликованное поколение не тронуто."""
        _ = osm_extract_service
        snapshot = await _snapshot_state()
        try:
            await _set_state(generation=5, source_modified_at=None)
            svc = _import_svc(
                GeoSettings(
                    osm_extract_urls=[
                        "http://127.0.0.1:18099/extracts/missing.osm.pbf"
                    ]
                )
            )
            with pytest.raises(Exception):
                _ = await svc.run_sync()
            state = await _state()
            assert state.status == GeoImportStatus.FAILED
            assert state.last_error != ""
            assert state.current_generation == 5
        finally:
            await _restore_state(snapshot)

    async def test_http_unreachable_fails(self, geo_service: None) -> None:
        """Зеркало недоступно (порт закрыт) → FAILED, поколение на месте."""
        _ = geo_service
        snapshot = await _snapshot_state()
        try:
            await _set_state(generation=6, source_modified_at=None)
            svc = _import_svc(
                GeoSettings(
                    osm_extract_urls=[
                        "http://127.0.0.1:19999/extracts/x.osm.pbf"
                    ]
                )
            )
            with pytest.raises(Exception):
                _ = await svc.run_sync()
            state = await _state()
            assert state.status == GeoImportStatus.FAILED
            assert state.current_generation == 6
        finally:
            await _restore_state(snapshot)


class TestTickAndRegistration:
    """Тик на брокере очереди geo и его исполнение живым воркером."""

    def test_spec_registered_on_geo_broker(self) -> None:
        """GEO_OSM_SYNC_TICK: scheduled=True, на брокере 'geo' — гейт scheduler."""
        wire_all()
        spec_names = {spec.name for spec in scheduled_task_specs()}
        assert GEO_OSM_SYNC_TICK.name in spec_names
        brokers = registered_queue_brokers()
        assert brokers["geo"].find_task(GEO_OSM_SYNC_TICK.name) is not None

    def test_require_scheduled_tasks_registered_passes(self) -> None:
        """Та же проверка, что падает на старте scheduler-процесса."""
        wire_all()
        require_scheduled_tasks_registered()

    async def test_tick_executes_real_import(self, geo_worker: None) -> None:
        """enqueue(tick) → воркер исполняет run_sync → поколение растёт."""
        _ = geo_worker
        # Указатель ниже сид-пола: публикация в gen=1, cleanup сидов не трогает;
        # source_modified_at=None → воркер делает полный импорт micro.osm.
        await _set_state(generation=0, source_modified_at=None)
        task = await enqueue(GEO_OSM_SYNC_TICK, background_kind="background")
        result = await task.wait_result(timeout=120)
        assert not result.is_err
        assert result.return_value == {
            "imported": True,
            "rows_addresses": 4,
            "rows_vertices": 8,
            "rows_edges": 9,
            "rows_restrictions": 2,
            "rows_barriers": 1,
            "rows_signals": 1,
        }
        state = await _state()
        assert state.current_generation == 1
        assert state.status == GeoImportStatus.IDLE

    async def test_double_tick_publishes_once(self, geo_worker: None) -> None:
        """Два тика подряд → один импорт; второй завершается not_modified."""
        _ = geo_worker
        await _set_state(generation=0, source_modified_at=None)
        first = await enqueue(GEO_OSM_SYNC_TICK, background_kind="background")
        second = await enqueue(GEO_OSM_SYNC_TICK, background_kind="background")
        results = [
            await first.wait_result(timeout=120),
            await second.wait_result(timeout=120),
        ]
        assert not any(r.is_err for r in results)
        outcomes = [r.return_value for r in results]
        assert any(isinstance(o, dict) and o.get("imported") for o in outcomes)
        assert any(isinstance(o, dict) and o.get("skipped") for o in outcomes)
        # Если оба прошли — импорт ровно один, второго поколения нет.
        assert (await _state()).current_generation == 1


class TestCoverageRegistry:
    """Реестр покрытия: сид дефолтного региона, per-регион счётчики,
    источники, курсоры и очередь обогащения."""

    async def test_import_seeds_region_stats_and_marks_rows(
        self, geo_service: None
    ) -> None:
        """Первый импорт сидит регион: строки данных и geo_stats его помечены."""
        _ = geo_service
        snapshot = await _snapshot_state()
        try:
            await _set_state(generation=0, source_modified_at=None)
            svc = _import_svc(GeoSettings(osm_extract_urls=[f"file://{_MICRO}"]))
            result = await svc.run_sync()
            assert result["imported"] is True
            gen = (await _state()).current_generation

            region = await GeoRegion.by_name("moscow")
            assert region is not None
            assert region.extract_urls == [f"file://{_MICRO}"]
            assert region.last_imported_at is not None

            rows = await execute_raw(
                "SELECT DISTINCT region FROM geo_addresses WHERE generation = $1",
                [gen],
                using="geo",
            )
            assert [r["region"] for r in rows] == ["moscow"]

            stats = await GeoStats.list_for_generation(gen)
            assert {s.entity: s.rows for s in stats} == {
                "addresses": 4,
                "vertices": 8,
                "edges": 9,
                "restrictions": 2,
                "barriers": 1,
                "signals": 1,
            }
            assert {s.source for s in stats} == {"osm"}

            coverage = GeoCoverageService(GeoSettings())
            overview = await coverage.stats_overview()
            assert overview.generation == gen
            assert overview.totals["addresses"] == 4
            regions = await coverage.regions_response()
            assert regions.generation == gen
            assert regions.items[0].addresses == 4
        finally:
            await _restore_state(snapshot)

    async def test_registry_overrides_settings(
        self, geo_service: None, tmp_path: Path
    ) -> None:
        """Непустой ``geo_regions`` — источник истины: настройки не сидятся."""
        _ = geo_service
        snapshot = await _snapshot_state()
        src = tmp_path / "town.osm"
        _ = src.write_bytes(_MICRO.read_bytes())
        try:
            await _set_state(generation=0, source_modified_at=None)
            now = datetime.now(UTC)
            _ = await GeoRegion.objects.create(
                instance=GeoRegion(
                    name="town",
                    title="Городок",
                    kind=GeoRegionKind.CITY,
                    bbox_south=54.0,
                    bbox_west=35.0,
                    bbox_north=57.0,
                    bbox_east=41.0,
                    extract_urls=[f"file://{src}"],
                    enabled=True,
                    created_at=now,
                    updated_at=now,
                )
            )
            # Настройки указывают на несуществующий файл — он не должен читаться.
            svc = _import_svc(GeoSettings(osm_extract_urls=["file:///absent.osm"]))
            result = await svc.run_sync()
            assert result["imported"] is True
            assert result["rows_addresses"] == 4
            assert await GeoRegion.count_all() == 1
            stats = await GeoStats.list_for_generation(
                (await _state()).current_generation
            )
            assert {s.region for s in stats} == {"town"}
        finally:
            await _restore_state(snapshot)

    async def test_region_crud_and_errors(self) -> None:
        """create/update/delete + конфликт, отсутствие и невалидный bbox."""
        svc = GeoCoverageService(GeoSettings())
        payload = GeoRegionUpsertRequest(
            name="spb",
            title="Санкт-Петербург",
            bbox=GeoBbox(south=59.6, west=29.4, north=60.3, east=31.0),
            extract_urls=["file:///tmp/spb.osm"],
        )
        item = await svc.create_region(payload)
        assert item.name == "spb"
        with pytest.raises(PlatformConflictError):
            _ = await svc.create_region(payload)

        updated = await svc.update_region(
            GeoRegionUpsertRequest(
                name="spb",
                title="Питер",
                bbox=payload.bbox,
                extract_urls=payload.extract_urls,
            )
        )
        assert updated.title == "Питер"

        await svc.delete_region("spb")
        with pytest.raises(PlatformNotFoundError):
            _ = await svc.delete_region("spb")

        with pytest.raises(GeoCoverageError):
            _ = await svc.create_region(
                GeoRegionUpsertRequest(
                    name="bad",
                    bbox=GeoBbox(south=60.0, west=29.0, north=59.0, east=31.0),
                )
            )

    async def test_sources_cursors_and_enrich_views(self) -> None:
        """Allowlist источников, курсоры потоков и очередь обогащения."""
        svc = GeoCoverageService(GeoSettings())
        await svc.ensure_seeded()
        sources = await svc.sources_response()
        assert {"osm", "manual"} <= {s.name for s in sources.items}
        osm = next(s for s in sources.items if s.name == "osm")
        assert osm.enabled and "ODbL" in osm.license

        now = datetime.now(UTC)
        _ = await GeoSourceCursor.objects.create(
            instance=GeoSourceCursor(
                source="nspd",
                region="moscow",
                cursor="page:7",
                status=GeoCursorStatus.RUNNING,
                rows_done=42,
                updated_at=now,
            )
        )
        cursors = await svc.cursors_response()
        assert [(c.source, c.rows_done) for c in cursors.items] == [("nspd", 42)]

        _ = await GeoEnrichItem.objects.create(
            instance=GeoEnrichItem(
                kind="building_nspd",
                payload={"source_ref": "77:01:0001001:1234"},
                priority=5,
                created_at=now,
                updated_at=now,
            )
        )
        enrich = await svc.enrich_list_response(status=None, limit=10, offset=0)
        assert enrich.pending == 1
        assert enrich.items[0].kind == "building_nspd"


class TestLayers:
    """Канонические слои карты: реестр, счётчики и фичи по рамке."""

    async def test_layers_counts_and_bbox_features(
        self, geo_service: None
    ) -> None:
        """Импорт наполняет слои: счётчики, зум-фильтры, GeoJSON-фичи."""
        _ = geo_service
        snapshot = await _snapshot_state()
        try:
            await _set_state(generation=0, source_modified_at=None)
            svc = _import_svc(GeoSettings(osm_extract_urls=[f"file://{_MICRO}"]))
            result = await svc.run_sync()
            assert result["imported"] is True

            layers_svc = GeoLayerService()
            listed = await layers_svc.layers_response()
            counts = {layer.name: layer.features for layer in listed.layers}
            assert counts == {
                "regions": 1,
                "roads": 9,
                "addresses": 4,
                "restrictions": 2,
                "barriers": 1,
                "signals": 1,
            }
            by_name = {layer.name: layer for layer in listed.layers}
            assert by_name["roads"].min_zoom < by_name["addresses"].min_zoom

            features = await layers_svc.features_response(
                south=54.0, west=35.0, north=57.0, east=41.0, zoom=15,
                layer_names=[],
            )
            per_layer = {f.layer for f in features.features}
            assert per_layer == {
                "regions", "roads", "addresses",
                "restrictions", "barriers", "signals",
            }
            roads = [f for f in features.features if f.layer == "roads"]
            assert roads[0].geometry["type"] == "LineString"
            assert "highway" in roads[0].properties
            # via-node рестрикция резолвит координаты; via-way — без geom,
            # слой её не рендерит.
            restrictions = [
                f for f in features.features if f.layer == "restrictions"
            ]
            assert len(restrictions) == 1
            assert restrictions[0].geometry["type"] == "Point"
            assert restrictions[0].properties["restriction"] == "no_left_turn"
            barriers = [
                f for f in features.features if f.layer == "barriers"
            ]
            assert len(barriers) == 1
            assert barriers[0].properties["barrier"] == "bollard"
            assert barriers[0].properties["block_car"] is True
            assert barriers[0].properties["block_foot"] is False
            signals = [
                f for f in features.features if f.layer == "signals"
            ]
            assert len(signals) == 1
            assert signals[0].properties["osm_node_id"] == 2
            assert features.truncated is False

            # Сырые ссылки отношений: from/to way, via node/way.
            rel_rows = await execute_raw(
                "SELECT restriction, via_node, via_way, via_lat IS NOT NULL"
                + " AS has_coords FROM geo_turn_restrictions"
                + " WHERE generation = $1 ORDER BY osm_relation_id",
                [(await _state()).current_generation],
                using="geo",
            )
            assert [
                (r["restriction"], r["via_node"], r["via_way"], r["has_coords"])
                for r in rel_rows
            ] == [
                ("no_left_turn", 2, None, True),
                ("no_u_turn", None, 16, False),
            ]

            # Под min_zoom адресного слоя — дороги видны, адреса нет.
            low_zoom = await layers_svc.features_response(
                south=54.0, west=35.0, north=57.0, east=41.0, zoom=12,
                layer_names=[],
            )
            assert {f.layer for f in low_zoom.features} == {"regions", "roads"}

            only_roads = await layers_svc.features_response(
                south=54.0, west=35.0, north=57.0, east=41.0, zoom=15,
                layer_names=["roads"],
            )
            assert {f.layer for f in only_roads.features} == {"roads"}
        finally:
            await _restore_state(snapshot)

    async def test_features_errors(self) -> None:
        """Невалидная рамка и неизвестный слой — доменные ошибки."""
        svc = GeoLayerService()
        with pytest.raises(GeoCoverageError) as bad_bbox:
            _ = await svc.features_response(
                south=57.0, west=35.0, north=54.0, east=41.0, zoom=15,
                layer_names=[],
            )
        assert bad_bbox.value.code == "geo_bbox_invalid"
        with pytest.raises(GeoCoverageError) as unknown:
            _ = await svc.features_response(
                south=54.0, west=35.0, north=57.0, east=41.0, zoom=15,
                layer_names=["moon"],
            )
        assert unknown.value.code == "geo_layer_unknown"
