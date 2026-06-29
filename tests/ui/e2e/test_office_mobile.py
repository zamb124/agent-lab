"""E2E: мобильный shell Office."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.office_e2e_helpers import (
    office_api_create_catalog,
    office_api_create_empty_document,
    office_e2e_expect_editor_loaded,
    office_e2e_explorer,
    office_e2e_open_with_namespace,
    office_e2e_select_catalog,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="office",
    tag="mobile",
    doc_slug="mobile-documents-workflow",
    title="Office: мобильный интерфейс документов",
    title_en="Office: mobile documents workflow",
    description="Bottom nav, выбор пространства и каталога, редактор без нижней навигации.",
    description_en="Bottom nav, workspace and catalog pickers, editor without bottom navigation.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_office_mobile_documents_workflow(
    scenario: ScenarioRecorder,
    office_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
    auth_token_system: str,
) -> None:
    doc_title = f"Mobile {unique_id}"

    await ui_page_system.set_viewport_size({"width": 390, "height": 844})
    namespace = await office_e2e_open_with_namespace(office_ui, ui_page_system, unique_id, suffix="mob")
    bottom_nav = ui_page_system.locator("platform-bottom-nav")
    await expect(bottom_nav).to_be_visible(timeout=30_000)
    await scenario.step(
        "Мобильная нижняя навигация",
        ui_page_system,
        label_en="Mobile bottom navigation",
    )

    await bottom_nav.locator("button.nav-tab").filter(has_text="Недавние").click()
    await expect(office_e2e_explorer(ui_page_system)).to_be_visible(timeout=15_000)
    await bottom_nav.locator("button.nav-tab").filter(has_text="Файлы").click()
    await scenario.step(
        "Переключение Files / Recent",
        ui_page_system,
        label_en="Files and Recent tabs",
    )

    catalog_id = await office_api_create_catalog(
        office_ui.origin,
        auth_token_system,
        unique_id,
        namespace=namespace,
        title_prefix="mobile",
    )
    binding_id = await office_api_create_empty_document(
        office_ui.origin,
        auth_token_system,
        namespace=namespace,
        catalog_id=catalog_id,
        title=doc_title,
    )
    await ui_page_system.reload(wait_until="domcontentloaded")
    mobile_catalog_btn = office_e2e_explorer(ui_page_system).locator("button.mobile-catalog-btn")
    await expect(mobile_catalog_btn).to_be_visible(timeout=30_000)
    await scenario.step(
        "Выбор каталога на мобильном",
        ui_page_system,
        label_en="Mobile catalog picker",
    )

    await office_e2e_select_catalog(ui_page_system, f"mobile-{unique_id}")
    row = ui_page_system.locator("platform-file-row, platform-file-card").filter(has_text=doc_title).first
    await row.dblclick()
    await office_e2e_expect_editor_loaded(ui_page_system)
    await expect(bottom_nav).to_be_hidden(timeout=15_000)
    await scenario.step(
        "Редактор скрывает bottom nav",
        ui_page_system,
        label_en="Editor hides bottom nav",
    )

    _ = binding_id
