"""E2E: представления Recent, Starred, Deleted и корзина."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.office_e2e_helpers import (
    office_api_create_catalog,
    office_api_delete_document,
    office_api_upload_txt,
    office_e2e_explorer,
    office_e2e_open_document_by_title,
    office_e2e_open_with_namespace,
    office_e2e_select_catalog,
    office_e2e_select_nav_view,
)
from tests.ui.e2e.sync_e2e_helpers import sync_e2e_click_platform_button
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
@pytest.mark.timeout(300)
async def test_office_views_and_trash(
    scenario: ScenarioRecorder,
    office_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
    office_client_http,
    auth_headers_system,
    auth_token_system: str,
) -> None:
    doc_title = f"Trash {unique_id}"

    namespace = await office_e2e_open_with_namespace(office_ui, ui_page_system, unique_id, suffix="view")
    catalog_id = await office_api_create_catalog(
        office_ui.origin,
        auth_token_system,
        unique_id,
        namespace=namespace,
        title_prefix="views",
    )
    binding_id = await office_api_upload_txt(
        office_client_http,
        auth_headers_system,
        namespace=namespace,
        catalog_id=catalog_id,
        title=doc_title,
    )
    await ui_page_system.reload(wait_until="domcontentloaded")
    await office_e2e_select_catalog(ui_page_system, f"views-{unique_id}")

    await office_e2e_open_document_by_title(ui_page_system, doc_title)
    await ui_page_system.locator("office-document-editor-page button.back").click()
    await scenario.step(
        "Документ в недавних",
        ui_page_system,
        label_en="Document in recent",
    )

    await office_e2e_select_nav_view(ui_page_system, "Недавние", "Recent")
    await expect(
        office_e2e_explorer(ui_page_system).locator("platform-file-row, platform-file-card").filter(
            has_text=doc_title
        ).first
    ).to_be_visible(timeout=30_000)
    await scenario.step(
        "Раздел «Недавние»",
        ui_page_system,
        label_en="Recent view",
    )

    await office_e2e_select_catalog(ui_page_system, f"views-{unique_id}")
    details_row = ui_page_system.locator("platform-file-row").filter(has_text=doc_title).first
    await details_row.click()
    details = office_e2e_explorer(ui_page_system).locator("office-file-details-panel")
    await details.get_by_role("button", name="В избранное").click()
    await office_e2e_select_nav_view(ui_page_system, "Избранное", "Starred")
    await expect(
        office_e2e_explorer(ui_page_system).locator("platform-file-row, platform-file-card").filter(
            has_text=doc_title
        ).first
    ).to_be_visible(timeout=30_000)
    await scenario.step(
        "Раздел «Избранное»",
        ui_page_system,
        label_en="Starred view",
    )

    await office_api_delete_document(
        office_client_http, auth_headers_system, binding_id, namespace=namespace,
    )
    await ui_page_system.reload(wait_until="domcontentloaded")
    await office_e2e_select_nav_view(ui_page_system, "Удалённые", "Deleted")
    await expect(
        office_e2e_explorer(ui_page_system).locator("platform-file-row, platform-file-card").filter(
            has_text=doc_title
        ).first
    ).to_be_visible(timeout=45_000)
    await scenario.step(
        "Раздел «Удалённые»",
        ui_page_system,
        label_en="Deleted view",
    )

    deleted_row = ui_page_system.locator("platform-file-row").filter(has_text=doc_title).first
    await deleted_row.click()
    details = office_e2e_explorer(ui_page_system).locator("office-file-details-panel")
    await details.get_by_role("button", name="Восстановить").click()
    await office_e2e_select_catalog(ui_page_system, f"views-{unique_id}")
    await expect(
        office_e2e_explorer(ui_page_system).locator("platform-file-row, platform-file-card").filter(
            has_text=doc_title
        ).first
    ).to_be_visible(timeout=45_000)
    await scenario.step(
        "Документ восстановлен",
        ui_page_system,
        label_en="Document restored",
    )

    await office_api_delete_document(
        office_client_http, auth_headers_system, binding_id, namespace=namespace,
    )
    await ui_page_system.reload(wait_until="domcontentloaded")
    await office_e2e_select_nav_view(ui_page_system, "Удалённые", "Deleted")
    deleted_row = ui_page_system.locator("platform-file-row").filter(has_text=doc_title).first
    await deleted_row.click()
    details = office_e2e_explorer(ui_page_system).locator("office-file-details-panel")
    await details.get_by_role("button", name="Удалить навсегда").click()
    confirm = ui_page_system.locator("platform-confirm-modal")
    await expect(confirm).to_be_visible(timeout=15_000)
    await sync_e2e_click_platform_button(confirm, "Удалить", "Delete")
    await scenario.step(
        "Документ удалён навсегда",
        ui_page_system,
        label_en="Document permanently deleted",
    )
