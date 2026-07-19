"""E2E: создание и загрузка документов Office."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.office_e2e_helpers import (
    office_api_create_catalog,
    office_api_create_empty_document,
    office_e2e_explorer,
    office_e2e_min_png_path,
    office_e2e_open_create_empty_modal,
    office_e2e_open_upload_modal,
    office_e2e_open_with_namespace,
    office_e2e_select_catalog,
    office_e2e_upload_file_ui,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="office",
    tag="documents",
    doc_slug="create-and-upload-documents",
    title="Office: создание и загрузка документов",
    title_en="Office: create and upload documents",
    description="Пустые документы Word/Sheet/Slide, загрузка через модалку и drag-and-drop зона.",
    description_en="Empty Word/Sheet/Slide documents and file upload via modal and drop zone.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(60)
async def test_office_create_and_upload_documents(
    scenario: ScenarioRecorder,
    office_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
    tmp_path: Path,
) -> None:
    catalog_title = f"files-{unique_id}"
    word_title = f"Word {unique_id}"
    sheet_title = f"Sheet {unique_id}"
    slide_title = f"Slide {unique_id}"
    upload_name = f"upload-{unique_id}.png"

    namespace = await office_e2e_open_with_namespace(
        office_ui, ui_page_system, unique_id, suffix="doc"
    )
    catalog_id = await office_api_create_catalog(
        office_ui.origin,
        auth_token_system,
        unique_id,
        namespace=namespace,
        title_prefix="files",
    )
    await office_api_create_empty_document(
        office_ui.origin,
        auth_token_system,
        namespace=namespace,
        catalog_id=catalog_id,
        title=word_title,
        document_type="word",
    )
    await office_api_create_empty_document(
        office_ui.origin,
        auth_token_system,
        namespace=namespace,
        catalog_id=catalog_id,
        title=sheet_title,
        document_type="cell",
    )
    await office_api_create_empty_document(
        office_ui.origin,
        auth_token_system,
        namespace=namespace,
        catalog_id=catalog_id,
        title=slide_title,
        document_type="slide",
    )
    await ui_page_system.reload(wait_until="domcontentloaded")
    await office_e2e_select_catalog(ui_page_system, catalog_title)
    explorer = office_e2e_explorer(ui_page_system)
    await expect(
        explorer.locator("platform-file-row, platform-file-card").filter(has_text=word_title).first
    ).to_be_visible(timeout=5_000)
    await scenario.step(
        "Каталог выбран для документов",
        ui_page_system,
        label_en="Catalog selected for documents",
    )

    modal = await office_e2e_open_create_empty_modal(ui_page_system)
    await expect(modal.locator(".type-card").filter(has_text="Текст")).to_be_visible(timeout=5_000)
    await expect(modal.locator(".type-card").filter(has_text="Таблица")).to_be_visible(timeout=5_000)
    await expect(modal.locator(".type-card").filter(has_text="Презентация")).to_be_visible(
        timeout=5_000
    )
    await modal.locator("button.btn-secondary").click()
    await scenario.step(
        "Форма создания пустого документа",
        ui_page_system,
        label_en="Empty document form",
    )

    await expect(
        explorer.locator("platform-file-row, platform-file-card").filter(has_text=sheet_title).first
    ).to_be_visible(timeout=5_000)
    await expect(
        explorer.locator("platform-file-row, platform-file-card").filter(has_text=slide_title).first
    ).to_be_visible(timeout=5_000)
    await scenario.step(
        "Созданы документы Word, Sheet и Slide",
        ui_page_system,
        label_en="Word, Sheet, and Slide documents created",
    )

    upload_modal = await office_e2e_open_upload_modal(ui_page_system)
    await expect(upload_modal.get_by_text("Перетащите файлы сюда")).to_be_visible(timeout=5_000)
    await upload_modal.locator("button.btn-secondary").click()
    await scenario.step(
        "Модалка загрузки с drag-and-drop",
        ui_page_system,
        label_en="Upload modal with drag-and-drop",
    )

    png_path = office_e2e_min_png_path(tmp_path, upload_name)
    await office_e2e_upload_file_ui(ui_page_system, png_path)
    await expect(
        office_e2e_explorer(ui_page_system).locator("platform-file-row, platform-file-card").first
    ).to_be_visible(timeout=5_000)
    await scenario.step(
        "Загруженный файл в списке",
        ui_page_system,
        label_en="Uploaded file in list",
    )

    toolbar = ui_page_system.locator("office-file-toolbar")
    await expect(toolbar.get_by_role("button", name="Новый документ")).to_be_visible(timeout=5_000)
    await scenario.step(
        "Панель действий над списком документов",
        ui_page_system,
        label_en="Document list toolbar actions",
    )
