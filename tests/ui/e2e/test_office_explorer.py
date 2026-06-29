"""E2E: проводник документов — поиск, сортировка, представления."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.office_e2e_helpers import (
    office_api_create_catalog,
    office_api_upload_txt,
    office_e2e_explorer,
    office_e2e_open_with_namespace,
    office_e2e_refresh_documents,
    office_e2e_search_documents,
    office_e2e_select_catalog,
    office_e2e_set_view_mode,
    office_e2e_toolbar,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="office",
    tag="explorer",
    doc_slug="explorer-search-and-organize",
    title="Office: проводник — поиск и организация",
    title_en="Office: explorer search and organize",
    description="Список и сетка, поиск, выбор файла, избранное и обновление списка.",
    description_en="List and grid views, search, file selection, starred, and refresh.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_office_explorer_search_and_organize(
    scenario: ScenarioRecorder,
    office_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
    office_client_http,
    auth_headers_system,
    auth_token_system: str,
) -> None:
    alpha_title = f"Alpha {unique_id}"
    beta_title = f"Beta {unique_id}"

    namespace = await office_e2e_open_with_namespace(office_ui, ui_page_system, unique_id, suffix="exp")
    catalog_id = await office_api_create_catalog(
        office_ui.origin,
        auth_token_system,
        unique_id,
        namespace=namespace,
        title_prefix="explorer",
    )
    await office_api_upload_txt(
        office_client_http,
        auth_headers_system,
        namespace=namespace,
        catalog_id=catalog_id,
        title=alpha_title,
    )
    await office_api_upload_txt(
        office_client_http,
        auth_headers_system,
        namespace=namespace,
        catalog_id=catalog_id,
        title=beta_title,
    )
    await ui_page_system.reload(wait_until="domcontentloaded")
    await expect(office_e2e_explorer(ui_page_system)).to_be_visible(timeout=30_000)
    await office_e2e_select_catalog(ui_page_system, f"explorer-{unique_id}")
    await scenario.step(
        "Список документов в каталоге",
        ui_page_system,
        label_en="Documents listed in catalog",
    )

    await office_e2e_set_view_mode(ui_page_system, "grid")
    await expect(ui_page_system.locator("platform-file-card").first).to_be_visible(timeout=15_000)
    await office_e2e_set_view_mode(ui_page_system, "list")
    await expect(ui_page_system.locator("platform-file-row").first).to_be_visible(timeout=15_000)
    await scenario.step(
        "Переключение списка и сетки",
        ui_page_system,
        label_en="List and grid toggle",
    )

    await office_e2e_search_documents(ui_page_system, "Alpha")
    await expect(
        office_e2e_explorer(ui_page_system).locator("platform-file-row, platform-file-card").filter(
            has_text="Alpha"
        ).first
    ).to_be_visible(timeout=15_000)
    await scenario.step(
        "Поиск по названию",
        ui_page_system,
        label_en="Search by name",
    )

    row = ui_page_system.locator("platform-file-row").filter(has_text=alpha_title).first
    await row.click()
    details = office_e2e_explorer(ui_page_system).locator("office-file-details-panel")
    await expect(details).to_be_visible(timeout=15_000)
    await scenario.step(
        "Панель сведений о файле",
        ui_page_system,
        label_en="File details panel",
    )

    star_btn = details.get_by_role("button", name="В избранное")
    await star_btn.click()
    await scenario.step(
        "Документ добавлен в избранное",
        ui_page_system,
        label_en="Document starred",
    )

    await office_e2e_refresh_documents(ui_page_system)
    await expect(ui_page_system.locator("platform-file-row").first).to_be_visible(timeout=30_000)
    await scenario.step(
        "Список обновлён",
        ui_page_system,
        label_en="List refreshed",
    )
