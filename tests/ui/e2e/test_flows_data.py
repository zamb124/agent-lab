"""UI E2E сценарии Flows: ресурсы, переменные и секреты."""

from __future__ import annotations

import os
import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_api_e2e_helpers import flows_seed_company_secret_var
from tests.ui.e2e.flows_e2e_helpers import (
    GREEN_GARDEN_AGENT_NAME,
    GREEN_GARDEN_CATALOG_FILE,
    GREEN_GARDEN_SUPPORT_EMAIL,
    flows_api_create_flow,
    flows_api_get_flow,
    flows_doc_flow_id,
    flows_drop_resource_type,
    flows_llm_payload,
    flows_open_editor,
    flows_open_node_editor,
    flows_open_variables_modal,
    flows_publish_editor,
    flows_save_variable_editor_modal,
    flows_set_platform_field,
    flows_set_selected_llm_prompt,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")


@pytest.mark.scenario(
    service="flows",
    tag="data",
    doc_slug="reuse-with-resources",
    title="Переиспользуем настройки и файлы",
    description=(
        "**Для чего:** эта инструкция подключит общий ресурс файлов к агенту, "
        "чтобы не дублировать каталог в каждой ноде.\n\n"
        "**Какие проблемы решает:** один и тот же PDF-каталог нужен нескольким шагам графа — "
        "удобнее хранить его как resource.\n\n"
        "**Результат:** ресурс files создан на канве и привязан к агенту."
    ),
    title_en="Reuse settings and files with resources",
    description_en=(
        "**What for:** this guide attaches a shared files resource to the agent "
        "so you do not duplicate the catalog in every node.\n\n"
        "**Problems it solves:** the same PDF catalog is needed in several graph steps — "
        "storing it as a resource is cleaner.\n\n"
        "**Result:** a files resource is on the canvas and linked to the agent."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_flows_reuse_with_resources(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    flow_id = flows_doc_flow_id("resources", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(
            flow_id,
            name=GREEN_GARDEN_AGENT_NAME,
            prompt="Помогай покупателю, опираясь на каталог товаров.",
        ),
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, flow_id)
    await flows_drop_resource_type(page, "files", x=640, y=400)
    await scenario.step(
        "Перетащите ресурс files на канву",
        page,
        screenshot_name="files-resource-dropped",
        label_en="Drop a files resource on the canvas",
        details=(
            "В палитре слева в разделе «Ресурсы» перетащите тип files на канву. "
            "Появится resource-нода для общих файлов ветки."
        ),
        details_en=(
            "In the left palette under Resources drag the files type onto the canvas. "
            "A resource node for shared branch files appears."
        ),
    )

    resource_node = page.locator("flows-flow-canvas g.node[data-node-type='resource']").first
    await resource_node.dblclick()
    await expect(
        page.locator("flows-resource-node-editor, flows-resource-property-panel")
    ).to_be_visible(timeout=30_000)
    name_field = page.locator("flows-base-resource-editor platform-field").first
    if await name_field.count() > 0:
        await flows_set_platform_field(name_field, GREEN_GARDEN_CATALOG_FILE)
    await scenario.step(
        "Задайте имя ресурса каталога",
        page,
        screenshot_name="resource-name-set",
        label_en="Name the catalog resource",
        details=(
            f"Откройте свойства ресурса и задайте понятное имя — например "
            f"«{GREEN_GARDEN_CATALOG_FILE}». Так в графе видно, какой файл подключён."
        ),
        details_en=(
            f"Open the resource properties and set a clear name — for example "
            f"«{GREEN_GARDEN_CATALOG_FILE}». The graph then shows which file is attached."
        ),
    )

    await flows_open_node_editor(page, "agent")
    resources_heading = page.locator("flows-llm-node-editor").get_by_text(
        re.compile(r"ресурс|resource", re.I)
    ).first
    await expect(resources_heading).to_be_visible(timeout=15_000)
    await flows_publish_editor(page)
    persisted = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    assert persisted.get("resources"), "flow resources must be persisted after publish"
    await scenario.step(
        "Опубликуйте агента с ресурсом",
        page,
        screenshot_name="resource-published",
        label_en="Publish the agent with the resource",
        details=(
            "**Демонстрация результата.** Ресурс files сохранён в ветке графа — "
            "его можно переиспользовать в нескольких нодах без повторной загрузки.\n\n"
            "**Итог.** Теперь вы умеете добавлять resource на канву и подключать общие "
            "файлы к агенту."
        ),
        details_en=(
            "**Result demonstration.** The files resource is saved on the graph branch — "
            "you can reuse it across nodes without re-uploading.\n\n"
            "**Summary.** You can add a resource to the canvas and attach shared files "
            "to the agent."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="data",
    doc_slug="parameters-and-secrets",
    title="Параметры и секреты агента",
    description=(
        "**Для чего:** эта инструкция вынесет приветствие и контакты в переменные, "
        "а секреты — в защищённое хранилище.\n\n"
        "**Какие проблемы решает:** менять email поддержки в каждом промпте неудобно — "
        "переменные и @var: упрощают сопровождение.\n\n"
        "**Результат:** переменные заданы и подставляются в инструкцию агента."
    ),
    title_en="Agent parameters and secrets",
    description_en=(
        "**What for:** this guide moves greeting and contacts into variables "
        "and secrets into protected storage.\n\n"
        "**Problems it solves:** editing support email in every prompt is tedious — "
        "variables and @var: simplify maintenance.\n\n"
        "**Result:** variables are set and referenced in the agent instruction."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_flows_parameters_and_secrets(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    auth_headers_system: dict[str, str],
    unique_id: str,
    secrets_service,
) -> None:
    _ = secrets_service
    secret_key = f"telegram_bot_token_{unique_id}"
    await flows_seed_company_secret_var(
        auth_headers_system,
        secret_key,
        "demo-telegram-token",
        secret=True,
    )

    flow_id = flows_doc_flow_id("vars", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(
            flow_id,
            name=GREEN_GARDEN_AGENT_NAME,
            prompt="Приветствуй покупателя.",
        ),
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, flow_id)
    modal = await flows_open_variables_modal(page, scope="flow")
    add_btn = modal.locator("platform-button").filter(
        has_text=re.compile(r"Добавить|Add")
    ).first
    await expect(add_btn).to_be_visible(timeout=15_000)
    await add_btn.locator("button").first.click()
    var_editor = page.locator("flows-variable-editor-modal").first
    await expect(var_editor).to_be_visible(timeout=15_000)
    await scenario.step(
        "Откройте переменные агента",
        page,
        screenshot_name="variables-modal-opened",
        label_en="Open agent variables",
        details=(
            "В нижней панели редактора нажмите иконку переменных. Здесь задаются "
            "значения, доступные всему графу через {имя} или @var:."
        ),
        details_en=(
            "In the editor bottom bar click the variables icon. Here you define values "
            "available to the whole graph via {name} or @var:."
        ),
    )

    fields = var_editor.locator("platform-field")
    await flows_set_platform_field(fields.nth(0), "greeting")
    await flows_set_platform_field(fields.nth(1), "Здравствуйте! Это «Зелёный сад».")
    await flows_save_variable_editor_modal(var_editor)
    await flows_open_node_editor(page, "agent")
    await flows_set_selected_llm_prompt(
        page,
        (
            f"Начни с {{greeting}} Почта поддержки: {GREEN_GARDEN_SUPPORT_EMAIL}. "
            f"Токен бота: @var:{secret_key}"
        ),
    )
    await scenario.step(
        "Добавьте переменные и обновите промпт",
        page,
        screenshot_name="prompt-with-variables",
        label_en="Add variables and update the prompt",
        details=(
            f"Создайте переменную greeting и впишите в промпт адрес "
            f"{GREEN_GARDEN_SUPPORT_EMAIL} и секрет @var:{secret_key}. "
            "Так контакты меняются без правки всего текста."
        ),
        details_en=(
            f"Create a greeting variable and put support address "
            f"{GREEN_GARDEN_SUPPORT_EMAIL} and secret @var:{secret_key} in the prompt. "
            "Contacts can change without rewriting the whole instruction."
        ),
    )

    await flows_publish_editor(page)
    persisted = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    prompt = persisted["nodes"]["agent"]["prompt"]
    assert "greeting" in prompt
    assert secret_key in prompt
    await scenario.step(
        "Опубликуйте агента с переменными",
        page,
        screenshot_name="variables-published",
        label_en="Publish the agent with variables",
        details=(
            "**Демонстрация результата.** Промпт содержит ссылки на переменные и секрет — "
            "при запуске подставятся актуальные значения компании.\n\n"
            "**Итог.** Теперь вы умеете открывать переменные flow, хранить секреты через "
            "@var: и использовать их в инструкции агента."
        ),
        details_en=(
            "**Result demonstration.** The prompt references variables and a secret — "
            "at runtime the current company values are substituted.\n\n"
            "**Summary.** You can open flow variables, store secrets via @var:, "
            "and use them in the agent instruction."
        ),
    )
