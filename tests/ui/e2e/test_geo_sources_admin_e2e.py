"""Страница «Источники» — observability-хаб импорта + карточка админа на карте.

Продовый путь: Chromium + auth-cookie владельца компании, SPA geo на
:9028. Данные — живые geo_sources/geo_regions/geo_stats/geo_source_cursors
стека; CRUD региона и постановка импорта идут боевым контрактом
(WS→op→PostGIS/Redis-стрим geo).

Покрытие: карточки конвейера/источников/курсоров/обогащения/статистики/
регионов, запуск импорта конкретного источника, модалка редактора региона
(create → edit → remove), админ-действие «закрыть дорогу» из карточки
фичи на map-lab.
"""

from __future__ import annotations

import asyncio
import time
from typing import cast

import pytest
from playwright.async_api import Page, expect

from tests.ui.apps import SERVICE_UI_REGISTRY
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

_GEO_UI = AppUI(SERVICE_UI_REGISTRY["geo"])


async def _fill_platform_field(field, value: str) -> None:
    """Ввод в <platform-field> боевым путём: input-события → change с detail.value."""
    editable = field.locator("input:visible, textarea:visible").first
    await editable.click()
    await editable.fill(value)


async def _open_sources(page: Page) -> None:
    _ = await page.goto(f"{_GEO_UI.spa_url()}sources", wait_until="load")
    await expect(page.locator("geo-app")).to_be_visible(timeout=30_000)
    await expect(page.locator("geo-sources-page")).to_be_visible(timeout=30_000)


async def _open_map_lab(page: Page) -> None:
    _ = await page.goto(f"{_GEO_UI.spa_url()}map-lab", wait_until="load")
    await expect(page.locator("geo-app")).to_be_visible(timeout=30_000)
    await expect(page.locator("geo-map-lab-page")).to_be_visible(timeout=30_000)


@pytest.mark.scenario(
    service="geo",
    tag="sources",
    doc_slug="admin-sources-hub",
    timeout_seconds=90,
    title="Geo: хаб источников и регионов",
    description=(
        "Администратор видит статус конвейера, курсоры и очередь "
        "обогащения, запускает импорт источника и правит список регионов."
    ),
    title_en="Geo: sources and regions hub",
    description_en=(
        "The administrator sees pipeline status, cursors and the "
        "enrichment queue, runs a specific source and edits regions."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_sources_hub_and_region_crud(
    scenario: ScenarioRecorder,
    ui_page_system: Page,
) -> None:
    page = ui_page_system
    await page.add_init_script(
        "localStorage.setItem('pwa-banner-dismissed', 'true');"
    )
    await _open_sources(page)
    cards = page.locator("geo-sources-page .card")
    await expect(cards).to_have_count(6, timeout=20_000)
    await scenario.step(
        "Хаб источников: конвейер, источники, курсоры, обогащение, "
        "статистика и регионы",
        page,
        label_en="Sources hub: pipeline, sources, cursors, enrichment, "
        "stats and regions",
    )

    # Запуск импорта конкретного источника — кнопка у «osm» ставит тик.
    sources_card = page.locator("geo-sources-page .card").nth(1)
    osm_row = sources_card.locator("tbody tr", has_text="osm")
    await expect(osm_row).to_be_visible(timeout=15_000)
    await osm_row.locator("platform-button").click()
    await expect(
        page.locator("glass-toast").first
    ).to_be_visible(timeout=10_000)

    # CRUD региона: create → виден в таблице → edit → remove.
    add_btn = page.locator("geo-sources-page .card").nth(5).locator(
        "platform-button"
    ).first
    await add_btn.click()
    modal = page.locator("geo-region-editor-modal")
    await expect(modal).to_be_visible(timeout=10_000)
    await scenario.step(
        "Редактор региона: имя, тип, bbox, экстракты",
        page,
        label_en="Region editor: name, kind, bbox, extracts",
    )

    fields = modal.locator("platform-field")
    await _fill_platform_field(fields.nth(0), "e2e-region")
    await _fill_platform_field(fields.nth(1), "E2E регион")
    await _fill_platform_field(fields.nth(4), "55.0")
    await _fill_platform_field(fields.nth(5), "56.0")
    await _fill_platform_field(fields.nth(6), "37.0")
    await _fill_platform_field(fields.nth(7), "38.0")
    await modal.locator(".btn-primary").click()
    await expect(modal).to_be_hidden(timeout=15_000)
    row = page.locator("geo-sources-page tbody tr", has_text="e2e-region")
    await expect(row.first).to_be_visible(timeout=10_000)
    await scenario.step(
        "Регион создан и виден в таблице регионов",
        page,
        label_en="Region created and listed",
    )

    # Edit: меняем title через модалку.
    await row.first.locator(".icon-btn").first.click()
    await expect(modal).to_be_visible(timeout=10_000)
    await _fill_platform_field(modal.locator("platform-field").nth(1), "E2E регион 2")
    await modal.locator(".btn-primary").click()
    await expect(modal).to_be_hidden(timeout=15_000)
    await expect(
        page.locator("geo-sources-page tbody tr", has_text="E2E регион 2")
    ).to_be_visible(timeout=10_000)

    # Remove: platform-confirm-modal → удаление.
    await page.locator(
        "geo-sources-page tbody tr", has_text="E2E регион 2"
    ).first.locator(".icon-btn.danger").click()
    confirm = page.locator("platform-confirm-modal")
    await expect(confirm).to_be_visible(timeout=10_000)
    await confirm.locator(".btn-danger").click()
    await expect(
        page.locator("geo-sources-page tbody tr", has_text="E2E регион 2")
    ).to_have_count(0, timeout=10_000)
    await scenario.step(
        "Регион отредактирован и удалён — список актуален",
        page,
        label_en="Region edited and removed — list is up to date",
    )


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_map_feature_admin_close_road(ui_page_system: Page) -> None:
    """Карточка дороги на map-lab → «Закрыть дорогу» → модалка → override."""
    page = ui_page_system
    await page.add_init_script(
        "localStorage.setItem('pwa-banner-dismissed', 'true');"
    )
    await _open_map_lab(page)
    main_map = page.locator("platform-map.main-map")
    await expect(main_map).to_be_visible(timeout=20_000)
    # К дороге micro.osm: ждём фичи слоя roads и кликаем по ней.
    _ = await main_map.evaluate(
        "(el) => { el.getMap().jumpTo({ center: [37.6173, 55.7503], zoom: 17 }); return true; }"
    )
    deadline = time.monotonic() + 20.0
    count = 0
    while time.monotonic() < deadline:
        count = cast(
            int,
            await main_map.evaluate(
                """(el) => {
                    const s = el.getMap().getSource('pm-src-roads');
                    return s ? s.serialize().data.features.length : 0;
                }""",
            ),
        )
        if count > 0:
            break
        await asyncio.sleep(0.5)
    assert count > 0, "фичи слоя roads не приехали за 20s"

    x, y = cast(
        tuple[float, float],
        await main_map.evaluate(
            """(el) => {
            const m = el.getMap();
            const layers = m.getStyle().layers
                .filter((l) => l.id.startsWith('pm-lyr-roads'))
                .map((l) => l.id);
            const hits = m.queryRenderedFeatures(undefined, { layers });
            const c = hits[0].geometry.coordinates;
            const ll = Array.isArray(c[0]) ? c[Math.floor(c.length / 2)] : c;
            const p = m.project(ll);
            const r = m.getCanvas().getBoundingClientRect();
            return [r.x + p.x, r.y + p.y];
        }""",
        ),
    )
    await page.mouse.click(x, y)
    popup = page.locator(".maplibregl-popup.pm-card-popup")
    await expect(popup).to_be_visible(timeout=10_000)
    close_btn = popup.locator(".pm-card-act[data-pm-action='edge-close']").first
    await expect(close_btn).to_be_visible(timeout=5_000)
    await close_btn.click()

    modal = page.locator("geo-feature-admin-modal")
    await expect(modal).to_be_visible(timeout=10_000)
    chips = modal.locator(".mode-chip")
    await expect(chips).to_have_count(4)
    await modal.locator(".btn-danger").click()
    await expect(modal).to_be_hidden(timeout=15_000)

    # Override применён: в аудите страницы «Адреса» появилась запись edge.
    _ = await page.goto(f"{_GEO_UI.spa_url()}addresses", wait_until="load")
    await expect(page.locator("geo-addresses-page")).to_be_visible(timeout=30_000)
    await page.locator("geo-addresses-page .tab").nth(1).click()
    await expect(
        page.locator("geo-addresses-page tbody tr").first
    ).to_be_visible(timeout=15_000)
