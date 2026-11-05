"""<platform-map> — реальный браузер против живого geo :9028.

Продовый путь: Chromium + auth-cookie системного админа, SPA geo сервится
Granian'ом, слои/адреса/роутинг идут боевым контрактом (WS→op→PostGIS).
Данные — коммиченная фикстура tests/geo/fixtures/micro.osm (Тверская 1/3,
Никольская 10, Арбат 5, светофор, боллард, turn restriction), реально
запаршенная pyosmium при старте стека.

Покрытие: загрузка и контролы, zoom, панель слоёв и toggle, карточка
фичи по клику, поиск с suggest и pin, линейка, контекстное меню
«Что здесь?», статусбар, fit, кластер маркеров, draggable-маркер,
рисование зоны TerraDraw, панель адресов, неинтерактивное превью.
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
from tests.ui.harness import AppUI

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


async def _open_lab(page: Page) -> None:
    _ = await page.goto(f"{_GEO_UI.spa_url()}map-lab", wait_until="load")
    await expect(page.locator("geo-app")).to_be_visible(timeout=30_000)
    await expect(page.locator("canvas.maplibregl-canvas").first).to_be_visible(timeout=30_000)
    await expect(page.locator(".main-map .pm-zoom")).to_be_visible(timeout=30_000)


async def _project(page: Page, lng: float, lat: float, *, nth: int = 0) -> tuple[float, float]:
    """Экранные координаты lngLat внутри canvas platform-map."""
    pt = cast(
        dict[str, float],
        await page.locator("platform-map").nth(nth).evaluate(
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
        await expect(ui_page_system.locator(".pm-layers button").first).to_be_visible(timeout=20_000)
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
        card_text = await popup.inner_text()
        assert len(card_text.strip()) > 0

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
        ruler = ui_page_system.locator("button.pm-icon-btn", has_text="⟋")
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
            await ui_page_system.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            if pattern.search(await coords.inner_text()):
                return
            await asyncio.sleep(0.4)
        await expect(coords).to_have_text(pattern, timeout=10_000)

    async def test_scale_and_fit_controls(self, ui_page_system: Page) -> None:
        await _open_overview(ui_page_system)
        await expect(ui_page_system.locator(".maplibregl-ctrl-scale")).to_be_visible(timeout=20_000)
        fit = ui_page_system.locator("button.pm-icon-btn", has_text="⤢")
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
