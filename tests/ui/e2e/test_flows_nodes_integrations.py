"""UI E2E сценарии Flows: интеграционные ноды (код, API, MCP, каналы, внешний агент)."""

from __future__ import annotations

import os
import re

import pytest
from playwright.async_api import Page, expect

from apps.flows.src.services.mcp_catalog_ids import server_id_from_catalog_id
from tests.ui.e2e.flows_e2e_helpers import (
    GREEN_GARDEN_AGENT_NAME,
    GREEN_GARDEN_TELEGRAM_BOT,
    flows_api_create_flow,
    flows_api_get_flow,
    flows_api_sync_mcp_server,
    flows_click_platform_button,
    flows_code_echo_payload,
    flows_doc_flow_id,
    flows_drop_mcp_node,
    flows_drop_node,
    flows_ensure_channel_node_telegram,
    flows_external_api_payload,
    flows_graph_payload,
    flows_llm_payload,
    flows_open_editor,
    flows_open_mcp_servers_modal,
    flows_open_node_editor,
    flows_pick_first_mcp_tool_in_picker,
    flows_publish_editor,
    flows_seed_mcp_store_catalog_entry,
    flows_set_code_node_source,
    flows_set_external_api_url,
    flows_set_remote_flow_url,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")

_TRACKER_URL = "https://httpbin.org/get?order_id={order_id}"
_REMOTE_AGENT_URL = "https://partner.example.com/a2a/green-garden-returns"


@pytest.mark.scenario(
    service="flows",
    tag="nodes",
    doc_slug="process-with-code",
    title="Обрабатываем данные кодом",
    description=(
        "**Для чего:** эта инструкция покажет, как посчитать или преобразовать данные "
        "внутри агента с помощью ноды кода.\n\n"
        "**Какие проблемы решает:** не всё можно описать промптом — иногда нужен точный "
        "расчёт или преобразование полей заказа.\n\n"
        "**Результат:** нода кода эхо-обрабатывает вход и готова к запуску в графе."
    ),
    title_en="Process data with a code node",
    description_en=(
        "**What for:** this guide shows how to compute or transform data inside an agent "
        "with a code node.\n\n"
        "**Problems it solves:** not everything fits a prompt — sometimes you need exact "
        "calculations or order field transforms.\n\n"
        "**Result:** a code echo node is ready to run in the graph."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_flows_process_with_code(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    flow_id = flows_doc_flow_id("code_echo", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_graph_payload(flow_id, name=GREEN_GARDEN_AGENT_NAME),
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, flow_id)
    code_node_id = await flows_drop_node(page, "code", x=520, y=320)
    await scenario.step(
        "Добавьте ноду кода на канву",
        page,
        screenshot_name="code-node-dropped",
        label_en="Add a code node to the canvas",
        details=(
            "Перетащите ноду «Код» из палитры слева на канву. Она нужна для точных "
            "вычислений и преобразований данных между шагами агента."
        ),
        details_en=(
            "Drag a Code node from the left palette onto the canvas. Use it for precise "
            "calculations and data transforms between agent steps."
        ),
    )

    _ = await flows_open_node_editor(page, code_node_id)
    await expect(page.locator("flows-code-workbench").first).to_be_visible(timeout=30_000)
    echo_code = (
        "async def run(args, state):\n"
        "    content = str(state.get('content', ''))\n"
        "    state['response'] = 'echo:' + content\n"
        "    return state\n"
    )
    await flows_set_code_node_source(page, echo_code)
    code_editor = page.locator("flows-code-workbench").first
    await expect(code_editor).to_contain_text("echo:", timeout=15_000)
    await scenario.step(
        "Напишите код обработки",
        page,
        screenshot_name="code-source-filled",
        label_en="Write the processing code",
        details=(
            "Во вкладке «Код» опишите функцию run: она читает вход и записывает результат "
            "в state['response']. Так следующая нода получит готовое значение."
        ),
        details_en=(
            "On the Code tab define run: it reads input and writes the result to "
            "state['response'] so the next node gets a ready value."
        ),
    )

    await flows_open_node_editor(page, code_node_id)
    await expect(page.locator("flows-code-workbench").first).to_contain_text("echo:", timeout=15_000)
    await scenario.step(
        "Проверьте код перед публикацией",
        page,
        screenshot_name="code-source-reviewed",
        label_en="Review the code before publishing",
        details=(
            "Снова откройте ноду кода и убедитесь, что логика echo на месте. "
            "Так вы проверяете черновик до сохранения в опубликованную версию."
        ),
        details_en=(
            "Reopen the code node and confirm the echo logic is still there. "
            "This verifies the draft before saving to the published version."
        ),
    )

    await flows_publish_editor(page)
    persisted = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    code_nodes = [n for n in persisted["nodes"].values() if n.get("type") == "code"]
    assert len(code_nodes) >= 1
    assert any("echo:" in (node.get("code") or "") for node in code_nodes), code_nodes
    await scenario.step(
        "Опубликуйте граф с кодом",
        page,
        screenshot_name="code-node-published",
        label_en="Publish the graph with code",
        details=(
            "**Демонстрация результата.** После публикации код сохранён в ноде — "
            "при повторном открытии видна та же логика echo.\n\n"
            "**Итог.** Теперь вы умеете добавлять ноду кода и писать обработку данных "
            "внутри агента «Зелёного сада»."
        ),
        details_en=(
            "**Result demonstration.** After publishing the code is saved on the node — "
            "reopening shows the same echo logic.\n\n"
            "**Summary.** You can add a code node and write data processing inside "
            "the Green Garden agent."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="nodes",
    doc_slug="call-order-tracking-api",
    title="Подключаем сервис отслеживания заказов",
    description=(
        "**Для чего:** эта инструкция поможет получать статус заказа из внешнего HTTP-сервиса.\n\n"
        "**Какие проблемы решает:** покупатель спрашивает «где мой заказ», а ответ нужно "
        "взять из API службы доставки.\n\n"
        "**Результат:** нода внешнего API настроена на запрос статуса заказа."
    ),
    title_en="Connect an order tracking service",
    description_en=(
        "**What for:** this guide helps you fetch order status from an external HTTP service.\n\n"
        "**Problems it solves:** the customer asks where the order is and the answer must "
        "come from a delivery API.\n\n"
        "**Result:** an external API node is configured for order status requests."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_flows_call_order_tracking_api(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    flow_id = flows_doc_flow_id("order_api", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(flow_id, name=GREEN_GARDEN_AGENT_NAME, prompt="Помогай с заказами."),
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, flow_id)
    api_node_id = await flows_drop_node(page, "external_api", x=540, y=360)
    await scenario.step(
        "Добавьте ноду внешнего API",
        page,
        screenshot_name="external-api-dropped",
        label_en="Add an external API node",
        details=(
            "Перетащите ноду «Внешний API» на канву. Через неё агент обращается "
            "к HTTP-сервисам вроде трекера заказов."
        ),
        details_en=(
            "Drag an External API node onto the canvas. Through it the agent calls "
            "HTTP services such as an order tracker."
        ),
    )

    _ = await flows_open_node_editor(page, api_node_id)
    await expect(page.locator("flows-external-api-editor")).to_be_visible(timeout=30_000)
    await flows_set_external_api_url(page, _TRACKER_URL)
    url_field = page.locator("flows-external-api-editor platform-field").first
    await expect(url_field).to_be_visible(timeout=15_000)
    await scenario.step(
        "Укажите адрес сервиса заказов",
        page,
        screenshot_name="tracker-url-configured",
        label_en="Set the order service URL",
        details=(
            "В поле URL впишите адрес сервиса отслеживания. Можно подставлять переменные "
            "в фигурных скобках — например номер заказа из диалога."
        ),
        details_en=(
            "Enter the tracking service URL. You can insert variables in curly braces, "
            "for example the order number from the chat."
        ),
    )

    await flows_open_node_editor(page, api_node_id)
    await expect(page.locator("flows-external-api-editor platform-field[input-type='url']").get_by_role("textbox")).to_have_value(
        re.compile(r"order_id"), timeout=5_000
    )
    await scenario.step(
        "Проверьте URL с переменной заказа",
        page,
        screenshot_name="tracker-url-with-variable",
        label_en="Verify the URL with order variable",
        details=(
            "Убедитесь, что в адресе есть placeholder {order_id} — агент подставит "
            "номер заказа из диалога при вызове сервиса доставки."
        ),
        details_en=(
            "Confirm the address includes the {order_id} placeholder — the agent will "
            "insert the order number from the chat when calling the delivery service."
        ),
    )

    await flows_publish_editor(page)
    persisted = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    api_nodes = [n for n in persisted["nodes"].values() if n.get("type") == "external_api"]
    assert len(api_nodes) == 1
    assert "order_id" in api_nodes[0].get("url", "")
    await scenario.step(
        "Опубликуйте подключение API",
        page,
        screenshot_name="order-api-published",
        label_en="Publish the API connection",
        details=(
            "**Демонстрация результата.** Нода «Где мой заказ» сохранена с URL сервиса — "
            "агент готов запрашивать статус заказа по HTTP.\n\n"
            "**Итог.** Теперь вы умеете добавлять external API-ноду и настраивать вызов "
            "внешнего сервиса доставки."
        ),
        details_en=(
            "**Result demonstration.** The order tracker node is saved with the service URL — "
            "the agent can request order status over HTTP.\n\n"
            "**Summary.** You can add an external API node and configure a delivery "
            "service call."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="nodes",
    doc_slug="connect-mcp-tool",
    title="Подключаем MCP-инструмент",
    description=(
        "**Для чего:** эта инструкция расширит агента инструментами MCP-сервера.\n\n"
        "**Какие проблемы решает:** готовых встроенных tools не хватает, а внешний MCP "
        "даёт новые операции без переписывания графа.\n\n"
        "**Результат:** MCP-сервер установлен, tool добавлен в агента и на канву."
    ),
    title_en="Connect an MCP tool",
    description_en=(
        "**What for:** this guide extends the agent with tools from an MCP server.\n\n"
        "**Problems it solves:** built-in tools are not enough and external MCP adds "
        "new operations without rewriting the graph.\n\n"
        "**Result:** the MCP server is installed, the tool is added to the agent and canvas."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(360)
async def test_flows_connect_mcp_tool(
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
    await page.goto(f"{flows_ui.origin}/flows/", wait_until="domcontentloaded")
    modal = await flows_open_mcp_servers_modal(page)
    await flows_click_platform_button(modal, "Каталог", "Catalog")
    search = modal.locator("platform-modal-search-field").first
    await search.evaluate(
        """
        (el, value) => {
            el.value = value;
            if (typeof el.requestUpdate === 'function') el.requestUpdate();
            el.dispatchEvent(new CustomEvent('change', { detail: { value }, bubbles: true, composed: true }));
        }
        """,
        unique_id,
    )
    await flows_click_platform_button(modal, "Установить", "Install")
    await flows_click_platform_button(modal, "Подключённые", "Installed")
    await expect(modal.get_by_text(server_id, exact=True)).to_be_visible(timeout=5_000)
    await scenario.step(
        "Установите MCP-сервер из каталога",
        page,
        screenshot_name="mcp-server-installed",
        label_en="Install an MCP server from the catalog",
        details=(
            "На главной Flows откройте MCP, перейдите в каталог, найдите сервер и нажмите "
            "«Установить». После этого инструменты сервера доступны в редакторе."
        ),
        details_en=(
            "On the Flows home open MCP, go to the catalog, find the server and click "
            "Install. Its tools then become available in the editor."
        ),
    )

    await flows_api_sync_mcp_server(flows_ui.origin, auth_token_system, server_id)
    flow_id = flows_doc_flow_id("mcp_tool", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_graph_payload(flow_id, name=GREEN_GARDEN_AGENT_NAME),
    )
    await flows_open_editor(page, flows_ui, flow_id)
    await flows_drop_mcp_node(page)
    await flows_pick_first_mcp_tool_in_picker(page)
    await expect(page.locator("flows-flow-canvas g.node[data-node-type='mcp']")).to_have_count(
        1,
        timeout=30_000,
    )
    await scenario.step(
        "Добавьте MCP-инструмент на канву",
        page,
        screenshot_name="mcp-node-on-canvas",
        label_en="Add an MCP tool to the canvas",
        details=(
            "В редакторе перетащите MCP на канву и выберите tool в окне библиотеки. "
            "На графе появится отдельная MCP-нода с выбранным инструментом."
        ),
        details_en=(
            "In the editor drop MCP onto the canvas and pick a tool in the library "
            "dialog. A dedicated MCP node with that tool appears on the graph."
        ),
    )

    # The new picker selects the created node and opens its floating properties
    # panel immediately; clicking through the backdrop only waits on interception.
    await expect(page.locator("flows-mcp-node-editor, flows-base-node-editor").first).to_be_visible(
        timeout=5_000
    )
    await scenario.step(
        "Проверьте настройки MCP-ноды",
        page,
        screenshot_name="mcp-node-settings-open",
        label_en="Review the MCP node settings",
        details=(
            "После выбора инструмента проверьте автоматически открытую панель свойств — "
            "там видно, какой инструмент сервера подключён к графу."
        ),
        details_en=(
            "After choosing the tool, review the properties panel that opens automatically. "
            "It shows which server tool is wired into the graph."
        ),
    )

    await flows_publish_editor(page)
    persisted = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    mcp_nodes = [n for n in persisted["nodes"].values() if n.get("type") == "mcp"]
    assert len(mcp_nodes) == 1
    await scenario.step(
        "Опубликуйте агента с MCP",
        page,
        screenshot_name="mcp-tool-published",
        label_en="Publish the agent with MCP",
        details=(
            "**Демонстрация результата.** MCP-нода видна на канве, а в сохранённом графе "
            "есть подключённый инструмент сервера.\n\n"
            "**Итог.** Теперь вы умеете устанавливать MCP-сервер и добавлять его tools "
            "в агента «Зелёного сада»."
        ),
        details_en=(
            "**Result demonstration.** The MCP node is visible on the canvas and the "
            "saved graph includes the server tool.\n\n"
            "**Summary.** You can install an MCP server and add its tools to the "
            "Green Garden agent."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="nodes",
    doc_slug="notify-in-telegram",
    title="Отправляем ответ в Telegram",
    description=(
        "**Для чего:** эта инструкция настроит доставку сообщения покупателю в Telegram.\n\n"
        "**Какие проблемы решает:** ответ агента нужно продублировать в бот магазина, "
        "а не только показать в тестовом чате.\n\n"
        "**Результат:** нода канала Telegram с демо-настройками бота."
    ),
    title_en="Send the answer to Telegram",
    description_en=(
        "**What for:** this guide configures delivering a message to the customer in Telegram.\n\n"
        "**Problems it solves:** the agent reply must also reach the store bot, "
        "not only the test chat.\n\n"
        "**Result:** a Telegram channel node with demo bot settings."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_flows_notify_in_telegram(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    flow_id = flows_doc_flow_id("telegram_ch", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_code_echo_payload(flow_id, name=GREEN_GARDEN_AGENT_NAME),
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, flow_id)
    channel_node_id = await flows_drop_node(page, "channel", x=560, y=340)
    _ = await flows_open_node_editor(page, channel_node_id)
    await expect(page.locator("flows-channel-node-editor")).to_be_visible(timeout=30_000)
    await scenario.step(
        "Добавьте ноду канала",
        page,
        screenshot_name="channel-node-opened",
        label_en="Add a channel node",
        details=(
            "Перетащите ноду «Канал» и откройте её настройки. Здесь выбирается способ "
            "доставки ответа — Telegram, email или webhook."
        ),
        details_en=(
            "Drag a Channel node and open its settings. Here you choose how to deliver "
            "the reply — Telegram, email, or webhook."
        ),
    )

    editor = page.locator("flows-channel-node-editor").first
    token_field = editor.locator("platform-variable-input, platform-field").first
    await expect(token_field).to_be_visible(timeout=15_000)
    await flows_ensure_channel_node_telegram(page)
    await expect(editor.get_by_text(re.compile(r"Telegram|телеграм", re.I)).first).to_be_visible(
        timeout=15_000
    )
    await scenario.step(
        "Выберите Telegram и укажите бота",
        page,
        screenshot_name="telegram-channel-configured",
        label_en="Choose Telegram and set the bot",
        details=(
            f"Оставьте канал Telegram и укажите токен бота (в учебном примере — "
            f"«{GREEN_GARDEN_TELEGRAM_BOT}»). Так агент знает, куда отправлять уведомление."
        ),
        details_en=(
            f"Keep Telegram as the channel and set the bot token (in this tutorial — "
            f"«{GREEN_GARDEN_TELEGRAM_BOT}»). The agent then knows where to send notifications."
        ),
    )

    await flows_open_node_editor(page, channel_node_id)
    await expect(page.locator("flows-channel-node-editor")).to_be_visible(timeout=15_000)
    await scenario.step(
        "Проверьте настройки канала перед публикацией",
        page,
        screenshot_name="telegram-channel-reviewed",
        label_en="Review channel settings before publishing",
        details=(
            "Снова откройте ноду канала и убедитесь, что выбран Telegram и указан токен "
            "через переменную — доставка ответов пойдёт в бот магазина."
        ),
        details_en=(
            "Reopen the channel node and confirm Telegram is selected with the token "
            "via a variable — replies will route to the store bot."
        ),
    )

    await flows_publish_editor(page)
    persisted = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    channel_nodes = [n for n in persisted["nodes"].values() if n.get("type") == "channel"]
    assert len(channel_nodes) == 1
    assert channel_nodes[0].get("channel") == "telegram"
    await scenario.step(
        "Опубликуйте канал Telegram",
        page,
        screenshot_name="telegram-channel-published",
        label_en="Publish the Telegram channel",
        details=(
            "**Демонстрация результата.** Нода канала Telegram сохранена в графе — "
            "агент может отправлять ответы в бот магазина.\n\n"
            "**Итог.** Теперь вы умеете добавлять channel-ноду и настраивать доставку "
            "сообщений в Telegram."
        ),
        details_en=(
            "**Result demonstration.** The Telegram channel node is saved in the graph — "
            "the agent can send replies to the store bot.\n\n"
            "**Summary.** You can add a channel node and configure Telegram message delivery."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="nodes",
    doc_slug="call-remote-agent",
    title="Вызываем внешнего агента",
    description=(
        "**Для чего:** эта инструкция подключит агента-партнёра по протоколу A2A.\n\n"
        "**Какие проблемы решает:** часть сценариев живёт у другого поставщика, "
        "и нужно вызвать его удалённого агента из своего графа.\n\n"
        "**Результат:** нода внешнего агента с адресом и веткой."
    ),
    title_en="Call a remote agent",
    description_en=(
        "**What for:** this guide connects a partner agent over the A2A protocol.\n\n"
        "**Problems it solves:** some scenarios live with another provider and you need "
        "to call their remote agent from your graph.\n\n"
        "**Result:** a remote agent node with URL and branch."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_flows_call_remote_agent(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    flow_id = flows_doc_flow_id("remote_agent", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_external_api_payload(flow_id, name=GREEN_GARDEN_AGENT_NAME, url=_TRACKER_URL),
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, flow_id)
    remote_node_id = await flows_drop_node(page, "remote_flow", x=580, y=360)
    _ = await flows_open_node_editor(page, remote_node_id)
    await expect(page.locator("flows-remote-flow-editor")).to_be_visible(timeout=30_000)
    await scenario.step(
        "Добавьте ноду внешнего агента",
        page,
        screenshot_name="remote-flow-node-opened",
        label_en="Add a remote agent node",
        details=(
            "Перетащите ноду «Внешний агент» и откройте её настройки. Она вызывает "
            "агента другой компании по URL или идентификатору."
        ),
        details_en=(
            "Drag a Remote agent node and open its settings. It calls another company's "
            "agent by URL or identifier."
        ),
    )

    editor = page.locator("flows-remote-flow-editor").first
    await flows_set_remote_flow_url(page, _REMOTE_AGENT_URL)
    await expect(editor.locator(".remote-flow-endpoint-stack platform-field").first.get_by_role("textbox")).to_have_value(
        _REMOTE_AGENT_URL, timeout=5_000
    )
    await scenario.step(
        "Укажите адрес партнёрского агента",
        page,
        screenshot_name="remote-agent-url-set",
        label_en="Set the partner agent address",
        details=(
            "В режиме URL впишите адрес агента-партнёра и при необходимости ветку. "
            "Так ваш агент знает, куда отправить запрос покупателя."
        ),
        details_en=(
            "In URL mode enter the partner agent address and branch if needed. "
            "Your agent then knows where to forward the customer request."
        ),
    )

    await flows_open_node_editor(page, remote_node_id)
    await expect(page.locator("flows-remote-flow-editor .remote-flow-endpoint-stack platform-field").first.get_by_role("textbox")).to_have_value(
        _REMOTE_AGENT_URL, timeout=5_000
    )
    await scenario.step(
        "Проверьте адрес перед публикацией",
        page,
        screenshot_name="remote-agent-url-reviewed",
        label_en="Review the address before publishing",
        details=(
            "Откройте ноду снова и убедитесь, что URL партнёра сохранён в черновике — "
            "граф готов делегировать запрос внешнему агенту."
        ),
        details_en=(
            "Reopen the node and confirm the partner URL is in the draft — "
            "the graph is ready to delegate requests to an external agent."
        ),
    )

    await flows_publish_editor(page)
    persisted = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    remote_nodes = [n for n in persisted["nodes"].values() if n.get("type") == "remote_flow"]
    assert len(remote_nodes) >= 1
    assert _REMOTE_AGENT_URL in (remote_nodes[-1].get("url") or "")
    await scenario.step(
        "Опубликуйте вызов внешнего агента",
        page,
        screenshot_name="remote-agent-published",
        label_en="Publish the remote agent call",
        details=(
            "**Демонстрация результата.** Нода внешнего агента сохранена с указанным URL — "
            "граф готов делегировать запрос партнёру.\n\n"
            "**Итог.** Теперь вы умеете добавлять remote_flow-ноду и настраивать вызов "
            "внешнего агента по A2A."
        ),
        details_en=(
            "**Result demonstration.** The remote agent node is saved with the URL — "
            "the graph is ready to delegate requests to a partner.\n\n"
            "**Summary.** You can add a remote_flow node and configure an external "
            "agent call over A2A."
        ),
    )
