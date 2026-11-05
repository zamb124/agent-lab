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
from apps.geo.models.geo_import_state import GeoImportState, GeoImportStatus
from apps.geo.services.osm_import_service import OsmImportService
from apps.geo.tasks.task_names import GEO_OSM_SYNC_TICK
from apps.geo.worker import ensure_import_bootstrapped
from apps.scheduler.dispatch import require_scheduled_tasks_registered
from apps.worker_manifest import wire_all
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


@pytest.fixture(autouse=True)
async def _clean_import_generations() -> None:
    for table in ("geo_addresses", "geo_road_vertices", "geo_road_edges"):
        _ = await execute_raw(
            f"DELETE FROM {table} WHERE generation < $1",
            [_SEED_FLOOR],
            using="geo",
        )


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
        svc = OsmImportService(GeoSettings())
        # Сама рецепт-функция из worker.py — ровно то, что зовёт startup.
        await ensure_import_bootstrapped(svc)

        state = await _wait_generation_at_least(1)
        # Воркер импортировал micro.osm из своего env — полный прод-парс.
        assert state.rows_addresses == 4
        assert state.rows_vertices == 8
        assert state.rows_edges == 9
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
            svc = OsmImportService(GeoSettings())
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
            svc = OsmImportService(GeoSettings())
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
            disabled = OsmImportService(GeoSettings(sync_enabled=False))
            no_urls = OsmImportService(GeoSettings(osm_extract_urls=[]))
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
            svc = OsmImportService(
                GeoSettings(osm_extract_urls=[f"file://{src}"])
            )
            result = await svc.run_sync()
            assert result["imported"] is True
            assert result["rows_addresses"] == 4
            assert result["rows_vertices"] == 8
            assert result["rows_edges"] == 9
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
            svc = OsmImportService(
                GeoSettings(osm_extract_urls=[f"file://{_MICRO_PBF}"])
            )
            result = await svc.run_sync()
            assert result["imported"] is True
            assert result["rows_addresses"] == 4
            assert result["rows_edges"] == 9
            assert _MICRO_PBF.is_file()
        finally:
            await _restore_state(snapshot)

    async def test_second_run_not_modified(self, geo_service: None) -> None:
        """Та же mtime → If-Modified-Since → skip без нового поколения."""
        _ = geo_service
        snapshot = await _snapshot_state()
        try:
            await _set_state(generation=0, source_modified_at=None)
            svc = OsmImportService(
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
            svc = OsmImportService(
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
            svc = OsmImportService(
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
            svc = OsmImportService(
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
            svc = OsmImportService(
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
            svc = OsmImportService(
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
            svc = OsmImportService(
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
            svc = OsmImportService(GeoSettings(sync_enabled=False))
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
            svc = OsmImportService(
                GeoSettings(osm_extract_urls=[_EMU_URL])
            )
            tmp_glob = Path(tempfile.gettempdir()).glob("tmp*.osm.pbf")
            before_tmps = set(tmp_glob)
            result = await svc.run_sync()
            assert result["imported"] is True
            assert result["rows_addresses"] == 4
            assert result["rows_edges"] == 9
            state = await _state()
            assert state.current_generation == 1
            assert state.source_modified_at is not None
            # Скачанный tmp-файл удалён после парсинга.
            assert set(tmp_glob) == before_tmps

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
            svc = OsmImportService(
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
            svc = OsmImportService(
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
            svc = OsmImportService(
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
