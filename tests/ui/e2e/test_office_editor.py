"""E2E: редактор OnlyOffice и просмотр других типов файлов."""

from __future__ import annotations

import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.office_e2e_helpers import (
    office_api_create_catalog,
    office_api_create_empty_document,
    office_api_upload_txt,
    office_e2e_expect_editor_loaded,
    office_e2e_explorer,
    office_e2e_namespace_headers,
    office_e2e_open_document_by_title,
    office_e2e_open_with_namespace,
    office_e2e_select_catalog,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="office",
    tag="editor",
    doc_slug="edit-in-onlyoffice",
    title="Office: редактирование в OnlyOffice",
    title_en="Office: edit in OnlyOffice",
    description="Открытие docx в OnlyOffice, возврат в проводник и повторное открытие.",
    description_en="Open docx in OnlyOffice, return to explorer, and reopen.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(360)
async def test_office_edit_in_onlyoffice(
    scenario: ScenarioRecorder,
    office_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
    auth_token_system: str,
    office_client_http,
    auth_headers_system,
) -> None:
    doc_title = f"OnlyOffice {unique_id}"

    namespace = await office_e2e_open_with_namespace(office_ui, ui_page_system, unique_id, suffix="edit")
    catalog_id = await office_api_create_catalog(
        office_ui.origin,
        auth_token_system,
        unique_id,
        namespace=namespace,
        title_prefix="editor",
    )
    binding_id = await office_api_create_empty_document(
        office_ui.origin,
        auth_token_system,
        namespace=namespace,
        catalog_id=catalog_id,
        title=doc_title,
        document_type="word",
    )
    await ui_page_system.reload(wait_until="domcontentloaded")
    await office_e2e_select_catalog(ui_page_system, f"editor-{unique_id}")
    await scenario.step(
        "Документ Word в каталоге",
        ui_page_system,
        label_en="Word document in catalog",
    )

    await office_e2e_open_document_by_title(ui_page_system, doc_title)
    await office_e2e_expect_editor_loaded(ui_page_system)
    await scenario.step(
        "OnlyOffice редактор открыт",
        ui_page_system,
        label_en="OnlyOffice editor opened",
    )

    await ui_page_system.locator("office-document-editor-page button.back").click()
    await expect(office_e2e_explorer(ui_page_system)).to_be_visible(timeout=30_000)
    await scenario.step(
        "Возврат к списку документов",
        ui_page_system,
        label_en="Back to document list",
    )

    await office_e2e_open_document_by_title(ui_page_system, doc_title)
    await office_e2e_expect_editor_loaded(ui_page_system)
    await expect(ui_page_system).to_have_url(re.compile(rf"/documents/edit/{binding_id}"))
    await scenario.step(
        "Тот же документ открыт повторно",
        ui_page_system,
        label_en="Same document reopened",
    )

    response = await office_client_http.get(
        "/documents/api/v1/integration/status",
        headers=office_e2e_namespace_headers(auth_headers_system, namespace),
    )
    if response.status_code != 200:
        raise AssertionError(f"integration status failed: {response.status_code}")
    body = response.json()
    if body.get("configured") is not True:
        raise AssertionError("OnlyOffice integration must be configured in test environment")
    await scenario.step(
        "Интеграция Document Server активна",
        ui_page_system,
        label_en="Document Server integration active",
    )


@pytest.mark.scenario(
    service="office",
    tag="editor",
    doc_slug="view-other-file-types",
    title="Office: просмотр текстовых и других файлов",
    title_en="Office: view text and other file types",
    description="Inline-просмотр текста и возврат к списку документов.",
    description_en="Inline text preview and return to document list.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_office_view_other_file_types(
    scenario: ScenarioRecorder,
    office_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
    office_client_http,
    auth_headers_system,
    auth_token_system: str,
) -> None:
    txt_title = f"Notes {unique_id}.txt"

    namespace = await office_e2e_open_with_namespace(office_ui, ui_page_system, unique_id, suffix="view")
    catalog_id = await office_api_create_catalog(
        office_ui.origin,
        auth_token_system,
        unique_id,
        namespace=namespace,
        title_prefix="viewer",
    )
    await office_api_upload_txt(
        office_client_http,
        auth_headers_system,
        namespace=namespace,
        catalog_id=catalog_id,
        title=txt_title.replace(".txt", ""),
        content=b"Plain text preview for office UI e2e",
    )
    await ui_page_system.reload(wait_until="domcontentloaded")
    await office_e2e_select_catalog(ui_page_system, f"viewer-{unique_id}")
    await scenario.step(
        "Текстовый файл в каталоге",
        ui_page_system,
        label_en="Text file in catalog",
    )

    await office_e2e_open_document_by_title(ui_page_system, txt_title.replace(".txt", ""))
    await office_e2e_expect_editor_loaded(ui_page_system)
    await scenario.step(
        "Текстовый просмотрщик открыт",
        ui_page_system,
        label_en="Text viewer opened",
    )

    await ui_page_system.locator("office-document-editor-page button.back").click()
    await expect(office_e2e_explorer(ui_page_system)).to_be_visible(timeout=30_000)
    await scenario.step(
        "Возврат к проводнику",
        ui_page_system,
        label_en="Back to explorer",
    )

    await expect(
        office_e2e_explorer(ui_page_system).locator("platform-file-row, platform-file-card").first
    ).to_be_visible(timeout=15_000)
    await scenario.step(
        "Список документов после просмотра",
        ui_page_system,
        label_en="Document list after preview",
    )
