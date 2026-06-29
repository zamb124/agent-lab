"""E2E: RAG-индексация каталога и семантический поиск."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.office_e2e_helpers import (
    office_api_create_catalog,
    office_api_upload_txt,
    office_e2e_catalog_context_action,
    office_e2e_open_with_namespace,
    office_e2e_search_documents,
    office_e2e_select_catalog,
    office_e2e_toolbar,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="office",
    tag="rag",
    doc_slug="catalog-rag-and-semantic-search",
    title="Office: RAG-индексация и семантический поиск",
    title_en="Office: RAG indexing and semantic search",
    description="Модалка RAG, статус индексации, семантический поиск и открытие результата.",
    description_en="RAG modal, indexing status, semantic search, and opening a result.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(360)
async def test_office_catalog_rag_and_semantic_search(
    scenario: ScenarioRecorder,
    office_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
    office_client_http,
    auth_headers_system,
    auth_token_system: str,
    rag_service,
    rag_worker,
) -> None:
    catalog_title = f"rag-{unique_id}"
    doc_title = f"SemanticTarget {unique_id}"
    query = "SemanticTarget"

    namespace = await office_e2e_open_with_namespace(office_ui, ui_page_system, unique_id, suffix="rag")
    catalog_id = await office_api_create_catalog(
        office_ui.origin,
        auth_token_system,
        unique_id,
        namespace=namespace,
        title_prefix="rag",
    )
    await office_api_upload_txt(
        office_client_http,
        auth_headers_system,
        namespace=namespace,
        catalog_id=catalog_id,
        title=doc_title,
        content=b"semantic indexing content about project roadmap and milestones",
    )
    await ui_page_system.reload(wait_until="domcontentloaded")
    await office_e2e_select_catalog(ui_page_system, catalog_title)
    await scenario.step(
        "Каталог с документом для индексации",
        ui_page_system,
        label_en="Catalog with document for indexing",
    )

    await office_e2e_catalog_context_action(ui_page_system, catalog_title, "RAG", "RAG-индексация")
    rag_modal = ui_page_system.locator("office-catalog-rag-modal")
    await expect(rag_modal).to_be_visible(timeout=30_000)
    await scenario.step(
        "Модалка RAG-индексации",
        ui_page_system,
        label_en="RAG indexing modal",
    )

    enable_switch = rag_modal.locator("platform-switch").first
    await enable_switch.click()
    await expect(rag_modal.get_by_text("Готово")).to_be_visible(timeout=120_000)
    await rag_modal.get_by_role("button", name="Закрыть").click()
    await expect(rag_modal).to_be_hidden(timeout=30_000)
    await ui_page_system.reload(wait_until="domcontentloaded")
    await office_e2e_select_catalog(ui_page_system, catalog_title)
    await scenario.step(
        "Индексация каталога включена",
        ui_page_system,
        label_en="Catalog indexing enabled",
    )

    semantic_btn = office_e2e_toolbar(ui_page_system).get_by_role("button", name="Семантика")
    await semantic_btn.click()
    await scenario.step(
        "Режим семантического поиска",
        ui_page_system,
        label_en="Semantic search mode",
    )

    await office_e2e_search_documents(ui_page_system, query)
    results = ui_page_system.locator("office-catalog-semantic-search-results")
    await expect(results).to_be_visible(timeout=120_000)
    await scenario.step(
        "Результаты семантического поиска",
        ui_page_system,
        label_en="Semantic search results",
    )

    result_row = results.locator(".result-title").first
    if await result_row.count() > 0:
        await result_row.click()
        await expect(ui_page_system.locator("office-document-editor-page")).to_be_visible(timeout=60_000)
    await scenario.step(
        "Документ открыт из результата поиска",
        ui_page_system,
        label_en="Document opened from search result",
    )
