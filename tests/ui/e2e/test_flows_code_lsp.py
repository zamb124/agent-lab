"""Playwright: живой CodeMirror + language server в code_node. Без моков сети LSP."""

from __future__ import annotations

import os

import pytest
from playwright.async_api import Page, Request, expect

from tests.ui.e2e.flows_e2e_helpers import (
    GREEN_GARDEN_AGENT_NAME,
    flows_api_create_flow,
    flows_code_assert_no_lsp_failed_toast,
    flows_code_caret_after,
    flows_code_echo_payload,
    flows_code_editor_trigger_completion,
    flows_code_hover_token,
    flows_code_wait_completion_labels,
    flows_code_wait_diagnostic,
    flows_code_wait_editor_mounted,
    flows_code_wait_lsp_ready,
    flows_doc_flow_id,
    flows_e2e_ensure_canvas_layout,
    flows_open_editor,
    flows_open_node_editor,
    flows_open_raw_json_modal,
    flows_select_canvas_node,
    flows_set_code_node_source,
    flows_switch_code_language,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")

_PYTHON_JSON_PREFIX = "import json\n\nasync def run(args, state):\n    data = json."
_PYTHON_FILES_PREFIX = (
    "import json\n\nasync def run(args, state):\n    data = json.loads('{}')\n    created = files."
)
_PYTHON_FILES_HOVER = (
    "import json\n\nasync def run(args, state):\n"
    "    data = json.loads('{}')\n"
    "    created = await files.create(content='x')\n"
    "    return created\n"
)
_JS_LODASH_PREFIX = (
    "import lodash from 'lodash';\n\nasync function run(args, state) {\n  const value = lodash."
)
_PYTHON_HTTPX = "import httpx\n\nasync def run(args, state):\n    return args\n"


async def _open_code_canvas(
    page: Page,
    flows_ui: AppUI,
    auth_token_system: str,
    unique_id: str,
) -> str:
    flow_id = flows_doc_flow_id("code_lsp", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_code_echo_payload(flow_id, name=GREEN_GARDEN_AGENT_NAME),
    )
    await flows_open_editor(page, flows_ui, flow_id)
    await flows_e2e_ensure_canvas_layout(page)
    await expect(page.locator("flows-node-types-sidebar .node-item").first).to_be_visible(
        timeout=30_000
    )
    await flows_select_canvas_node(page, "echo")
    return flow_id


async def _open_code_workbench(
    page: Page,
    flows_ui: AppUI,
    auth_token_system: str,
    unique_id: str,
) -> str:
    flow_id = await _open_code_canvas(page, flows_ui, auth_token_system, unique_id)
    _ = await flows_open_node_editor(page, "echo")
    await expect(
        page.locator("flows-floating-panel[show-backdrop] flows-code-node-editor").first
    ).to_be_visible(timeout=60_000)
    await expect(
        page.locator("flows-floating-panel[show-backdrop] flows-code-workbench").first
    ).to_be_visible(timeout=60_000)
    await flows_code_wait_editor_mounted(page)
    await flows_code_wait_lsp_ready(page, language="python")
    return flow_id


@pytest.mark.scenario(
    service="flows",
    tag="nodes",
    doc_slug="code-editor-completions",
    timeout_seconds=240,
    title="Как редактор кода подсказывает методы как IDE",
    title_en="How the code editor suggests methods like an IDE",
    description=(
        "**Для чего:** эта инструкция поможет писать код ноды с подсказками "
        "стандартной библиотеки и платформенных методов, как в обычной IDE.\n\n"
        "**Какие проблемы решает:** не нужно помнить наизусть `json.loads` или "
        "`files.create` — редактор сам показывает подходящие имена и краткую справку.\n\n"
        "**Результат:** в редакторе кода агента видны автодополнение и подсказка по наведению."
    ),
    description_en=(
        "**What for:** this guide shows how to write node code with standard-library "
        "and platform method suggestions, like in a regular IDE.\n\n"
        "**Problems it solves:** you do not need to memorize `json.loads` or "
        "`files.create` — the editor lists matching names and a short hint.\n\n"
        "**Result:** the agent code editor shows completions and a hover tooltip."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_flows_code_editor_completions_scenario(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
    sandbox_services: dict[str, str],
) -> None:
    _ = sandbox_services
    page = ui_page_system
    _ = await _open_code_canvas(page, flows_ui, auth_token_system, unique_id)
    await scenario.step(
        "Откройте ноду кода",
        page,
        screenshot_name="code-node-editor",
        label_en="Open the code node",
        details=(
            "На канве выберите ноду «Код» и откройте её редактор. Здесь пишется функция "
            "обработки данных между шагами агента."
        ),
        details_en=(
            "On the canvas select the Code node and open its editor. This is where you "
            "write the function that transforms data between agent steps."
        ),
    )
    _ = await flows_open_node_editor(page, "echo")
    await expect(
        page.locator("flows-floating-panel[show-backdrop] flows-code-workbench").first
    ).to_be_visible(timeout=60_000)
    await flows_code_wait_editor_mounted(page)
    await flows_code_wait_lsp_ready(page, language="python")

    await flows_set_code_node_source(page, _PYTHON_JSON_PREFIX)
    await flows_code_wait_lsp_ready(page, language="python")
    await flows_code_caret_after(page, "json.")
    await flows_code_editor_trigger_completion(page)
    labels = await flows_code_wait_completion_labels(page, "loads")
    assert any("dumps" in label or label == "dumps" for label in labels) or any(
        "loads" in label for label in labels
    )
    await flows_code_assert_no_lsp_failed_toast(page)
    await scenario.step(
        "Начните писать json. и выберите подсказку",
        page,
        screenshot_name="json-completion",
        label_en="Type json. and pick a suggestion",
        details=(
            "В теле функции введите `json.` и вызовите автодополнение (Ctrl+Пробел). "
            "Появятся стандартные методы вроде loads и dumps — их не нужно искать в документации."
        ),
        details_en=(
            "In the function body type `json.` and trigger completion (Ctrl+Space). "
            "Standard methods such as loads and dumps appear, so you do not look them up."
        ),
    )

    await page.keyboard.press("Escape")
    await flows_set_code_node_source(page, _PYTHON_FILES_PREFIX)
    await flows_code_wait_lsp_ready(page, language="python")
    await flows_code_caret_after(page, "files.")
    await flows_code_editor_trigger_completion(page)
    _ = await flows_code_wait_completion_labels(page, "create")
    await scenario.step(
        "Допишите files. — редактор подскажет методы платформы",
        page,
        screenshot_name="files-completion",
        label_en="Type files. to see platform methods",
        details=(
            "На новой строке введите `files.` и снова Ctrl+Пробел. В списке будет метод "
            "создания файла платформы — так код ноды вызывает capabilities, а не запрещённый open()."
        ),
        details_en=(
            "On a new line type `files.` and press Ctrl+Space again. The list includes the "
            "platform file-create method — node code calls capabilities instead of forbidden open()."
        ),
    )

    await page.keyboard.press("Escape")
    await flows_set_code_node_source(page, _PYTHON_FILES_HOVER)
    await flows_code_wait_lsp_ready(page, language="python")
    hover_text = await flows_code_hover_token(page, "files.create")
    assert hover_text
    await scenario.step(
        "Наведите курсор на имя, чтобы увидеть справку",
        page,
        screenshot_name="hover-docs",
        label_en="Hover a name to see its hint",
        details=(
            "**Итог.** Редактор кода агента работает как IDE: после точки видны методы "
            "json и files, а наведение показывает краткую справку. Так быстрее писать "
            "обработку данных и меньше опечаток в именах."
        ),
        details_en=(
            "**Result demonstration.** The agent code editor behaves like an IDE: a dot "
            "lists json and files methods, and hover shows a short hint.\n\n"
            "**Summary.** You can write data transforms faster and with fewer name typos."
        ),
    )


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_flows_code_editor_javascript_lodash_completion(
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
    sandbox_services: dict[str, str],
) -> None:
    _ = sandbox_services
    page = ui_page_system
    _ = await _open_code_workbench(page, flows_ui, auth_token_system, unique_id)
    await flows_switch_code_language(page, "javascript")
    await flows_code_wait_lsp_ready(page, language="javascript")
    await flows_set_code_node_source(page, _JS_LODASH_PREFIX)
    await flows_code_wait_lsp_ready(page, language="javascript")
    await flows_code_caret_after(page, "lodash.")
    await flows_code_editor_trigger_completion(page)
    _ = await flows_code_wait_completion_labels(page, "get")
    await flows_code_assert_no_lsp_failed_toast(page)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_flows_raw_json_modal_does_not_open_lsp_session(
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
    sandbox_services: dict[str, str],
) -> None:
    _ = sandbox_services
    page = ui_page_system
    flow_id = flows_doc_flow_id("code_json", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_code_echo_payload(flow_id, name=GREEN_GARDEN_AGENT_NAME),
    )
    await flows_open_editor(page, flows_ui, flow_id)
    hits: list[str] = []

    def _on_request(request: Request) -> None:
        if "/flows/api/v1/code/lsp/session" in request.url:
            hits.append(request.url)

    page.on("request", _on_request)
    _ = await flows_open_raw_json_modal(page)
    json_editor = page.locator(
        "flows-raw-json-modal flows-code-editor, platform-modal flows-code-editor"
    ).first
    await expect(json_editor).to_be_visible(timeout=30_000)
    await page.wait_for_timeout(2_000)
    page.remove_listener("request", _on_request)
    assert hits == []


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_flows_code_editor_httpx_import_shows_diagnostic(
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
    sandbox_services: dict[str, str],
) -> None:
    _ = sandbox_services
    page = ui_page_system
    _ = await _open_code_workbench(page, flows_ui, auth_token_system, unique_id)
    await flows_set_code_node_source(page, _PYTHON_HTTPX)
    await flows_code_wait_lsp_ready(page, language="python")
    await flows_code_wait_diagnostic(page)
    await flows_code_assert_no_lsp_failed_toast(page)
