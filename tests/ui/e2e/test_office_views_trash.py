"""E2E: представления Recent, Starred, Deleted и корзина."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.office_e2e_helpers import (
    office_api_create_catalog,
    office_api_delete_document_auth,
    office_api_upload_txt_auth,
    office_e2e_confirm_delete,
    office_e2e_explorer,
    office_e2e_open_with_namespace,
    office_e2e_select_catalog,
    office_e2e_select_nav_view,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="office",
    tag="views",
    doc_slug="views-and-trash",
    title="Office: недавние, избранное и корзина",
    title_en="Office: recent, starred, and trash",
    description="Nav-rail Recent/Starred/Deleted, восстановление и окончательное удаление.",
    description_en="Nav-rail Recent/Starred/Deleted, restore and permanent delete.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_office_views_and_trash(
    scenario: ScenarioRecorder,
    office_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
    auth_token_system: str, frontend_di,
) -> None:
    doc_title = f"Trash {unique_id}"
    catalog_title = f"views-{unique_id}"

    namespace = await office_e2e_open_with_namespace(
        office_ui, ui_page_system, unique_id, suffix="view", di=frontend_di
    )
    catalog_id = await office_api_create_catalog(
        office_ui.origin,
        auth_token_system,
        unique_id,
        namespace=namespace,
        title_prefix="views",
    )
    file_id = await office_api_upload_txt_auth(
        office_ui.origin,
        auth_token_system,
        namespace=namespace,
        catalog_id=catalog_id,
        title=doc_title,
    )
    await ui_page_system.reload(wait_until="domcontentloaded")
    await office_e2e_select_catalog(ui_page_system, catalog_title)
    explorer = office_e2e_explorer(ui_page_system)
    file_row = explorer.locator("platform-file-row, platform-file-card").filter(
        has_text=doc_title
    ).first
    await expect(file_row).to_be_visible(timeout=5_000)
    await file_row.click()
    details = explorer.locator("office-file-details-panel")
    await details.get_by_role("button", name="Открыть").click()
    await expect(ui_page_system.locator("office-document-editor-page")).to_be_visible(timeout=5_000)
    await ui_page_system.locator("office-document-editor-page button.stage-back").click()
    await expect(explorer).to_be_visible(timeout=5_000)
    await scenario.step(
        "Документ в недавних",
        ui_page_system,
        label_en="Document in recent",
    )

    await office_e2e_select_nav_view(ui_page_system, "Недавние", "Recent")
    await expect(
        explorer.locator("platform-file-row, platform-file-card").filter(has_text=doc_title).first
    ).to_be_visible(timeout=5_000)
    await scenario.step(
        "Раздел «Недавние»",
        ui_page_system,
        label_en="Recent view",
    )

    await office_e2e_select_catalog(ui_page_system, catalog_title)
    details_row = ui_page_system.locator("platform-file-row").filter(has_text=doc_title).first
    await expect(details_row).to_be_visible(timeout=5_000)
    await details_row.click()
    details = explorer.locator("office-file-details-panel")
    await details.get_by_role("button", name="В избранное").click()
    await office_e2e_select_nav_view(ui_page_system, "Избранное", "Starred")
    await expect(
        explorer.locator("platform-file-row, platform-file-card").filter(has_text=doc_title).first
    ).to_be_visible(timeout=5_000)
    await scenario.step(
        "Раздел «Избранное»",
        ui_page_system,
        label_en="Starred view",
    )

    await office_api_delete_document_auth(
        office_ui.origin,
        auth_token_system,
        file_id,
        namespace=namespace,
    )
    await ui_page_system.reload(wait_until="domcontentloaded")
    await office_e2e_select_nav_view(ui_page_system, "Удалённые", "Deleted")
    await expect(
        explorer.locator("platform-file-row, platform-file-card").filter(has_text=doc_title).first
    ).to_be_visible(timeout=5_000)
    await scenario.step(
        "Раздел «Удалённые»",
        ui_page_system,
        label_en="Deleted view",
    )

    deleted_row = ui_page_system.locator("platform-file-row").filter(has_text=doc_title).first
    await deleted_row.click()
    details = explorer.locator("office-file-details-panel")
    await details.get_by_role("button", name="Восстановить").click()
    # После restore список каталога может ещё держать stale empty — reload.
    await expect(deleted_row).to_be_hidden(timeout=15_000)
    await ui_page_system.reload(wait_until="domcontentloaded")
    await office_e2e_select_catalog(ui_page_system, catalog_title)
    await expect(
        explorer.locator("platform-file-row, platform-file-card").filter(has_text=doc_title).first
    ).to_be_visible(timeout=30_000)
    await scenario.step(
        "Документ восстановлен",
        ui_page_system,
        label_en="Document restored",
    )

    await office_api_delete_document_auth(
        office_ui.origin,
        auth_token_system,
        file_id,
        namespace=namespace,
    )
    await ui_page_system.reload(wait_until="domcontentloaded")
    await office_e2e_select_nav_view(ui_page_system, "Удалённые", "Deleted")
    deleted_row = ui_page_system.locator("platform-file-row").filter(has_text=doc_title).first
    await expect(deleted_row).to_be_visible(timeout=5_000)
    await deleted_row.click()
    details = explorer.locator("office-file-details-panel")
    await details.get_by_role("button", name="Удалить навсегда").click()
    await office_e2e_confirm_delete(ui_page_system)
    await scenario.step(
        "Документ удалён навсегда",
        ui_page_system,
        label_en="Document permanently deleted",
    )
