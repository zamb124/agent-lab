"""Generated documentation scenarios for the Flows editor."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    flows_api_create_flow,
    flows_api_delete_flow,
    flows_api_get_flow,
    flows_click_platform_button,
    flows_doc_flow_id,
    flows_drop_llm_node,
    flows_graph_payload,
    flows_llm_payload,
    flows_publish_editor,
    flows_set_platform_field,
    flows_set_selected_llm_config,
    flows_set_selected_llm_prompt,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="flows",
    tag="editor",
    doc_slug="create-flow",
    title="Flows: создание flow",
    description=(
        "Пошаговая инструкция для обычного пользователя: открыть Flows, выбрать шаблон, "
        "заполнить понятные поля и попасть в редактор с готовой канвой."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_flows_create_graph_flow_scenario(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    flow_id = flows_doc_flow_id("doc_graph", unique_id)
    await flows_api_delete_flow(flows_ui.origin, auth_token_system, flow_id)

    page = ui_page_system
    await page.goto(f"{flows_ui.origin}/flows/", wait_until="domcontentloaded")
    await expect(page.locator("flows-app")).to_be_visible(timeout=30_000)
    await expect(page.locator("flows-catalog-list")).to_be_visible(timeout=30_000)
    await scenario.step(
        "Открываем Flows. Это список ваших flow: здесь можно найти готового агента или создать нового.",
        page,
    )

    await page.locator("flows-catalog-list [data-action='create-flow']").first.click()
    modal = page.locator("flows-flow-create-modal").first
    await expect(modal).to_be_visible(timeout=30_000)
    await scenario.step(
        "Нажимаем плюс. Открывается мастер создания: сначала выбираем тип будущего flow.",
        page,
    )

    await modal.locator("[data-preset-id='graph']").click()
    await expect(modal.locator("platform-field").nth(0)).to_be_visible(timeout=30_000)
    await flows_set_platform_field(modal.locator("platform-field").nth(0), flow_id)
    await flows_set_platform_field(modal.locator("platform-field").nth(1), "Учебный flow")
    await flows_set_platform_field(
        modal.locator("platform-field").nth(2),
        "Простой граф для обучения: стартовая нода, конечная нода и место для следующих шагов.",
    )
    await scenario.step(
        "Заполняем ID, название и описание. ID нужен системе, а название и описание видит человек.",
        page,
    )

    await flows_click_platform_button(modal, "Создать", "Create")
    await expect(page.locator("flow-editor-page")).to_be_visible(timeout=30_000)
    await expect(page.locator("flows-flow-canvas g.node")).to_have_count(2, timeout=30_000)
    await scenario.step(
        "После создания мы сразу попадаем в редактор. На канве уже есть две ноды: Start и End.",
        page,
    )

    created = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    assert created["flow_id"] == flow_id
    assert set(created["nodes"]) >= {"start", "end"}


@pytest.mark.scenario(
    service="flows",
    tag="editor",
    doc_slug="add-llm-node",
    title="Flows: добавление LLM-ноды",
    description=(
        "Инструкция показывает, как добавить LLM Node на канву, открыть настройки ноды, "
        "заполнить промпт и выбрать LLM-профиль."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_flows_add_llm_node_scenario(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    flow_id = flows_doc_flow_id("doc_llm", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_graph_payload(
            flow_id,
            name="Flow для LLM-ноды",
            description="Учебный граф для добавления LLM Node.",
        ),
    )

    page = ui_page_system
    await page.goto(f"{flows_ui.origin}/flows/{flow_id}/editor", wait_until="domcontentloaded")
    await expect(page.locator("flow-editor-page")).to_be_visible(timeout=30_000)
    await expect(page.locator("flows-node-types-sidebar")).to_be_visible(timeout=30_000)
    await scenario.step(
        "Открываем редактор flow. Слева находится палитра нод, в центре находится канва.",
        page,
    )

    await flows_drop_llm_node(page)
    await expect(page.locator("flows-property-panel flows-llm-node-editor")).to_be_visible(timeout=30_000)
    await scenario.step(
        "Перетаскиваем LLM Node из палитры на канву. Справа открываются настройки выбранной ноды.",
        page,
    )

    prompt = (
        "Ты помощник в учебном flow. Отвечай простыми словами, сначала уточняй задачу, "
        "а затем предлагай следующий шаг."
    )
    await flows_set_selected_llm_prompt(page, prompt)
    await flows_set_selected_llm_config(
        page,
        {
            "provider": "humanitec_llm",
            "model": "auto",
            "temperature": 0.2,
            "max_tokens": 1024,
        },
    )
    await page.locator("flows-property-panel prompt-editor").scroll_into_view_if_needed(timeout=30_000)
    await scenario.step(
        "Заполняем промпт и LLM-настройки. Промпт говорит агенту, как вести себя с пользователем.",
        page,
    )

    await flows_publish_editor(page)
    await scenario.step(
        "Нажимаем Publish. Так черновик сохраняется, и flow можно запускать или продолжать редактировать позже.",
        page,
    )

    saved = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    llm_nodes = [node for node in saved["nodes"].values() if node.get("type") == "llm_node"]
    assert len(llm_nodes) == 1
    assert llm_nodes[0]["prompt"] == prompt
    assert llm_nodes[0]["llm"]["provider"] == "humanitec_llm"


@pytest.mark.scenario(
    service="flows",
    tag="editor",
    doc_slug="edit-llm-flow",
    title="Flows: редактирование flow",
    description=(
        "Инструкция для повторного редактирования: открыть готовый flow, изменить название, "
        "обновить промпт LLM-ноды и сохранить изменения."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_flows_edit_llm_flow_scenario(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    flow_id = flows_doc_flow_id("doc_edit", unique_id)
    original_prompt = "Ты коротко объясняешь пользователю, что делает flow."
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(
            flow_id,
            name="Flow до редактирования",
            description="Учебный flow с одной LLM-нодой.",
            prompt=original_prompt,
        ),
    )

    page = ui_page_system
    await page.goto(f"{flows_ui.origin}/flows/{flow_id}/editor", wait_until="domcontentloaded")
    await expect(page.locator("flow-editor-page")).to_be_visible(timeout=30_000)
    llm_node = page.locator("flows-flow-canvas g.node[data-node-type='llm_node']").first
    await expect(llm_node).to_be_visible(timeout=30_000)
    await llm_node.click()
    await expect(page.locator("flows-property-panel flows-llm-node-editor")).to_be_visible(timeout=30_000)
    await scenario.step(
        "Открываем уже готовый flow и кликаем по LLM-ноду. Справа снова видны ее настройки.",
        page,
    )

    new_name = "Flow после редактирования"
    new_prompt = (
        "Ты объясняешь работу flow очень простыми словами. "
        "Сначала скажи, что сейчас произойдет, потом попроси пользователя подтвердить действие."
    )
    name_input = page.locator("flows-editor-header input.flow-name-input").first
    await expect(name_input).to_be_visible(timeout=30_000)
    await name_input.fill(new_name)
    await flows_set_selected_llm_prompt(page, new_prompt)
    await page.locator("flows-property-panel prompt-editor").scroll_into_view_if_needed(timeout=30_000)
    await scenario.step(
        "Меняем название flow и переписываем промпт. Это обычное редактирование: как переименовать файл и исправить текст.",
        page,
    )

    await flows_publish_editor(page)
    await scenario.step(
        "Сохраняем изменения через Publish. После этого новое название и промпт лежат в сохраненной версии flow.",
        page,
    )

    saved = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    assert saved["name"] == new_name
    assert saved["nodes"]["agent"]["prompt"] == new_prompt
