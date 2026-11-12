"""E2E: RAG resource-нода на канве — документы, test-run поиск, без node.files."""

from __future__ import annotations

import os
import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    GREEN_GARDEN_AGENT_NAME,
    flows_api_create_flow,
    flows_doc_flow_id,
    flows_drop_resource_type,
    flows_e2e_ensure_canvas_layout,
    flows_llm_payload,
    flows_open_editor,
    flows_open_node_editor,
)
from tests.ui.e2e.office_e2e_helpers import office_e2e_set_locale_ru
from tests.ui.harness import AppUI, ui_set_platform_field

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")

_FILES_SECTION = re.compile(r"Прикреплённые файлы|Attached files")
_DOCUMENTS = re.compile(r"Документы namespace|Namespace documents")
_TEST_SECTION = re.compile(r"Проверка поиска|Search test")
_READY = re.compile(r"Готово|Ready")
_QUERY_REQUIRED = re.compile(r"Введите запрос для проверки поиска|Enter a query to test search")
_QUERY_LABEL = re.compile(r"Запрос|Query")


async def _rag_json(page: Page, origin: str, method: str, path: str, body: dict | None = None) -> dict:
    url = f"{origin}{path}"
    if method == "GET":
        response = await page.request.get(url)
    elif method == "POST":
        response = await page.request.post(
            url,
            headers={"Content-Type": "application/json"},
            data=body,
        )
    else:
        raise AssertionError(f"unsupported method {method}")
    if response.status >= 400:
        raise AssertionError(f"{method} {path} -> {response.status} {await response.text()}")
    payload = await response.json()
    if not isinstance(payload, dict):
        raise AssertionError(f"{method} {path} JSON object required, got {type(payload)}")
    return payload


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_flows_rag_node_documents_and_search(
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
    unique_namespace_name: str,
    rag_service,
) -> None:
    _ = rag_service
    flow_id = flows_doc_flow_id("ragnode", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(
            flow_id,
            name=GREEN_GARDEN_AGENT_NAME,
            prompt="Ищи в базе знаний.",
        ),
    )

    page = ui_page_system
    await office_e2e_set_locale_ru(page)
    await flows_open_editor(page, flows_ui, flow_id)
    await flows_e2e_ensure_canvas_layout(page)

    namespace = unique_namespace_name
    marker = f"canvas_rag_needle_{unique_id}"
    created = await _rag_json(
        page,
        flows_ui.origin,
        "POST",
        "/rag/api/v1/namespaces",
        {"name": namespace, "description": "canvas rag node"},
    )
    assert created["name"] == namespace
    ingested = await _rag_json(
        page,
        flows_ui.origin,
        "POST",
        f"/rag/api/v1/namespaces/{namespace}/ingest-text",
        {
            "text": f"Правила возврата: {marker}. Срок 14 дней.",
            "document_name": "returns.md",
        },
    )
    assert ingested["status"] == "completed"
    assert ingested["document_name"] == "returns.md"

    node_id = await flows_drop_resource_type(
        page,
        "rag",
        x=640,
        y=400,
        name="Knowledge",
        config={"namespace": namespace, "default_top_k": 5},
    )
    panel = await flows_open_node_editor(page, node_id)
    editor = page.locator("flows-rag-resource-editor:visible").last
    await expect(editor).to_be_visible(timeout=10_000)

    await expect(panel.get_by_text(_FILES_SECTION)).to_have_count(0)
    await expect(editor.get_by_text(_DOCUMENTS)).to_be_visible()
    await expect(editor.get_by_text(_TEST_SECTION)).to_be_visible()
    await expect(editor.get_by_text("returns.md")).to_be_visible(timeout=20_000)
    await expect(editor.get_by_text(_READY)).to_be_visible()

    play = panel.locator("flows-node-run-control platform-button").first
    await expect(play).to_be_visible()
    await play.click()
    await expect(page.locator("glass-toast").filter(has_text=_QUERY_REQUIRED)).to_be_visible(timeout=8_000)

    query_field = editor.locator("platform-field").filter(has_text=_QUERY_LABEL).first
    await expect(query_field).to_be_visible()
    await ui_set_platform_field(query_field, f"Правила возврата: {marker}. Срок 14 дней.")
    await play.click()

    hit = editor.locator(".result-card").filter(has_text="returns.md")
    await expect(hit).to_be_visible(timeout=20_000)
    await expect(hit).to_contain_text(marker)
    bubble = page.locator(".flows-node-run-bubble")
    await expect(bubble).to_be_visible(timeout=10_000)
