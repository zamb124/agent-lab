"""E2E-сценарий: как работать с MCP в Flows (Store, LLM tools, нода на канве)."""

from __future__ import annotations

import re

import pytest
from playwright.async_api import Page, expect

from apps.flows.src.services.mcp_catalog_ids import server_id_from_catalog_id
from tests.ui.e2e.flows_e2e_helpers import (
    flows_api_create_flow,
    flows_api_sync_mcp_server,
    flows_click_platform_button,
    flows_doc_flow_id,
    flows_drop_llm_node,
    flows_drop_mcp_node,
    flows_graph_payload,
    flows_open_mcp_servers_modal,
    flows_pick_first_mcp_tool_in_picker,
    flows_seed_mcp_store_catalog_entry,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="flows",
    tag="general",
    doc_slug="mcp-workflow",
    title="Flows: как работать с MCP",
    title_en="Flows: working with MCP",
    description=(
        "Короткая инструкция: где искать MCP серверы, как установить из каталога, "
        "как добавить MCP tool в LLM-ноду и как поставить MCP-ноду на канву."
    ),
    description_en=(
        "Short guide: where to find MCP servers, how to install from the catalog, "
        "how to add an MCP tool to an LLM node, and how to place an MCP node on the canvas."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(360)
async def test_flows_mcp_workflow_scenario(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
    local_mcp_http_url: str,
) -> None:
    catalog_id = await flows_seed_mcp_store_catalog_entry(
        unique_id,
        upstream_url=local_mcp_http_url,
    )
    server_id = server_id_from_catalog_id(catalog_id)

    page = ui_page_system
    _ = await page.goto(f"{flows_ui.origin}/flows/", wait_until="domcontentloaded")
    await expect(page.locator("flows-app")).to_be_visible(timeout=30_000)
    await scenario.step(
        "Открываем Flows. На главной есть кнопка MCP — это управление серверами и каталогом.",
        page,
        label_en="Open Flows. The home page has an MCP button for servers and the catalog.",
    )

    modal = await flows_open_mcp_servers_modal(page)
    await scenario.step(
        (
            "Нажимаем MCP. Открывается модалка: вкладка «Подключённые» — серверы компании; "
            "Browser и Search обычно уже есть после создания компании."
        ),
        page,
        label_en="Click MCP. The modal opens: Installed lists company servers; Browser and Search are usually preconnected.",
    )

    await flows_click_platform_button(modal, "Каталог", "Catalog")
    search = modal.locator("platform-modal-search-field").first
    await expect(search).to_be_visible(timeout=30_000)
    await search.evaluate(
        """
        (el, value) => {
            el.value = value;
            if (typeof el.requestUpdate === 'function') el.requestUpdate();
            el.dispatchEvent(new CustomEvent('change', {
                detail: { value },
                bubbles: true,
                composed: true,
            }));
        }
        """,
        unique_id,
    )
    await expect(modal.locator("platform-button").filter(has_text=re.compile(r"Установить|Install"))).to_be_visible(
        timeout=30_000,
    )
    await flows_click_platform_button(modal, "Установить", "Install")
    await expect(modal.locator(".mcp-chip").filter(has_text=re.compile(r"Установлен|Installed"))).to_be_visible(
        timeout=60_000,
    )
    await scenario.step(
        "Во вкладке «Каталог» ищем сервер и нажимаем «Установить». После установки он появится в «Подключённых».",
        page,
        label_en="On the Catalog tab, search and click Install. The server then appears under Installed.",
    )

    await flows_api_sync_mcp_server(flows_ui.origin, auth_token_system, server_id)

    flow_id = flows_doc_flow_id("doc_mcp", unique_id)
    _ = await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_graph_payload(
            flow_id,
            name="Flow для MCP",
            description="Учебный граф для MCP tools и MCP-ноды.",
        ),
    )
    _ = await page.goto(f"{flows_ui.origin}/flows/{flow_id}/editor", wait_until="domcontentloaded")
    await expect(page.locator("flow-editor-page")).to_be_visible(timeout=30_000)
    await flows_drop_llm_node(page)
    await expect(page.locator("flows-llm-node-editor")).to_be_visible(timeout=30_000)
    await scenario.step(
        "В редакторе добавляем LLM-ноду. Справа открываются её настройки, включая список tools.",
        page,
        label_en="In the editor, add an LLM node. Its settings panel opens on the right, including tools.",
    )

    llm_editor = page.locator("flows-llm-node-editor").first
    await flows_click_platform_button(llm_editor, "Из библиотеки", "From library")
    await flows_pick_first_mcp_tool_in_picker(page)
    await scenario.step(
        (
            "Нажимаем «Из библиотеки», открываем вкладку MCP и выбираем tool. "
            "Поиск в шапке ищет по имени tool и сервера."
        ),
        page,
        label_en="Click From library, open the MCP tab, and pick a tool. Header search matches tool and server names.",
    )

    await flows_drop_mcp_node(page)
    await flows_pick_first_mcp_tool_in_picker(page)
    await expect(page.locator("flows-flow-canvas g.node[data-node-type='mcp']")).to_have_count(
        1,
        timeout=30_000,
    )
    await scenario.step(
        (
            "Перетаскиваем MCP на канву (или используем палитру). Откроется picker — выбираем tool, "
            "и на графе появится MCP-нода."
        ),
        page,
        label_en="Drop MCP onto the canvas. The picker opens; after you choose a tool, an MCP node appears on the graph.",
    )
