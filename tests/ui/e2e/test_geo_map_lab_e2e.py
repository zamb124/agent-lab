"""Страница «Карта» /geo/map-lab — витрина возможностей platform-map.

Продовый путь: Chromium + auth-cookie владельца компании, SPA geo на
:9028, маршрут и изохроны строятся боевым движком против графа
micro.osm (PostGIS + pgRouting). Без моков.

Покрытие: демо-маркеры и кластер, GeoJSON-зона, маршрут с кольцами
изохрон, линейка измерения расстояния, раскрытие кластера кликом,
встраиваемое превью карты.
"""

from __future__ import annotations

import asyncio
import time
from typing import cast

import pytest
from playwright.async_api import Page, ViewportSize, expect

from apps.geo.models.geo_import_state import GeoImportState, GeoImportStatus
from apps.geo.models.geo_road_edge import GeoRoadEdge
from apps.geo.tasks.task_names import GEO_OSM_SYNC_TICK
from core.tasks import enqueue
from tests.ui.apps import SERVICE_UI_REGISTRY
from tests.ui.harness import AppUI, ui_wait_ws_open
from tests.ui.scenario_doc import ScenarioRecorder
from tests.ui.shots.conftest import click_geo_map_at, wait_geo_map_ready

_GEO_UI = AppUI(SERVICE_UI_REGISTRY["geo"])

_DESKTOP = ViewportSize(width=1440, height=900)
_CENTER = (37.6178, 55.7503)


@pytest.fixture(scope="module", autouse=True)
async def _geo_graph_imported(geo_worker: None) -> None:
    """Маршрут и изохроны map-lab строятся по графу micro.osm."""
    _ = geo_worker
    state = await GeoImportState.get_state()
    edges = (
        await GeoRoadEdge.objects.filter(generation=state.current_generation).count()
        if state is not None and state.current_generation > 0
        else 0
    )
    if edges == 0 and state is not None:
        state.current_generation = 0
        state.source_modified_at = None
        state.status = GeoImportStatus.IDLE
        _ = await state.save()
    if state is None or edges == 0:
        _ = await enqueue(GEO_OSM_SYNC_TICK, background_kind="background")
        deadline = time.monotonic() + 120.0
        while time.monotonic() < deadline:
            state = await GeoImportState.get_state()
            if state is None:
                await asyncio.sleep(0.5)
                continue
            if state.status == GeoImportStatus.FAILED:
                pytest.fail(f"geo импорт упал: {state.last_error}", pytrace=False)
            if state.current_generation > 0 and state.status == GeoImportStatus.IDLE:
                return
            await asyncio.sleep(0.5)
        pytest.fail("geo импорт не опубликовал поколение за 120s", pytrace=False)


async def _open_map_lab(page: Page) -> None:
    _ = await page.goto(f"{_GEO_UI.spa_url()}map-lab", wait_until="load")
    await expect(page.locator("geo-map-lab-page")).to_be_visible(timeout=30_000)
    await wait_geo_map_ready(page, center=_CENTER, zoom=14)
    await ui_wait_ws_open(page)


async def _wait_map_source(
    page: Page, source: str, minimum: int, timeout_s: float = 40.0
) -> None:
    """Поллинг фич geojson-source карты (маршрут/изохроны строятся async)."""
    deadline = time.monotonic() + timeout_s
    while True:
        count = cast(
            int,
            await page.locator("platform-map").first.evaluate(
                """(el, src) => {
                    const s = el.getMap().getSource(src);
                    const d = s ? s.serialize().data : null;
                    if (!d) return -1;
                    if (d.type === 'Feature') return 1;
                    return d.features ? d.features.length : 0;
                }""",
                source,
            ),
        )
        if count >= minimum:
            return
        if time.monotonic() >= deadline:
            raise AssertionError(
                f"map-lab: source {source} — {count} фич < {minimum} за {timeout_s}s"
            )
        await page.wait_for_timeout(400)


@pytest.mark.scenario(
    service="geo",
    tag="map_lab",
    doc_slug="map-lab-tour",
    timeout_seconds=120,
    title="Карта Geo: маркеры, зоны и линейка",
    description=(
        "Раздел «Карта» показывает все возможности платформенной карты "
        "на живом примере: кластеры точек, выделенная зона, маршрут, "
        "зоны доступности и линейка для измерения расстояний."
    ),
    title_en="Geo map: markers, zones and ruler",
    description_en=(
        "The «Map» section shows every platform-map capability on a "
        "live example: point clusters, a highlighted zone, a route, "
        "reachability rings and a distance ruler."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_geo_map_lab_tour(
    scenario: ScenarioRecorder,
    ui_page_system: Page,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)
    _ = await page.add_init_script(
        "localStorage.setItem('pwa-banner-dismissed', 'true');"
    )
    await _open_map_lab(page)

    # Боевые слои демо: зона, маршрут, изохроны — всё строится движком.
    await _wait_map_source(page, "pm-ov-demo-zone", 1)
    await _wait_map_source(page, "pm-route", 1)
    await _wait_map_source(page, "pm-iso", 1)
    await expect(
        page.locator("geo-map-lab-page .preview platform-map")
    ).to_be_visible(timeout=15_000)
    await page.wait_for_timeout(900)
    await scenario.step(
        "Откройте «Карту» в меню Geo",
        page,
        screenshot_name="map-lab-overview",
        label_en="Open «Map» in the Geo menu",
        details=(
            "Раздел «Карта» — витрина гео-возможностей компании. "
            "На карте сразу видно: маркеры точек (синяя — курьер, "
            "зелёная — склад), круглый значок кластера объединяет "
            "близкие точки, фиолетовый контур — выделенная зона, "
            "линия — построенный маршрут, а кольца вокруг точки — "
            "зоны доступности за 3 и 7 минут пешком. Панель слева "
            "показывает адреса, попавшие в выделенную зону. Справа — пример "
            "компактной карты-превью, которую можно встраивать "
            "в другие страницы."
        ),
        details_en=(
            "The «Map» section is a showcase of the company geo "
            "capabilities. The map immediately shows: point markers "
            "(blue — courier, green — depot), a round cluster badge "
            "grouping nearby points, a purple outline — a highlighted "
            "zone, a line — a built route, and rings around a point — "
            "3- and 7-minute walking reachability zones. The left "
            "panel lists addresses inside the highlighted zone. On "
            "the right — a compact preview map that can be embedded "
            "into other pages."
        ),
    )

    # Линейка: режим ruler → два клика → линия с подписью расстояния.
    ruler_btn = page.locator("platform-map .pm-ctrl[data-action='ruler']").first
    await expect(ruler_btn).to_be_visible(timeout=15_000)
    await ruler_btn.click()
    await click_geo_map_at(page, (37.6135, 55.7508))
    await page.wait_for_timeout(300)
    await click_geo_map_at(page, (37.6215, 55.7498))
    await _wait_map_source(page, "pm-ruler", 3)
    # Выходим из режима линейки — линия и подпись остаются на карте.
    await ruler_btn.click()
    await page.wait_for_timeout(400)
    await scenario.step(
        "Измерьте расстояние линейкой",
        page,
        screenshot_name="map-lab-ruler",
        label_en="Measure a distance with the ruler",
        details=(
            "Нажмите кнопку линейки на панели инструментов карты и "
            "кликните две точки — между ними появится линия с "
            "расстоянием в метрах или километрах. Каждый следующий "
            "клик продолжает ломаную, а повторное нажатие кнопки "
            "завершает измерение."
        ),
        details_en=(
            "Click the ruler button on the map toolbar and click two "
            "points — a line with the distance in meters or kilometers "
            "appears between them. Each next click extends the "
            "polyline, and pressing the button again finishes "
            "the measurement."
        ),
    )

    # Кластер: клик по круглому значку приближает карту и раскрывает точки.
    ruler_left = cast(
        int,
        await page.locator("platform-map").first.evaluate(
            """(el) => {
                el.clearRuler();
                const s = el.getMap().getSource('pm-ruler');
                const d = s ? s.serialize().data : null;
                return d && d.features ? d.features.length : -1;
            }"""
        ),
    )
    assert ruler_left == 0, f"линейка не очищена: {ruler_left} фич"
    zoom_before = cast(
        float,
        await page.locator("platform-map").first.evaluate(
            "(el) => el.getMap().getZoom()"
        ),
    )
    cluster_pt = cast(
        dict[str, float] | None,
        await page.locator("platform-map").first.evaluate(
            """(el) => {
                const m = el.getMap();
                const feats = m.queryRenderedFeatures({ layers: ['pm-cluster-circle'] });
                if (!feats.length) return null;
                const p = m.project(feats[0].geometry.coordinates);
                return { x: p.x, y: p.y };
            }"""
        ),
    )
    assert cluster_pt is not None, "кластер маркеров не отрендерен"
    box = cast(
        dict[str, float] | None,
        await page.locator("canvas.maplibregl-canvas").first.bounding_box(),
    )
    assert box is not None
    await page.mouse.click(
        box["x"] + float(cluster_pt["x"]), box["y"] + float(cluster_pt["y"])
    )
    await page.wait_for_timeout(1400)
    zoom_after = cast(
        float,
        await page.locator("platform-map").first.evaluate(
            "(el) => el.getMap().getZoom()"
        ),
    )
    popup_count = await page.locator(".pm-cluster-popup").count()
    assert (
        zoom_after > zoom_before or popup_count > 0
    ), "клик по кластеру не раскрыл точки"
    await page.wait_for_timeout(600)
    await scenario.step(
        "Раскройте кластер точек",
        page,
        screenshot_name="map-lab-cluster",
        label_en="Expand a point cluster",
        details=(
            "Когда точек много рядом, карта объединяет их в круглый "
            "значок с числом. Клик по нему приближает карту — и "
            "каждая точка становится видна отдельно. Так работает "
            "кластеризация во всех сервисах, где есть карта.\n\n"
            "**Итог.** Карта Geo умеет показывать маркеры и кластеры, "
            "выделенные зоны, маршруты и зоны доступности, а линейка "
            "измеряет расстояние прямо на карте."
        ),
        details_en=(
            "When many points are close together, the map groups them "
            "into a round badge with a count. Clicking it zooms in — "
            "and each point becomes visible separately. Clustering "
            "works the same way in every service that has a map.\n\n"
            "**Summary.** The Geo map can show markers and clusters, "
            "highlighted zones, routes and reachability rings, and "
            "the ruler measures distance right on the map."
        ),
    )
