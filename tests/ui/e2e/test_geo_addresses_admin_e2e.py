"""Страница «Адреса» — админ-правки справочника в реальном браузере.

Продовый путь: Chromium + auth-cookie владельца компании, SPA geo на
:9028, поиск/правки идут боевым контрактом (WS→op→PostGIS/оверлеи).
Данные — поколение из micro.osm (geo_worker стека) + ручной адрес,
созданный и скрытый самим тестом.

Покрытие: загрузка страницы и поиска, таблица результатов, модалка
редактора (platform-field + platform-map с draggable-маркером), патч
housenumber с записью в аудит, вкладка «Аудит правок», откат правки,
создание и скрытие ручного адреса.
"""

from __future__ import annotations

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


async def _open_addresses(page: Page) -> None:
    _ = await page.goto(f"{_GEO_UI.spa_url()}addresses", wait_until="load")
    await expect(page.locator("geo-app")).to_be_visible(timeout=30_000)
    await expect(page.locator("geo-addresses-page")).to_be_visible(timeout=30_000)


async def _search(page: Page, q: str) -> None:
    field = page.locator("geo-addresses-page .search-box platform-field")
    await _fill_platform_field(field, q)


@pytest.mark.scenario(
    service="geo",
    tag="addresses",
    doc_slug="admin-edit-address",
    timeout_seconds=90,
    title="Geo: правка адреса администратором",
    description=(
        "Администратор находит адрес поиском, правит номер дома в модалке "
        "редактора, видит правку в аудите и откатывает её."
    ),
    title_en="Geo: admin edits an address",
    description_en=(
        "The administrator searches for an address, edits the house number "
        "in the editor modal, sees the patch in the audit tab and reverts it."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_admin_edit_audit_and_revert_address(
    scenario: ScenarioRecorder,
    ui_page_system: Page,
) -> None:
    page = ui_page_system
    await page.add_init_script(
        "localStorage.setItem('pwa-banner-dismissed', 'true');"
    )
    await _open_addresses(page)
    await scenario.step(
        "Страница «Адреса» открыта: поиск, вкладки, пустая таблица",
        page,
        label_en="Addresses page opened: search, tabs, empty table",
    )

    await _search(page, "Тверская")
    rows = page.locator("geo-addresses-page tbody tr")
    await expect(rows.first).to_contain_text("Тверская", timeout=10_000)
    await scenario.step(
        "Поиск «Тверская»: найдены адреса активного поколения",
        page,
        label_en="Search 'Tverskaya': addresses of the active generation found",
    )

    await rows.first.locator(".actions platform-button").first.click()
    modal = page.locator("geo-address-editor-modal")
    await expect(modal).to_be_visible(timeout=10_000)
    await expect(modal.locator("platform-map")).to_be_visible(timeout=15_000)
    await scenario.step(
        "Модалка редактора: поля адреса и мини-карта с маркером",
        page,
        label_en="Editor modal: address fields and mini-map with marker",
    )

    await _fill_platform_field(modal.locator("platform-field").nth(3), "1Е2А")
    await _fill_platform_field(modal.locator("platform-field").nth(5), "e2e уточнение")
    await modal.locator(".btn-primary").click()
    await expect(modal).to_be_hidden(timeout=15_000)
    await expect(
        page.locator("geo-addresses-page tbody tr").first
    ).to_contain_text("1Е2А", timeout=10_000)

    await page.locator("geo-addresses-page .tab").nth(1).click()
    audit_rows = page.locator("geo-addresses-page tbody tr")
    await expect(audit_rows.first).to_contain_text("e2e уточнение", timeout=10_000)
    await scenario.step(
        "Вкладка «Аудит правок»: патч записан с причиной и автором",
        page,
        label_en="Audit tab: patch recorded with reason and actor",
    )

    await audit_rows.first.locator(".actions platform-button").first.click()
    await page.locator("geo-addresses-page .tab").nth(0).click()
    await _search(page, "Тверская")
    await expect(
        page.locator("geo-addresses-page tbody tr").first
    ).to_contain_text("Тверская улица, 1", timeout=10_000)
    await scenario.step(
        "Откат правки: адрес вернулся к исходному значению",
        page,
        label_en="Revert: address restored to the source value",
    )


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_admin_creates_and_hides_manual_address(ui_page_system: Page) -> None:
    """Ручной адрес: create → виден в поиске → hide → пропал из выдачи."""
    page = ui_page_system
    await page.add_init_script(
        "localStorage.setItem('pwa-banner-dismissed', 'true');"
    )
    await _open_addresses(page)

    await page.locator("geo-addresses-page .toolbar platform-button").click()
    modal = page.locator("geo-address-editor-modal")
    await expect(modal).to_be_visible(timeout=10_000)

    fields = modal.locator("platform-field")
    await _fill_platform_field(fields.nth(0), "Тестовая улица, 7")
    await _fill_platform_field(fields.nth(1), "Москва")
    await _fill_platform_field(fields.nth(2), "Тестовая улица")
    await _fill_platform_field(fields.nth(3), "7")
    await _fill_platform_field(fields.nth(4), "")
    await _fill_platform_field(fields.nth(5), "moscow")
    await _fill_platform_field(fields.nth(6), "e2e create")

    await expect(modal.locator("platform-map")).to_be_visible(timeout=15_000)
    map_box = await modal.locator("platform-map canvas").first.bounding_box()
    assert map_box is not None
    await page.mouse.click(
        map_box["x"] + map_box["width"] / 2,
        map_box["y"] + map_box["height"] / 2,
    )
    await modal.locator(".btn-primary").click()
    await expect(modal).to_be_hidden(timeout=15_000)

    await _search(page, "Тестовая")
    row = page.locator("geo-addresses-page tbody tr", has_text="Тестовая")
    await expect(row.first).to_contain_text("manual", timeout=10_000)

    await row.first.locator(".actions platform-button").nth(1).click()
    await expect(
        page.locator("geo-addresses-page tbody tr", has_text="Тестовая")
    ).to_have_count(0, timeout=10_000)
