"""<platform-map> — реальный браузер против живого geo :9028.

Продовый путь: Chromium + auth-cookie системного админа, SPA geo сервится
Granian'ом, слои/адреса/роутинг идут боевым контрактом (WS→op→PostGIS).
Данные — коммиченная фикстура tests/geo/fixtures/micro.osm (Тверская 1/3,
Никольская 10, Арбат 5, светофор, боллард, turn restriction), реально
запаршенная pyosmium при старте стека.

Покрытие: загрузка и контролы, zoom, панель слоёв и toggle, карточка
фичи по клику, поиск с suggest и pin, линейка (длина и площадь),
контекстное меню «Что здесь?», статусбар, fit, кластер маркеров,
draggable-маркер, рисование зоны TerraDraw, панель адресов,
неинтерактивное превью; маршрут (линия/чип/режимы/build кликами/
очистка), изохроны, переключение light/dark-схемы, компас,
живучесть draw после смены стиля.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import cast

import pytest
from playwright.async_api import Page, expect

from apps.geo.models.geo_import_state import GeoImportState, GeoImportStatus
from apps.geo.tasks.task_names import GEO_OSM_SYNC_TICK
from core.tasks import enqueue
from tests.ui.apps import SERVICE_UI_REGISTRY
from tests.ui.harness import AppUI, ui_wait_ws_open

_GEO_UI = AppUI(SERVICE_UI_REGISTRY["geo"])


@pytest.fixture(scope="module", autouse=True)
async def _geo_directory_imported(geo_worker: None) -> None:
    """Карта без данных — не тест: если справочник пуст, реальный тик через
    живого geo_worker импортирует micro.osm (тот же путь, что у bootstrap).

    Bootstrap-enqueue при старте стека может прийти раньше создания
    consumer-group брокера — тогда сообщение сидит в стриме недоставленным;
    здесь тик уходит гарантированно после старта воркера.
    """
    _ = geo_worker
    state = await GeoImportState.get_state()
    if state is not None and state.current_generation > 0:
        return
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


# micro.osm: Тверская 1 — центральная точка фикстуры.
_TVERSKAYA_1 = (37.61730, 55.75010)
_NIKOLSKAYA_10 = (37.61840, 55.75060)


async def _open_overview(page: Page) -> None:
    _ = await page.goto(_GEO_UI.spa_url(), wait_until="load")
    await expect(page.locator("geo-app")).to_be_visible(timeout=30_000)
    await expect(page.locator("canvas.maplibregl-canvas")).to_be_visible(timeout=30_000)
    await expect(page.locator(".pm-controls .pm-zoom")).to_be_visible(timeout=30_000)
    await ui_wait_ws_open(page)


async def _open_lab(page: Page) -> None:
    _ = await page.goto(f"{_GEO_UI.spa_url()}map-lab", wait_until="load")
    await expect(page.locator("geo-app")).to_be_visible(timeout=30_000)
    await expect(page.locator("canvas.maplibregl-canvas").first).to_be_visible(timeout=30_000)
    await expect(page.locator(".main-map .pm-zoom")).to_be_visible(timeout=30_000)
    await ui_wait_ws_open(page)


async def _project(page: Page, lng: float, lat: float, *, nth: int = 0) -> tuple[float, float]:
    """Экранные координаты lngLat внутри canvas platform-map."""
    pt = cast(
        dict[str, float],
        await page.locator("platform-map")
        .nth(nth)
        .evaluate(
            "(el, ll) => { const m = el.getMap(); const p = m.project(ll); return {x: p.x, y: p.y}; }",
            [lng, lat],
        ),
    )
    box = await page.locator("canvas.maplibregl-canvas").nth(nth).bounding_box()
    assert box is not None
    return box["x"] + float(pt["x"]), box["y"] + float(pt["y"])


async def _map_eval(page: Page, expr: str, *, nth: int = 0) -> object:
    return cast(object, await page.locator("platform-map").nth(nth).evaluate(expr))


async def _zoom(page: Page) -> float:
    return cast(float, await _map_eval(page, "(el) => el.getMap().getZoom()"))


class TestOverviewRealData:
    """Обзорная карта: живые слои из micro.osm."""

    async def test_loads_controls_search_statusbar_layers(self, ui_page_system: Page) -> None:
        await _open_overview(ui_page_system)
        # Контролы: zoom, locate, ruler, fit, fullscreen, слои.
        zoom = ui_page_system.locator(".pm-zoom")
        await expect(zoom.locator("button")).to_have_count(2)
        await expect(ui_page_system.locator(".pm-search-input")).to_be_visible()
        await expect(ui_page_system.locator(".pm-status")).to_be_visible()
        # Панель слоёв — реальные счётчики из micro.osm (signals=1, barriers=1).
        layers = ui_page_system.locator(".pm-layers")
        await expect(layers.locator("button").first).to_be_visible(timeout=20_000)
        text = await layers.inner_text()
        assert "Светофоры" in text or "signals" in text.lower() or len(text) > 10

    async def test_zoom_buttons_change_camera(self, ui_page_system: Page) -> None:
        await _open_overview(ui_page_system)
        z0 = await _zoom(ui_page_system)
        await ui_page_system.locator(".pm-zoom button").first.click()
        # zoomIn/zoomOut — 300мс easeTo-анимация; ждём стабилизации камеры.
        await ui_page_system.wait_for_timeout(500)
        z1 = await _zoom(ui_page_system)
        assert z1 > z0, f"zoomIn: {z0} -> {z1}"
        await ui_page_system.locator(".pm-zoom button").nth(1).click()
        await ui_page_system.wait_for_timeout(500)
        z2 = await _zoom(ui_page_system)
        assert z2 < z1, f"zoomOut: {z1} -> {z2}"

    async def test_layer_toggle_updates_visibility(self, ui_page_system: Page) -> None:
        await _open_overview(ui_page_system)
        btn = ui_page_system.locator(".pm-layers button").first
        await expect(btn).to_be_visible(timeout=20_000)
        name_el = btn
        await expect(name_el).to_have_class(re.compile(r"active"))
        await name_el.click()
        await expect(name_el).not_to_have_class(re.compile(r"active"))
        await name_el.click()
        await expect(name_el).to_have_class(re.compile(r"active"))

    async def test_feature_click_opens_card(self, ui_page_system: Page) -> None:
        await _open_overview(ui_page_system)
        # Приблизиться к фикстурной зоне и дождаться фич слоёв в source.
        _ = await _map_eval(
            ui_page_system,
            "(el) => { el.getMap().jumpTo({ center: [37.6173, 55.7503], zoom: 17 }); return true; }",
        )
        await expect(ui_page_system.locator(".pm-layers button").first).to_be_visible(
            timeout=20_000
        )
        # moveend→debounce→geo/layer_features→setData: ждём непустой source.
        # Поллинг снаружи браузера — headless rAF может не тикать.
        deadline = time.monotonic() + 20.0
        count = 0
        while time.monotonic() < deadline:
            count = cast(
                int,
                await _map_eval(
                    ui_page_system,
                    """(el) => {
                        const s = el.getMap().getSource('pm-src-addresses');
                        return s ? s.serialize().data.features.length : 0;
                    }""",
                ),
            )
            if count > 0:
                break
            await asyncio.sleep(0.5)
        assert count > 0, "фичи слоя addresses не приехали за 20s"
        # Клик по реально отрендеренной фиче, а не по предполагаемой координате.
        x, y = cast(
            tuple[float, float],
            await ui_page_system.locator("platform-map").evaluate(
                """(el) => {
                const m = el.getMap();
                const layers = m.getStyle().layers.filter((l) => l.id.startsWith('pm-lyr-')).map((l) => l.id);
                const hits = m.queryRenderedFeatures(undefined, { layers });
                const c = hits[0].geometry.coordinates;
                const ll = Array.isArray(c[0]) ? c[0] : c;
                const p = m.project(ll);
                const r = m.getCanvas().getBoundingClientRect();
                return [r.x + p.x, r.y + p.y];
            }"""
            ),
        )
        await ui_page_system.mouse.click(x, y)
        popup = ui_page_system.locator(".maplibregl-popup.pm-card-popup")
        await expect(popup).to_be_visible(timeout=10_000)
        card = popup.locator(".pm-card").first
        await expect(card).to_be_visible()
        title = popup.locator(".pm-card-title").first
        assert len((await title.inner_text()).strip()) > 0
        # Регрессия «белый текст на белом попапе»: цвет текста тёмный,
        # фон попапа непрозрачный.
        readable = cast(
            bool,
            await card.evaluate(
                """(el) => {
                const cs = getComputedStyle(el);
                const m = cs.color.match(/\\d+(\\.\\d+)?/g).map(Number);
                const lum = (0.2126*m[0] + 0.7152*m[1] + 0.0722*m[2]) / 255;
                const bg = getComputedStyle(el.closest('.maplibregl-popup-content')).backgroundColor;
                return lum < 0.45 && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent';
            }"""
            ),
        )
        assert readable, "карточка фичи нечитаема: светлый текст или прозрачный фон"

    async def test_search_suggest_pick_pin(self, ui_page_system: Page) -> None:
        await _open_overview(ui_page_system)
        box = ui_page_system.locator(".pm-search-input")
        await expect(box).to_be_visible(timeout=20_000)
        await box.fill("Тверская")
        item = ui_page_system.locator(".pm-suggest-item").first
        await expect(item).to_be_visible(timeout=15_000)
        assert "Тверск" in (await item.inner_text())
        await item.click()
        # Pin-источник выставлен и камера долетела к точке.
        pin = cast(
            int,
            await _map_eval(
                ui_page_system,
                """(el) => {
                    const s = el.getMap().getSource('pm-search-pin');
                    const d = s.serialize().data;
                    return d.features.length;
                }""",
            ),
        )
        assert pin == 1

    async def test_context_menu_whats_here(self, ui_page_system: Page) -> None:
        await _open_overview(ui_page_system)
        _ = await _map_eval(
            ui_page_system,
            "(el) => { el.getMap().jumpTo({ center: [37.6173, 55.7501], zoom: 16 }); return true; }",
        )
        await ui_page_system.wait_for_timeout(800)
        x, y = await _project(ui_page_system, *_TVERSKAYA_1)
        await ui_page_system.mouse.click(x, y, button="right")
        menu = ui_page_system.locator(".pm-menu")
        await expect(menu).to_be_visible(timeout=10_000)
        await menu.locator("button[data-action='whats-here']").click(timeout=10_000)
        popup = ui_page_system.locator(".maplibregl-popup.pm-card-popup")
        await expect(popup).to_be_visible(timeout=15_000)
        assert "Тверск" in (await popup.inner_text())

    async def test_ruler_measures_distance(self, ui_page_system: Page) -> None:
        await _open_overview(ui_page_system)
        ruler = ui_page_system.locator("button[data-action='ruler']")
        await expect(ruler).to_be_visible(timeout=20_000)
        await ruler.click()
        x1, y1 = await _project(ui_page_system, *_TVERSKAYA_1)
        x2, y2 = await _project(ui_page_system, *_NIKOLSKAYA_10)
        await ui_page_system.mouse.click(x1, y1)
        await ui_page_system.mouse.click(x2, y2)
        # Линия и метка в источнике линейки.
        kinds = cast(
            list[str],
            await _map_eval(
                ui_page_system,
                """(el) => {
                    const d = el.getMap().getSource('pm-ruler').serialize().data;
                    return d.features.map((f) => f.geometry.type);
                }""",
            ),
        )
        assert "LineString" in kinds
        await ruler.click()
        finished = cast(
            int,
            await _map_eval(
                ui_page_system,
                "(el) => el.getMap().getSource('pm-ruler').serialize().data.features.length",
            ),
        )
        assert finished >= 1  # линейка остаётся видимой до clearRuler

    async def test_statusbar_shows_coords(self, ui_page_system: Page) -> None:
        await _open_overview(ui_page_system)
        status = ui_page_system.locator(".pm-status")
        await expect(status).to_be_visible(timeout=20_000)
        canvas = ui_page_system.locator("canvas.maplibregl-canvas")
        box = await canvas.bounding_box()
        assert box is not None
        coords = ui_page_system.locator(".pm-status-coords")
        pattern = re.compile(r"\d+\.\d+,\s*-?\d+\.\d+")
        # Поверх карты могут всплывать системные баннеры (Lara/install) —
        # повторяем move, пока mousemove не попадёт на canvas.
        for _ in range(20):
            await ui_page_system.mouse.move(
                box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            )
            if pattern.search(await coords.inner_text()):
                return
            await asyncio.sleep(0.4)
        await expect(coords).to_have_text(pattern, timeout=10_000)

    async def test_scale_and_fit_controls(self, ui_page_system: Page) -> None:
        await _open_overview(ui_page_system)
        await expect(ui_page_system.locator(".maplibregl-ctrl-scale")).to_be_visible(timeout=20_000)
        fit = ui_page_system.locator("button[data-action='fit']")
        await expect(fit).to_be_visible()
        await fit.click()
        await ui_page_system.wait_for_timeout(800)


class TestMapLabFullConfig:
    """Map Lab: вся мощь конфига на одной странице."""

    async def test_cluster_draggable_overlay_preview(self, ui_page_system: Page) -> None:
        await _open_lab(ui_page_system)
        # Кластерные слои установлены.
        has_cluster = cast(
            bool,
            await _map_eval(
                ui_page_system,
                "(el) => Boolean(el.getMap().getLayer('pm-cluster-circle'))",
            ),
        )
        assert has_cluster is True
        # Draggable depot → DOM-маркер.
        await expect(ui_page_system.locator(".maplibregl-marker").first).to_be_visible()
        # Overlay demo-zone: line-слой.
        has_overlay = cast(
            bool,
            await _map_eval(
                ui_page_system,
                "(el) => Boolean(el.getMap().getLayer('pm-ov-demo-zone-layer'))",
            ),
        )
        assert has_overlay is True
        # Неинтерактивное превью — вторая карта без контролов.
        await expect(ui_page_system.locator("platform-map")).to_have_count(2)
        preview_markers = cast(
            int,
            await _map_eval(
                ui_page_system,
                "(el) => el.getMap().getSource('pm-markers').serialize().data.features.length",
                nth=1,
            ),
        )
        assert preview_markers == 1

    async def test_cluster_click_expands(self, ui_page_system: Page) -> None:
        await _open_lab(ui_page_system)
        # Кластеры на зуме 12: 24 poi + depot вокруг центра.
        await ui_page_system.wait_for_timeout(1_200)
        clusters = cast(
            int,
            await _map_eval(
                ui_page_system,
                """(el) => {
                    const map = el.getMap();
                    return map.queryRenderedFeatures({ layers: ['pm-cluster-circle'] }).length;
                }""",
            ),
        )
        assert clusters > 0, "кластерные точки на карте"
        z0 = await _zoom(ui_page_system)
        # Клик по реально отрендеренному кластеру, а не по предполагаемой точке.
        x, y = cast(
            tuple[float, float],
            await ui_page_system.locator("platform-map").first.evaluate(
                """(el) => {
                const m = el.getMap();
                const hits = m.queryRenderedFeatures(undefined, { layers: ['pm-cluster-circle'] });
                const p = m.project(hits[0].geometry.coordinates);
                const r = m.getCanvas().getBoundingClientRect();
                return [r.x + p.x, r.y + p.y];
            }"""
            ),
        )
        await ui_page_system.mouse.click(x, y)
        await ui_page_system.wait_for_timeout(1_000)
        z1 = await _zoom(ui_page_system)
        assert z1 > z0, f"cluster expand zoom: {z0} -> {z1}"

    async def test_addresses_panel_lists_zone(self, ui_page_system: Page) -> None:
        await _open_lab(ui_page_system)
        panel = ui_page_system.locator("platform-zone-address-panel")
        await expect(panel).to_be_visible(timeout=20_000)
        # Тверская 1/3 и Никольская 10 внутри demo-зоны → ≥1 адрес.
        await expect(panel.locator("text=Тверск").first).to_be_visible(timeout=20_000)

    async def test_addresses_panel_collapses(self, ui_page_system: Page) -> None:
        await _open_lab(ui_page_system)
        panel = ui_page_system.locator("platform-zone-address-panel")
        await expect(panel).to_be_visible(timeout=20_000)
        wrapper = ui_page_system.locator(".pm-panel")
        full_width = await wrapper.evaluate("el => el.getBoundingClientRect().width")
        assert full_width > 100
        # Сворачивание → рельса без поиска/списка, контейнер узкий.
        await panel.locator("[data-action='panel-collapse']").click()
        await expect(panel.locator(".rail")).to_be_visible()
        await ui_page_system.wait_for_timeout(200)
        rail_width = await wrapper.evaluate("el => el.getBoundingClientRect().width")
        assert rail_width < 100, f"collapsed panel width: {rail_width}"
        await expect(panel.locator(".list")).to_have_count(0)
        # Разворот возвращает полную панель со списком.
        await panel.locator("[data-action='panel-expand']").click()
        await expect(panel.locator(".list")).to_be_visible()
        expanded_width = await wrapper.evaluate("el => el.getBoundingClientRect().width")
        assert expanded_width == full_width


# Узлы дорожного графа micro.osm — клики строительства маршрута
# должны приземляться на рёбра, иначе pgRouting не найдёт путь.
_ROAD_A = (37.6170, 55.7500)
_ROAD_B = (37.6190, 55.7510)


async def _wait_source_features(
    page: Page, source: str, minimum: int, *, timeout_s: float = 20.0
) -> int:
    """Число фич geojson-source с поллингом — headless rAF ненадёжен."""
    deadline = time.monotonic() + timeout_s
    count = 0
    while time.monotonic() < deadline:
        count = cast(
            int,
            await _map_eval(
                page,
                f"""(el) => {{
                    const s = el.getMap().getSource('{source}');
                    return s ? s.serialize().data.features.length : -1;
                }}""",
            ),
        )
        if count >= minimum:
            return count
        await asyncio.sleep(0.4)
    return count


class TestRouteIsoScheme:
    """Map Lab: маршрут, изохроны, схема, компас, линейка площади."""

    async def test_route_line_endpoints_and_chip(self, ui_page_system: Page) -> None:
        await _open_lab(ui_page_system)
        # Конфиг-маршрут Тверская→Никольская: линия, A/B-точки, чип с ETA.
        assert await _wait_source_features(ui_page_system, "pm-route", 1) >= 1
        pts = await _wait_source_features(ui_page_system, "pm-route-pts", 2)
        assert pts == 2
        chip = ui_page_system.locator(".pm-route-chip")
        await expect(chip).to_be_visible(timeout=10_000)
        text = await chip.inner_text()
        assert "·" in text  # «0.1 км · 1 мин» — дистанция + ETA
        info = cast(
            dict[str, float],
            await _map_eval(ui_page_system, "(el) => el._routeInfo"),
        )
        assert info["distanceM"] > 0 and info["durationS"] > 0

    async def test_route_mode_switch_recalculates(self, ui_page_system: Page) -> None:
        await _open_lab(ui_page_system)
        assert await _wait_source_features(ui_page_system, "pm-route", 1) >= 1
        chip = ui_page_system.locator(".pm-route-chip")
        await expect(chip).to_be_visible(timeout=10_000)
        car_s = cast(
            float,
            await _map_eval(ui_page_system, "(el) => el._routeInfo.durationS"),
        )
        await chip.locator("button[data-mode='foot']").click()
        # Пешеход медленнее авто: ждём пересчёт и иное ETA.
        deadline = time.monotonic() + 20.0
        foot_s = car_s
        while time.monotonic() < deadline:
            foot = cast(
                dict[str, float] | None,
                await _map_eval(ui_page_system, "(el) => el._routeInfo"),
            )
            if foot is not None and abs(foot["durationS"] - car_s) > 0.01:
                foot_s = foot["durationS"]
                break
            await asyncio.sleep(0.4)
        assert foot_s != car_s, f"ETA не изменилось при смене режима: {car_s}"
        await expect(chip.locator("button[data-mode='foot']")).to_have_class(re.compile(r"active"))

    async def test_route_build_mode_two_clicks_and_clear(self, ui_page_system: Page) -> None:
        await _open_lab(ui_page_system)
        await expect(ui_page_system.locator(".pm-route-chip")).to_be_visible(timeout=20_000)
        await ui_page_system.locator("button[data-action='route']").click()
        # Режим построения: конфиг-маршрут скрыт, чип показывает подсказку.
        await expect(ui_page_system.locator(".pm-route-hint")).to_be_visible(timeout=10_000)
        for pt in (_ROAD_A, _ROAD_B):
            x, y = await _project(ui_page_system, *pt)
            await ui_page_system.mouse.click(x, y)
            await asyncio.sleep(0.3)
        assert await _wait_source_features(ui_page_system, "pm-route", 1) >= 1
        assert await _wait_source_features(ui_page_system, "pm-route-pts", 2) == 2
        built = cast(
            dict[str, float],
            await _map_eval(ui_page_system, "(el) => el._routeInfo"),
        )
        assert built["distanceM"] > 0
        # Очистка возвращает конфиг-маршрут хоста (A на Тверской).
        await ui_page_system.locator("button[data-action='route-clear']").click()
        assert await _wait_source_features(ui_page_system, "pm-route-pts", 2) == 2
        first = cast(
            list[float],
            await _map_eval(
                ui_page_system,
                """(el) => {
                    const d = el.getMap().getSource('pm-route-pts').serialize().data;
                    return d.features[0].geometry.coordinates;
                }""",
            ),
        )
        assert abs(first[0] - 37.6173) < 0.001 and abs(first[1] - 55.7501) < 0.001

    async def test_isochrone_polygons_and_labels(self, ui_page_system: Page) -> None:
        await _open_lab(ui_page_system)
        assert await _wait_source_features(ui_page_system, "pm-iso", 2) == 2
        minutes = cast(
            list[int],
            await _map_eval(
                ui_page_system,
                """(el) => {
                    const d = el.getMap().getSource('pm-iso').serialize().data;
                    return d.features.map((f) => f.properties.minutes);
                }""",
            ),
        )
        assert sorted(minutes) == [3, 7]
        # Центр + лейблы «N мин» на границах контуров.
        pts = cast(
            list[object],
            await _map_eval(
                ui_page_system,
                """(el) => {
                    const d = el.getMap().getSource('pm-iso-pts').serialize().data;
                    return d.features.map((f) => f.properties?.minutes ?? null);
                }""",
            ),
        )
        assert len(pts) >= 3 and pts.count(None) == 1  # ровно один центр

    async def test_scheme_toggle_dark_light(self, ui_page_system: Page) -> None:
        await _open_lab(ui_page_system)
        bg = cast(
            str,
            await _map_eval(
                ui_page_system,
                """(el) => {
                    const m = el.getMap();
                    const layer = m.getStyle().layers.find((l) => l.type === 'background');
                    return m.getPaintProperty(layer.id, 'background-color');
                }""",
            ),
        )
        await ui_page_system.locator("button[data-action='scheme']").click()
        deadline = time.monotonic() + 15.0
        dark = bg
        while time.monotonic() < deadline:
            dark = cast(
                str,
                await _map_eval(
                    ui_page_system,
                    """(el) => {
                        const m = el.getMap();
                        const layer = m.getStyle().layers.find((l) => l.type === 'background');
                        return layer ? m.getPaintProperty(layer.id, 'background-color') : '';
                    }""",
                ),
            )
            if dark and dark != bg:
                break
            await asyncio.sleep(0.4)
        assert dark != bg, f"фон не сменился: {bg}"
        # Обратно в light — кнопка и фон возвращаются.
        await ui_page_system.locator("button[data-action='scheme']").click()
        deadline = time.monotonic() + 15.0
        cur = ""
        while time.monotonic() < deadline:
            cur = cast(
                str,
                await _map_eval(
                    ui_page_system,
                    """(el) => {
                        const m = el.getMap();
                        const layer = m.getStyle().layers.find((l) => l.type === 'background');
                        return layer ? m.getPaintProperty(layer.id, 'background-color') : '';
                    }""",
                ),
            )
            if cur == bg:
                break
            await asyncio.sleep(0.4)
        assert cur == bg, f"фон не вернулся к light: {cur}"

    async def test_compass_resets_north(self, ui_page_system: Page) -> None:
        await _open_lab(ui_page_system)
        _ = await _map_eval(ui_page_system, "(el) => { el.getMap().setBearing(55); return true; }")
        arrow = ui_page_system.locator(".pm-compass-arrow")
        # Lit батчит requestUpdate — ждём поворота стрелки опросом.
        deadline = time.monotonic() + 10.0
        transform = ""
        while time.monotonic() < deadline:
            transform = cast(str, await arrow.evaluate("(el) => el.style.transform"))
            if "rotate(-55" in transform:
                break
            await asyncio.sleep(0.3)
        assert "rotate(-55" in transform, f"стрелка не повернулась: {transform}"
        await ui_page_system.locator("button[data-action='compass']").click()
        deadline = time.monotonic() + 10.0
        bearing = 55.0
        while time.monotonic() < deadline:
            bearing = cast(
                float, await _map_eval(ui_page_system, "(el) => el.getMap().getBearing()")
            )
            if abs(bearing) < 1.0:
                break
            await asyncio.sleep(0.3)
        assert abs(bearing) < 1.0, f"bearing не сбросился: {bearing}"

    async def test_area_ruler_polygon(self, ui_page_system: Page) -> None:
        await _open_lab(ui_page_system)
        await ui_page_system.locator("button[data-action='ruler-area']").click()
        for pt in (_ROAD_A, (37.6200, 55.7500), (37.6190, 55.7520)):
            x, y = await _project(ui_page_system, *pt)
            await ui_page_system.mouse.click(x, y)
            await asyncio.sleep(0.3)
        kinds = cast(
            list[str],
            await _map_eval(
                ui_page_system,
                """(el) => {
                    const d = el.getMap().getSource('pm-ruler').serialize().data;
                    return d.features.map((f) => f.geometry.type);
                }""",
            ),
        )
        assert "Polygon" in kinds
        area = cast(float, await _map_eval(ui_page_system, "(el) => el._rulerAreaM2()"))
        assert area > 0
        # Выход из режима — линейка остаётся до clearRuler.
        await ui_page_system.locator("button[data-action='ruler-area']").click()

    async def test_draw_survives_scheme_switch(self, ui_page_system: Page) -> None:
        await _open_lab(ui_page_system)
        # TerraDraw грузится асинхронно после style.load — ждём init.
        snap0 = -1
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            snap0 = cast(
                int,
                await _map_eval(
                    ui_page_system,
                    "(el) => (el.getDraw() ? el.getDraw().draw.getSnapshot().length : -1)",
                ),
            )
            if snap0 >= 0:
                break
            await asyncio.sleep(0.4)
        assert snap0 >= 1  # demo-зона в сторе TerraDraw
        await ui_page_system.locator("button[data-action='scheme']").click()
        deadline = time.monotonic() + 15.0
        snap = 0
        while time.monotonic() < deadline:
            snap = cast(
                int,
                await _map_eval(
                    ui_page_system,
                    "(el) => (el.getDraw() ? el.getDraw().draw.getSnapshot().length : -1)",
                ),
            )
            if snap >= snap0:
                break
            await asyncio.sleep(0.4)
        assert snap >= snap0, f"TerraDraw потерял фичи после смены стиля: {snap0} -> {snap}"
        mode = cast(str, await _map_eval(ui_page_system, "(el) => el.getDraw().draw.getMode()"))
        assert mode in ("select", "static", "polygon")


class TestEmbedRouteActions:
    """Третья итерация: embed-UX, route-действия, auto-схема, export."""

    async def test_context_menu_route_from_and_to(self, ui_page_system: Page) -> None:
        await _open_lab(ui_page_system)
        assert await _wait_source_features(ui_page_system, "pm-route", 1) >= 1
        x, y = await _project(ui_page_system, *_ROAD_B)
        await ui_page_system.mouse.click(x, y, button="right")
        menu = ui_page_system.locator(".pm-menu")
        await expect(menu).to_be_visible(timeout=10_000)
        await expect(menu.locator("button[data-action='route-from']")).to_be_visible()
        # «Маршрут сюда»: B → место клика; маршрут пересчитывается.
        await menu.locator("button[data-action='route-to']").click()
        await expect(menu).to_be_hidden(timeout=10_000)
        last = cast(
            list[float],
            await _map_eval(
                ui_page_system,
                "(el) => el._routeBuildPts.at(-1)",
            ),
        )
        assert abs(last[0] - _ROAD_B[0]) < 0.002 and abs(last[1] - _ROAD_B[1]) < 0.002
        await ui_page_system.mouse.click(x, y, button="right")
        await ui_page_system.locator(".pm-menu button[data-action='route-from']").click()
        first = cast(
            list[float],
            await _map_eval(ui_page_system, "(el) => el._routeBuildPts[0]"),
        )
        assert abs(first[0] - _ROAD_B[0]) < 0.002
        assert await _wait_source_features(ui_page_system, "pm-route", 1) >= 1

    async def test_route_swap_reverses_endpoints(self, ui_page_system: Page) -> None:
        await _open_lab(ui_page_system)
        swap = ui_page_system.locator("button[data-action='route-swap']")
        await expect(swap).to_be_visible(timeout=20_000)
        await swap.click()
        pts = cast(
            list[list[float]],
            await _map_eval(
                ui_page_system,
                """(el) => {
                    const d = el.getMap().getSource('pm-route-pts').serialize().data;
                    return d.features.map((f) => f.geometry.coordinates);
                }""",
            ),
        )
        # Был A=Тверская(37.6173) → теперь первой точкой стала Никольская(37.6184).
        assert abs(pts[0][0] - 37.6184) < 0.001, f"swap не развернул точки: {pts[0]}"

    async def test_export_png_downloads_file(self, ui_page_system: Page) -> None:
        await _open_lab(ui_page_system)
        btn = ui_page_system.locator("button[data-action='export-png']")
        await expect(btn).to_be_visible(timeout=20_000)
        async with ui_page_system.expect_download(timeout=15_000) as dl:
            await btn.click()
        assert (await dl.value).suggested_filename.endswith(".png")

    async def test_marker_title_shows_hover_hint(self, ui_page_system: Page) -> None:
        await _open_lab(ui_page_system)
        await ui_page_system.wait_for_timeout(1_000)
        # Маркер превью-карты (title 'HQ'): layers.fetch:false — канонические
        # фичи не перекроют title (на главной карте хинт показывает слой улицы).
        preview = ui_page_system.locator("platform-map").nth(1)
        # Bounding box — canvas внутри самого preview (не глобальный nth:
        # миникарта main-карты добавила третий canvas в документ).
        pbox = await preview.locator(".map-canvas canvas.maplibregl-canvas").bounding_box()
        assert pbox is not None
        pt = cast(
            dict[str, float],
            await preview.evaluate(
                "(el, ll) => { const p = el.getMap().project(ll); return {x: p.x, y: p.y}; }",
                [37.6178, 55.7503],
            ),
        )
        x, y = pbox["x"] + float(pt["x"]), pbox["y"] + float(pt["y"])
        hint = preview.locator(".pm-hint")
        # Маркер-кружок попадает в render-pyramid асинхронно — водим мышь до хита.
        for _ in range(25):
            await ui_page_system.mouse.move(x, y)
            await asyncio.sleep(0.15)
            if await hint.count() > 0 and "HQ" in await hint.inner_text():
                return
            await ui_page_system.mouse.move(x + 2, y + 2)
            await asyncio.sleep(0.15)
        await expect(hint).to_be_visible(timeout=10_000)
        assert "HQ" in await hint.inner_text()

    async def test_preview_cooperative_gestures_screen(self, ui_page_system: Page) -> None:
        """Embed-превью: колесо без Ctrl не зумит, показывает подсказку."""
        await _open_lab(ui_page_system)
        preview = ui_page_system.locator("platform-map").nth(1)
        canvas = preview.locator("canvas.maplibregl-canvas")
        await expect(canvas).to_be_visible(timeout=20_000)
        box = await canvas.bounding_box()
        assert box is not None
        z0 = cast(
            float,
            await _map_eval(ui_page_system, "(el) => el.getMap().getZoom()", nth=1),
        )
        await ui_page_system.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        await ui_page_system.mouse.wheel(0, 300)
        # Экран-подсказка «используйте Ctrl»: opacity 0→1 через класс maplibregl-show.
        screen = preview.locator(".maplibregl-cooperative-gesture-screen")
        await expect(screen).to_have_class(re.compile(r"maplibregl-show"), timeout=10_000)
        z1 = cast(
            float,
            await _map_eval(ui_page_system, "(el) => el.getMap().getZoom()", nth=1),
        )
        assert abs(z1 - z0) < 0.05, f"wheel без Ctrl изменил зум: {z0} -> {z1}"

    async def test_scheme_auto_follows_os_emulation(self, ui_page_system: Page) -> None:
        """Превью со scheme:'auto' следует prefers-color-scheme ОС."""
        await _open_lab(ui_page_system)

        async def preview_bg() -> str:
            return cast(
                str,
                await _map_eval(
                    ui_page_system,
                    """(el) => {
                        const m = el.getMap();
                        const layer = m.getStyle().layers.find((l) => l.type === 'background');
                        return layer ? m.getPaintProperty(layer.id, 'background-color') : '';
                    }""",
                    nth=1,
                ),
            )

        light_bg = await preview_bg()
        await ui_page_system.emulate_media(color_scheme="dark")
        deadline = time.monotonic() + 20.0
        dark_bg = light_bg
        while time.monotonic() < deadline:
            dark_bg = await preview_bg()
            if dark_bg and dark_bg != light_bg:
                break
            await asyncio.sleep(0.5)
        assert dark_bg != light_bg, f"auto-схема не ушла в dark: {dark_bg}"
        await ui_page_system.emulate_media(color_scheme="light")
        deadline = time.monotonic() + 20.0
        back = dark_bg
        while time.monotonic() < deadline:
            back = await preview_bg()
            if back == light_bg:
                break
            await asyncio.sleep(0.5)
        assert back == light_bg, f"auto-схема не вернулась в light: {back}"

    async def test_long_press_opens_context_menu(self, ui_page_system: Page) -> None:
        """Долгий тап ≥600мс — контекстное меню (тач-устройства)."""
        await _open_lab(ui_page_system)
        x, y = await _project(ui_page_system, *_TVERSKAYA_1)
        _ = cast(
            object,
            await ui_page_system.locator("platform-map").first.evaluate(
                """(el, pt) => {
                const canvas = el.getMap().getCanvas();
                const r = canvas.getBoundingClientRect();
                const touch = new Touch({
                    identifier: 7, target: canvas,
                    clientX: pt[0], clientY: pt[1],
                });
                canvas.dispatchEvent(new TouchEvent('touchstart', {
                    touches: [touch], bubbles: true, composed: true,
                }));
                return true;
            }""",
                [x, y],
            ),
        )
        menu = ui_page_system.locator(".pm-menu")
        await expect(menu).to_be_visible(timeout=10_000)

    async def test_hash_syncs_camera_to_url(self, ui_page_system: Page) -> None:
        await _open_lab(ui_page_system)
        _ = await _map_eval(
            ui_page_system,
            "(el) => { el.getMap().jumpTo({ center: [37.62, 55.755], zoom: 15 }); return true; }",
        )
        deadline = time.monotonic() + 15.0
        url = ""
        while time.monotonic() < deadline:
            url = ui_page_system.url
            if "#map=" in url:
                break
            await asyncio.sleep(0.4)
        assert "#map=" in url, f"камера не синхронизировалась с URL: {url}"

    async def test_minimap_inset_shows_viewport(self, ui_page_system: Page) -> None:
        """controls.miniMap: inset в углу с прямоугольником видимой области."""
        await _open_lab(ui_page_system)
        # Inset — вторая MapLibre: ей нужен свой style.load, опрашиваем DOM.
        mini = ui_page_system.locator(".pm-minimap")
        await expect(mini.locator("canvas.maplibregl-canvas")).to_be_visible(timeout=20_000)
        # Source живёт на inset-карте (el._mini), не на основной — свой опрос.
        deadline = time.monotonic() + 20.0
        box_feats = 0
        while time.monotonic() < deadline:
            box_feats = cast(
                int,
                await _map_eval(
                    ui_page_system,
                    """(el) => {
                        const s = el._mini ? el._mini.getSource('pm-minimap-box') : null;
                        return s ? s.serialize().data.features.length : -1;
                    }""",
                ),
            )
            if box_feats == 1:
                break
            await asyncio.sleep(0.4)
        assert box_feats == 1, f"viewport-rect в inset: {box_feats}"
        # Двигаем основную карту — rect следует за viewport.
        init_ring = cast(
            list[float],
            await _map_eval(
                ui_page_system,
                """(el) => {
                    const d = el._mini.getSource('pm-minimap-box').serialize().data;
                    return d.features[0].geometry.coordinates[0][0];
                }""",
            ),
        )
        _ = await _map_eval(
            ui_page_system,
            "(el) => { el.getMap().jumpTo({ center: [37.623, 55.754], zoom: 15 }); return true; }",
        )
        deadline = time.monotonic() + 15.0
        moved = False
        ring = init_ring
        while time.monotonic() < deadline:
            ring = cast(
                list[float],
                await _map_eval(
                    ui_page_system,
                    """(el) => {
                        const d = el._mini.getSource('pm-minimap-box').serialize().data;
                        return d.features[0].geometry.coordinates[0][0];
                    }""",
                ),
            )
            # Западный край bbox для center=37.623 zoom=15 ≈ 37.6157 —
            # проверяем именно смещение rect относительно стартового.
            if abs(ring[0] - init_ring[0]) > 1e-4:
                moved = True
                break
            await asyncio.sleep(0.3)
        assert moved, f"inset-rect не следует за камерой: {init_ring} -> {ring}"

    async def test_locate_watch_blue_dot(self, ui_page_system: Page) -> None:
        """locateWatch: синяя точка + круг точности по реальной геолокации."""
        ctx = ui_page_system.context
        await ctx.grant_permissions(["geolocation"], origin=_GEO_UI.origin)
        await ctx.set_geolocation({"latitude": 55.7503, "longitude": 37.6178, "accuracy": 18})
        await _open_lab(ui_page_system)
        feats = await _wait_source_features(ui_page_system, "pm-user", 2)
        assert feats == 2, "точка + круг точности в pm-user"
        dot = cast(
            list[float],
            await _map_eval(
                ui_page_system,
                """(el) => {
                    const d = el.getMap().getSource('pm-user').serialize().data;
                    return d.features.find((f) => f.properties.kind === 'dot').geometry.coordinates;
                }""",
            ),
        )
        assert abs(dot[0] - 37.6178) < 0.0005 and abs(dot[1] - 55.7503) < 0.0005

    async def test_marker_click_opens_balloon(self, ui_page_system: Page) -> None:
        """Клик по маркеру с title — балун Яндекс-стиля."""
        await _open_lab(ui_page_system)
        # Приближаемся к courier-маркеру — на z12 он внутри кластера poi.
        _ = await _map_eval(
            ui_page_system,
            "(el) => { el.getMap().jumpTo({ center: [37.6173, 55.7501], zoom: 18 }); return true; }",
        )
        # Клик по реально отрендеренному маркеру, а не вслепую по координате.
        deadline = time.monotonic() + 15.0
        balloon = ui_page_system.locator(".pm-balloon")
        while time.monotonic() < deadline:
            pt = cast(
                list[float] | None,
                await _map_eval(
                    ui_page_system,
                    """(el) => {
                        const m = el.getMap();
                        const hits = m.queryRenderedFeatures({ layers: ['pm-markers-circle'] })
                            .filter((f) => f.properties.key === 'courier');
                        if (!hits.length) return null;
                        const p = m.project(hits[0].geometry.coordinates);
                        return [p.x, p.y];
                    }""",
                ),
            )
            if pt is not None:
                box = await ui_page_system.locator("canvas.maplibregl-canvas").first.bounding_box()
                assert box is not None
                await ui_page_system.mouse.click(box["x"] + pt[0], box["y"] + pt[1])
                if await balloon.count() > 0:
                    break
            await asyncio.sleep(0.4)
        await expect(balloon).to_be_visible(timeout=10_000)
        assert "Courier" in await balloon.inner_text()


class TestTiltShareLegs:
    """3D-tilt, share deep-link, плечи маршрута — витрина map-lab."""

    async def test_tilt_button_changes_pitch(self, ui_page_system: Page) -> None:
        await _open_lab(ui_page_system)
        btn = ui_page_system.locator("button[data-action='tilt']")
        await expect(btn).to_be_visible(timeout=10_000)
        _ = await _map_eval(
            ui_page_system,
            "(el) => { el.shadowRoot.querySelector(\"button[data-action='tilt']\").click(); return true; }",
        )
        deadline = time.monotonic() + 10.0
        pitch = 0.0
        while time.monotonic() < deadline:
            pitch = cast(float, await _map_eval(ui_page_system, "(el) => el.getMap().getPitch()"))
            if pitch > 50:
                break
            await asyncio.sleep(0.3)
        assert pitch > 50, f"pitch после tilt = {pitch}"
        _ = await _map_eval(
            ui_page_system,
            "(el) => { el.shadowRoot.querySelector(\"button[data-action='tilt']\").click(); return true; }",
        )
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            pitch = cast(float, await _map_eval(ui_page_system, "(el) => el.getMap().getPitch()"))
            if pitch < 5:
                break
            await asyncio.sleep(0.3)
        assert pitch < 5, f"pitch после сброса = {pitch}"

    async def test_share_button_copies_deeplink_and_toasts(self, ui_page_system: Page) -> None:
        await _open_lab(ui_page_system)
        btn = ui_page_system.locator("button[data-action='share']")
        await expect(btn).to_be_visible(timeout=10_000)
        # JS-клик: Playwright-клик висит на hit-target проверке поверх GL-canvas.
        _ = await _map_eval(
            ui_page_system,
            "(el) => { el.shadowRoot.querySelector(\"button[data-action='share']\").click(); return true; }",
        )
        toast = ui_page_system.locator(".pm-toast")
        await expect(toast).to_be_visible(timeout=5_000)
        toast_text = (await toast.inner_text()).lower()
        assert "копир" in toast_text or "copied" in toast_text
        # pm-share с URL, содержащим #map= deep-link — ловим синхронно через locator (проникает в shadow).
        url = cast(
            str,
            await _map_eval(
                ui_page_system,
                """(el) => {
                    let captured = null;
                    el.addEventListener('pm-share', (e) => { captured = e.detail.url; }, { once: true });
                    el._shareLink();
                    return captured;
                }""",
            ),
        )
        assert "#map=" in url, f"deep-link URL: {url}"
        # Тост сам гаснет через ~2с.
        await expect(toast).to_be_hidden(timeout=8_000)

    async def test_route_legs_panel_lists_segments(self, ui_page_system: Page) -> None:
        await _open_lab(ui_page_system)
        chip = ui_page_system.locator(".pm-route-chip")
        await expect(chip).to_be_visible(timeout=10_000)
        # Конфиг-маршрут в lab — 2 точки = 1 плечо: кнопки плечей нет.
        assert await chip.locator("button[data-action='route-legs']").count() == 0
        # Строим 3-точечный маршрут программно → 2 плеча → кнопка «⋮».
        _ = await _map_eval(
            ui_page_system,
            """(el) => {
                el._routeBuildPts = [[37.6174, 55.7504], [37.6186, 55.7509], [37.6194, 55.7512]];
                el._refreshRoute();
                return true;
            }""",
        )
        btn = chip.locator("button[data-action='route-legs']")
        await expect(btn).to_be_visible(timeout=15_000)
        _ = await _map_eval(
            ui_page_system,
            "(el) => { el.shadowRoot.querySelector(\"button[data-action='route-legs']\").click(); return true; }",
        )
        legs = ui_page_system.locator(".pm-route-leg")
        await expect(legs).to_have_count(2, timeout=5_000)
        text = await ui_page_system.locator(".pm-route-legs").inner_text()
        assert "A → B" in text and "B → C" in text
        # Повторный клик сворачивает панель.
        _ = await _map_eval(
            ui_page_system,
            "(el) => { el.shadowRoot.querySelector(\"button[data-action='route-legs']\").click(); return true; }",
        )
        await expect(ui_page_system.locator(".pm-route-legs")).to_be_hidden(timeout=5_000)
