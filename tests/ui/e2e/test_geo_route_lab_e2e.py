"""Страница «Маршрутная лаборатория» /geo/route-lab.

Продовый путь: Chromium + auth-cookie владельца компании, SPA geo на
:9028, маршрут считается боевым `geo/route/calculate` против графа
micro.osm (PostGIS + pgRouting). Без моков.

Покрытие: чипы режимов car/foot/bike/scooter, постановка точек A/B
кликами по карте, метрики дистанции и времени, пересчёт при смене
режима, сброс точек третьим кликом.
"""

from __future__ import annotations

import asyncio
import time
from typing import cast

import pytest
from playwright.async_api import Page, expect

from apps.geo.models.geo_import_state import GeoImportState, GeoImportStatus
from apps.geo.models.geo_road_edge import GeoRoadEdge
from apps.geo.tasks.task_names import GEO_OSM_SYNC_TICK
from core.tasks import enqueue
from tests.ui.apps import SERVICE_UI_REGISTRY
from tests.ui.harness import AppUI, ui_wait_ws_open
from tests.ui.scenario_doc import ScenarioRecorder

_GEO_UI = AppUI(SERVICE_UI_REGISTRY["geo"])

# micro.osm: две точки на дорожном графе Тверской улицы.
_ROAD_A = (37.6170, 55.7500)
_ROAD_B = (37.6190, 55.7510)


@pytest.fixture(scope="module", autouse=True)
async def _geo_graph_imported(geo_worker: None) -> None:
    """Маршруту нужен живой граф: нет рёбер поколения → боевой тик.

    ``current_generation`` может врать после соседних сьютов, чистящих
    строки поколений — проверяем сами рёбра, а не только указатель.
    """
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
        await state.save()
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


async def _open_route_lab(page: Page) -> None:
    _ = await page.goto(f"{_GEO_UI.spa_url()}route-lab", wait_until="load")
    await expect(page.locator("geo-app")).to_be_visible(timeout=30_000)
    await expect(page.locator("geo-route-lab-page")).to_be_visible(timeout=30_000)
    await expect(page.locator("canvas.maplibregl-canvas")).to_be_visible(timeout=30_000)
    await ui_wait_ws_open(page)


async def _project(page: Page, lng: float, lat: float) -> tuple[float, float]:
    """Экранные координаты lngLat внутри canvas platform-map."""
    pt = cast(
        dict[str, float],
        await page.locator("platform-map").first.evaluate(
            "(el, ll) => { const m = el.getMap(); const p = m.project(ll); return {x: p.x, y: p.y}; }",
            [lng, lat],
        ),
    )
    box = await page.locator("canvas.maplibregl-canvas").bounding_box()
    assert box is not None
    return box["x"] + float(pt["x"]), box["y"] + float(pt["y"])


@pytest.mark.scenario(
    service="geo",
    tag="route_lab",
    doc_slug="route-lab",
    timeout_seconds=90,
    title="Geo: маршрутная лаборатория",
    description=(
        "Два клика по карте строят маршрут A→B боевым движком: "
        "дистанция, время и пересчёт при смене режима движения."
    ),
    title_en="Geo: route lab",
    description_en=(
        "Two map clicks build an A→B route with the real engine: "
        "distance, duration and recalculation on mode switch."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_route_lab_builds_route_and_switches_mode(
    scenario: ScenarioRecorder,
    ui_page_system: Page,
) -> None:
    page = ui_page_system
    await page.add_init_script("localStorage.setItem('pwa-banner-dismissed', 'true');")
    await _open_route_lab(page)

    # Чипы режимов: 4 кнопки, car активен по умолчанию.
    modes = page.locator("geo-route-lab-page .map-modes .mode-btn")
    await expect(modes).to_have_count(4)
    await expect(modes.first).to_have_class("mode-btn active")
    # Подсказка ожидания кликов видна, метрик нет.
    await expect(page.locator("geo-route-lab-page .map-hint")).to_be_visible()
    await expect(page.locator("geo-route-lab-page .map-metrics")).to_have_count(0)

    # Камера на граф micro.osm.
    _ = await page.locator("platform-map").first.evaluate(
        "(el) => { el.getMap().jumpTo({ center: [37.6180, 55.7505], zoom: 16 }); return true; }"
    )
    await asyncio.sleep(0.5)

    # Клик 1 — точка A: маркер ставится, метрик ещё нет.
    x, y = await _project(page, *_ROAD_A)
    await page.mouse.click(x, y)
    await asyncio.sleep(0.3)

    # Клик 2 — точка B: боевой route/calculate → метрики.
    x, y = await _project(page, *_ROAD_B)
    await page.mouse.click(x, y)
    metrics = page.locator("geo-route-lab-page .map-metrics")
    await expect(metrics).to_be_visible(timeout=20_000)
    car_text = await metrics.inner_text()
    assert "км" in car_text or "km" in car_text, car_text
    await scenario.step(
        "Маршрут A→B построен: дистанция и время на карте",
        page,
        label_en="Route A→B built: distance and duration on the map",
    )

    # Смена режима foot → пересчёт, метрики остаются.
    await modes.nth(1).click()
    await expect(modes.nth(1)).to_have_class("mode-btn active")
    await expect(metrics).to_be_visible(timeout=20_000)
    foot_text = await metrics.inner_text()
    assert foot_text, "метрики исчезли после смены режима"
    await scenario.step(
        "Режим «пешком» пересчитал маршрут",
        page,
        label_en="Foot mode recalculated the route",
    )

    # Третий клик — сброс: новая точка A, метрики и B убираются.
    x, y = await _project(page, *_ROAD_A)
    await page.mouse.click(x, y)
    await asyncio.sleep(0.3)
    await expect(metrics).to_have_count(0)


@pytest.mark.scenario(
    service="geo",
    tag="route_lab",
    doc_slug="route-lab-matrix",
    timeout_seconds=90,
    title="Geo: матрица времени и оптимальный объезд",
    description=(
        "Инструменты лаборатории: матрица N×N длительностей по графу и "
        "оптимальный порядок объезда точек доставки."
    ),
    title_en="Geo: time matrix and optimal order",
    description_en=(
        "Lab tools: N×N duration matrix over the road graph and optimal "
        "stop ordering for deliveries."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_route_lab_matrix_and_order(
    scenario: ScenarioRecorder,
    ui_page_system: Page,
) -> None:
    page = ui_page_system
    await page.add_init_script("localStorage.setItem('pwa-banner-dismissed', 'true');")
    await _open_route_lab(page)

    _ = await page.locator("platform-map").first.evaluate(
        "(el) => { el.getMap().jumpTo({ center: [37.6180, 55.7505], zoom: 16 }); return true; }"
    )
    await asyncio.sleep(0.5)

    # Инструмент «Матрица»: два клика ставят точки, «Вычислить» — таблица 2×2.
    await page.locator("geo-route-lab-page .map-tools [data-tool='matrix']").click()
    for pt in (_ROAD_A, _ROAD_B):
        x, y = await _project(page, *pt)
        await page.mouse.click(x, y)
        await asyncio.sleep(0.3)
    await page.locator("geo-route-lab-page .map-actions [data-action='compute']").click()
    panel = page.locator("geo-route-lab-page .map-panel[data-panel='matrix']")
    await expect(panel).to_be_visible(timeout=20_000)
    await expect(panel.locator("tbody tr")).to_have_count(2)
    await scenario.step(
        "Матрица 2×2 длительностей построена боевым движком",
        page,
        label_en="2×2 duration matrix computed by the real engine",
    )

    # Инструмент «Объезд»: старт + остановка → оптимальная последовательность.
    await page.locator("geo-route-lab-page .map-tools [data-tool='order']").click()
    for pt in (_ROAD_A, _ROAD_B):
        x, y = await _project(page, *pt)
        await page.mouse.click(x, y)
        await asyncio.sleep(0.3)
    await page.locator("geo-route-lab-page .map-actions [data-action='compute']").click()
    order_panel = page.locator("geo-route-lab-page .map-panel[data-panel='order']")
    await expect(order_panel).to_be_visible(timeout=20_000)
    await expect(order_panel.locator(".seq .pill")).to_have_count(2)
    await scenario.step(
        "Оптимальный объезд: последовательность S → P2 и итог маршрута",
        page,
        label_en="Optimal order: sequence S → P2 with route totals",
    )
