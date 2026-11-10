"""Документационные сценарии Geo для обычного пользователя.

`address-lookup-on-map` — найти адрес на карте: главная Geo содержит
карту с поисковой строкой; запрос «тверск» по справочнику micro.osm
возвращает подсказки, выбор ставит пин и переносит камеру.
"""

from __future__ import annotations

import asyncio
import time

import pytest
from playwright.async_api import Page, expect

from apps.geo.models.geo_import_state import GeoImportState, GeoImportStatus
from apps.geo.models.geo_road_edge import GeoRoadEdge
from apps.geo.tasks.task_names import GEO_OSM_SYNC_TICK
from core.tasks import enqueue
from tests.ui.apps import SERVICE_UI_REGISTRY
from tests.ui.harness import AppUI, ui_wait_ws_open
from tests.ui.scenario_doc import ScenarioRecorder
from tests.ui.shots.conftest import wait_geo_map_ready

_GEO_UI = AppUI(SERVICE_UI_REGISTRY["geo"])

_DESKTOP = {"width": 1440, "height": 900}


@pytest.fixture(scope="module", autouse=True)
async def _geo_graph_imported(geo_worker: None) -> None:
    """micro.osm импорт: рёбра графа и справочник адресов (тик geo_worker)."""
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


@pytest.mark.scenario(
    service="geo",
    tag="addresses",
    doc_slug="address-lookup-on-map",
    timeout_seconds=90,
    title="Находим адрес на карте",
    description=(
        "Строка поиска на карте Geo подсказывает адреса из справочника: "
        "выбираем подсказку — карта сама переносится к точке и ставит пин."
    ),
    title_en="Find an address on the map",
    description_en=(
        "The map search box in Geo suggests addresses from the directory: "
        "pick a suggestion — the map flies to the point and drops a pin."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_geo_address_lookup_on_map(
    scenario: ScenarioRecorder,
    ui_page_system: Page,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)
    await _GEO_UI.open(page)
    await expect(page.locator("geo-overview-page")).to_be_visible(timeout=30_000)
    await wait_geo_map_ready(page)
    await ui_wait_ws_open(page)

    await scenario.step(
        "Откройте Geo — сразу видна карта",
        page,
        screenshot_name="geo-map-overview",
        label_en="Open Geo — the map is right there",
        details=(
            "Geo открывается картой вашего города. Слева — меню разделов, "
            "сверху на карте — строка поиска адреса. Справочник адресов "
            "уже подключён — искать можно сразу."
        ),
        details_en=(
            "Geo opens with a map of your city. On the left — section "
            "menu, on top of the map — an address search box. The address "
            "directory is already connected — you can search right away."
        ),
    )

    search_input = page.locator("platform-map .pm-search-input").first
    await expect(search_input).to_be_visible(timeout=15_000)
    await search_input.click()
    await search_input.press_sequentially("Тверская", delay=60)
    suggest_item = page.locator("platform-map .pm-suggest-item").first
    try:
        await expect(suggest_item).to_be_visible(timeout=20_000)
    except AssertionError:
        probe = await page.locator("platform-map").first.evaluate(
            """(el) => ({
                q: el._searchQuery,
                busy: el._suggestBusy,
                open: el._suggestOpen,
                items: el._suggestItems ? el._suggestItems.length : -1,
                lastResult: el._suggestOp ? el._suggestOp.lastResult : null,
                lastError: el._suggestOp ? String(el._suggestOp.lastError ?? null) : 'no-op',
            })"""
        )
        raise AssertionError(f"suggest empty: {probe}")
    await suggest_item.dispatch_event("mousedown")

    await expect(search_input).not_to_have_value("Тверская", timeout=10_000)
    pin_ready = await page.locator("platform-map").first.evaluate(
        """(el) => {
            const s = el.getMap().getSource('pm-search-pin');
            const d = s ? s.serialize().data : null;
            return !!(d && d.features && d.features.length === 1);
        }"""
    )
    assert pin_ready, "пин поиска не появился на карте"
    await page.wait_for_timeout(900)

    await scenario.step(
        "Наберите адрес и выберите подсказку",
        page,
        screenshot_name="address-found-pin",
        label_en="Type an address and pick a suggestion",
        details=(
            "**Демонстрация результата.** Начните печатать название "
            "улицы — например, «Тверская». Под строкой "
            "появятся подсказки из справочника: выберите нужную — карта "
            "сама перелетит к точке и поставит пин.\n\n"
            "**Итог.** Адрес найден за секунды: не нужно листать карту "
            "вручную — поиск знает справочник и приводит вас прямо к дому."
        ),
        details_en=(
            "**Result demonstration.** Start typing the address — the "
            "first letters of the street are enough. Suggestions from the "
            "directory appear under the box: pick one — the map flies to "
            "the point and drops a pin.\n\n"
            "**Summary.** The address is found in seconds: no manual map "
            "scrolling — search knows the directory and takes you "
            "straight to the building."
        ),
    )


async def _geo_nav(page: Page, index: int, *, page_selector: str) -> None:
    """Переход по пункту сайдбара geo и ожидание страницы."""
    await page.locator("geo-sidebar .nav-item").nth(index).click()
    await expect(page.locator(page_selector)).to_be_visible(timeout=30_000)


@pytest.mark.scenario(
    service="geo",
    tag="getting-started",
    doc_slug="geo-overview-tour",
    timeout_seconds=120,
    title="Знакомимся с Geo: карта, адреса, источники, лаборатории",
    description=(
        "Обзорный тур по разделам Geo: карта города, справочник адресов, "
        "источники геоданных и лаборатории маршрутов и карты."
    ),
    title_en="Meet Geo: map, addresses, sources, labs",
    description_en=(
        "A tour of the Geo sections: city map, address directory, "
        "geodata sources and the route/map labs."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_geo_overview_tour(
    scenario: ScenarioRecorder,
    ui_page_system: Page,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)
    await _GEO_UI.open(page)
    await expect(page.locator("geo-overview-page")).to_be_visible(timeout=30_000)
    await wait_geo_map_ready(page)
    await ui_wait_ws_open(page)

    await scenario.step(
        "Главная — живая карта города",
        page,
        screenshot_name="geo-map-home",
        label_en="Home — the live city map",
        details=(
            "Geo открывается картой: точки — дома из справочника адресов, "
            "линии — дороги для маршрутов. Сверху строка поиска адреса, "
            "справа — инструменты карты и легенда слоёв."
        ),
        details_en=(
            "Geo opens with a map: dots are houses from the address "
            "directory, lines are roads for routing. On top — the address "
            "search, on the right — map tools and the layer legend."
        ),
    )

    await _geo_nav(page, 1, page_selector="geo-sources-page")
    await scenario.step(
        "«Покрытие» — откуда данные",
        page,
        screenshot_name="geo-sources",
        label_en="«Coverage» — where the data comes from",
        details=(
            "Раздел «Покрытие» показывает источники геоданных: что "
            "импортировано, когда обновлялось и сколько объектов знает "
            "система. Обычно здесь ничего делать не нужно — это "
            "информационный экран для проверки свежести данных."
        ),
        details_en=(
            "The «Coverage» section shows geodata sources: what was "
            "imported, when it updated and how many objects the system "
            "knows. Usually nothing to do here — an info screen for "
            "checking data freshness."
        ),
    )

    await _geo_nav(page, 2, page_selector="geo-addresses-page")
    await expect(
        page.locator("geo-addresses-page .search-box platform-field")
    ).to_be_visible(timeout=15_000)
    await scenario.step(
        "«Адреса» — справочник компании",
        page,
        screenshot_name="geo-addresses",
        label_en="«Addresses» — the company directory",
        details=(
            "В «Адресах» живёт справочник: все дома и точки, которые "
            "система использует для поиска и маршрутов. Поиск по таблице "
            "находит адрес по названию улицы."
        ),
        details_en=(
            "«Addresses» holds the directory: every house and point the "
            "system uses for search and routing. The table search finds "
            "an address by street name."
        ),
    )

    await _geo_nav(page, 3, page_selector="geo-route-lab-page")
    await expect(
        page.locator("canvas.maplibregl-canvas").first
    ).to_be_visible(timeout=30_000)
    await scenario.step(
        "«Маршруты» — лаборатория маршрутов",
        page,
        screenshot_name="geo-route-lab",
        label_en="«Routes» — the route lab",
        details=(
            "«Маршруты» — место, где строят маршруты на карте: два клика "
            "ставят точки A и B, а система показывает дистанцию и время. "
            "Подробнее — в инструкции про маршрутную лабораторию."
        ),
        details_en=(
            "«Routes» is where routes are built on the map: two clicks "
            "set points A and B, and the system shows distance and "
            "duration. See the route lab guide for details."
        ),
    )

    await _geo_nav(page, 4, page_selector="geo-map-lab-page")
    await expect(
        page.locator("canvas.maplibregl-canvas").first
    ).to_be_visible(timeout=30_000)
    await scenario.step(
        "«Лаборатория карты» — витрина виджета",
        page,
        screenshot_name="geo-map-lab",
        label_en="«Map Lab» — the widget showcase",
        details=(
            "**Итог.** «Лаборатория карты» — демонстрация виджета карты: "
            "маркеры, кластеры и поиск в миниатюре. Теперь вы знаете все "
            "разделы Geo: карта на главной, справочник адресов, покрытие "
            "источников и две лаборатории для маршрутов и карты."
        ),
        details_en=(
            "**Summary.** «Map Lab» shows the map widget: markers, "
            "clusters and search in miniature. You now know every Geo "
            "section: map on home, address directory, source coverage "
            "and two labs for routes and the map."
        ),
    )
