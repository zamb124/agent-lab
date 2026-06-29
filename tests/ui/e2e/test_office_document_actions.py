"""E2E: действия с документами — переименование, удаление, меню."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.office_e2e_helpers import (
    office_api_create_catalog,
    office_api_upload_txt,
    office_e2e_delete_document,
    office_e2e_explorer,
    office_e2e_open_document_by_title,
    office_e2e_open_with_namespace,
    office_e2e_rename_document,
    office_e2e_select_catalog,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="office",
    tag="documents",
    doc_slug="document-actions-move-rename-delete",
    title="Office: действия с документами",
    title_en="Office: document actions",
    description="Открытие, переименование, контекстное меню и удаление документа.",
    description_en="Open, rename, context menu, and delete a document.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_office_document_actions(
    scenario: ScenarioRecorder,
    office_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
    office_client_http,
    auth_headers_system,
    auth_token_system: str,
) -> None:
    original_title = f"Draft {unique_id}"
    renamed_title = f"Final {unique_id}"

    namespace = await office_e2e_open_with_namespace(office_ui, ui_page_system, unique_id, suffix="act")
    catalog_id = await office_api_create_catalog(
        office_ui.origin,
        auth_token_system,
        unique_id,
        namespace=namespace,
        title_prefix="actions",
    )
    await office_api_upload_txt(
        office_client_http,
        auth_headers_system,
        namespace=namespace,
        catalog_id=catalog_id,
        title=original_title,
    )
    await ui_page_system.reload(wait_until="domcontentloaded")
    await office_e2e_select_catalog(ui_page_system, f"actions-{unique_id}")
    await scenario.step(
        "Документ в каталоге",
        ui_page_system,
        label_en="Document in catalog",
    )

    await office_e2e_open_document_by_title(ui_page_system, original_title)
    await ui_page_system.locator("office-document-editor-page button.back").click()
    await scenario.step(
        "Документ открыт и закрыт",
        ui_page_system,
        label_en="Document opened and closed",
    )

    await office_e2e_rename_document(ui_page_system, original_title, renamed_title)
    await expect(
        office_e2e_explorer(ui_page_system).locator("platform-file-row, platform-file-card").filter(
            has_text=renamed_title
        ).first
    ).to_be_visible(timeout=30_000)
    await scenario.step(
        "Документ переименован",
        ui_page_system,
        label_en="Document renamed",
    )

    row = ui_page_system.locator("platform-file-row").filter(has_text=renamed_title).first
    menu = row.locator("office-file-actions-menu button.trigger").first
    await menu.click()
    await expect(ui_page_system.locator("office-file-actions-menu .item").first).to_be_visible()
    await ui_page_system.keyboard.press("Escape")
    await scenario.step(
        "Меню действий файла",
        ui_page_system,
        label_en="File actions menu",
    )

    await office_e2e_delete_document(ui_page_system, renamed_title)
    await ui_page_system.reload(wait_until="domcontentloaded")
    await office_e2e_select_catalog(ui_page_system, f"actions-{unique_id}")
    await expect(
        office_e2e_explorer(ui_page_system).locator("platform-file-row, platform-file-card").filter(
            has_text=renamed_title
        )
    ).to_have_count(0, timeout=30_000)
    await scenario.step(
        "Документ удалён",
        ui_page_system,
        label_en="Document deleted",
    )
