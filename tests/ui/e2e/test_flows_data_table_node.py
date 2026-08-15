"""E2E: инспектор DataTable-ноды — Открыть, карточки схемы, без создания таблиц на ноде."""

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
from tests.ui.harness import AppUI

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")

_OPEN = re.compile(r"^(Открыть|Open)$")
_DOWNLOAD_CSV = re.compile(r"^(Скачать CSV|Download CSV)$")
_DOWNLOAD_XLSX = re.compile(r"^(Скачать Excel|Download Excel)$")
_ADD_TABLE = re.compile(r"^(Новая таблица|Add table)$")
_SQLITE_DOWNLOAD = re.compile(r"^(Скачать|Download)$")


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_flows_data_table_node_opens_documents_viewer(
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
    flows_client_http,
    auth_headers_system,
    office_service,
) -> None:
    _ = office_service
    flow_id = flows_doc_flow_id("dtable", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(
            flow_id,
            name=GREEN_GARDEN_AGENT_NAME,
            prompt="Работай с таблицей лидов.",
        ),
    )
    create_response = await flows_client_http.post(
        "/flows/api/v1/data-tables",
        headers=auth_headers_system,
        json={
            "original_name": f"node-table-{unique_id}.sqlite",
            "scope": "flow_asset",
            "flow_id": flow_id,
            "tables": [
                {
                    "name": "leads",
                    "columns": [
                        {"name": "title", "column_type": "text"},
                        {"name": "score", "column_type": "integer"},
                    ],
                }
            ],
        },
    )
    assert create_response.status_code == 200, create_response.text
    file_id = create_response.json()["file_id"]

    page = ui_page_system
    await office_e2e_set_locale_ru(page)
    await flows_open_editor(page, flows_ui, flow_id)
    await flows_e2e_ensure_canvas_layout(page)
    node_id = await flows_drop_resource_type(
        page,
        "data_table",
        x=640,
        y=400,
        name="Leads table",
        config={"file_id": file_id},
    )
    await flows_open_node_editor(page, node_id)
    editor = page.locator("flows-data-table-resource-editor:visible").last
    await expect(editor).to_be_visible(timeout=10_000)
    open_button = editor.get_by_role("button", name=_OPEN)
    await expect(open_button).to_be_visible(timeout=15_000)
    await expect(editor.get_by_text("Создать таблицу")).to_have_count(0)
    await expect(editor.get_by_text("Create table")).to_have_count(0)
    await expect(editor.get_by_text("Открыть в Documents")).to_have_count(0)
    await expect(editor.get_by_text("Open in Documents")).to_have_count(0)
    await expect(editor.get_by_text("SQLite")).to_have_count(0)
    await expect(editor.locator(".table-card").filter(has_text="leads")).to_be_visible(
        timeout=20_000
    )
    await expect(editor.locator(".col-chip").filter(has_text="title")).to_be_visible()
    await expect(editor.locator(".col-chip").filter(has_text="score")).to_be_visible()

    await open_button.click()
    modal = page.locator("platform-file-viewer-modal")
    await expect(modal).to_be_visible(timeout=30_000)
    host = modal.locator("platform-data-table-host")
    await expect(host).to_be_visible(timeout=30_000)
    await expect(host.get_by_role("button", name=_DOWNLOAD_CSV)).to_be_visible()
    await expect(host.get_by_role("button", name=_DOWNLOAD_XLSX)).to_be_visible()
    await expect(modal.get_by_role("button", name=_SQLITE_DOWNLOAD, exact=True)).to_have_count(0)
    await expect(host.get_by_role("button", name=_ADD_TABLE)).to_be_visible()
