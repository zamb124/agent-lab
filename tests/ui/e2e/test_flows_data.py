"""UI E2E сценарии Flows: ресурсы, переменные и секреты."""

from __future__ import annotations

import os
import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_api_e2e_helpers import flows_seed_company_secret_var
from tests.ui.e2e.flows_e2e_helpers import (
    GREEN_GARDEN_AGENT_NAME,
    GREEN_GARDEN_SUPPORT_EMAIL,
    flows_api_create_flow,
    flows_api_get_flow,
    flows_canvas_node_ids_of_type,
    flows_doc_flow_id,
    flows_drop_resource_type,
    flows_e2e_ensure_canvas_layout,
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
    await flows_e2e_ensure_canvas_layout(page)
    await flows_drop_resource_type(page, "files", x=640, y=400)
    resource_ids = await flows_canvas_node_ids_of_type(page, "resource")
    if not resource_ids:
        raise AssertionError("resource node missing after palette drop")

    async def _ensure_resource_node() -> str:
        ids = await flows_canvas_node_ids_of_type(page, "resource")
        if ids:
            return ids[0]
        await flows_drop_resource_type(page, "files", x=640, y=400)
        ids = await flows_canvas_node_ids_of_type(page, "resource")
        if not ids:
            raise AssertionError("resource node missing after palette drop")
        return ids[0]

    resource_node_id = resource_ids[0]
    await scenario.step(
        "Перетащите ресурс files на канву",
        page,
        screenshot_name="files-resource-dropped",
        label_en="Drop a files resource on the canvas",
        details=(
            "В палитре слева в разделе «Ресурсы» перетащите тип файлов на канву. "
            "Появится блок общих файлов ветки — каталог PDF можно переиспользовать "
            "в нескольких шагах. Ресурс контекста модели (llm context) настраивается "
            "в отдельной инструкции."
        ),
        details_en=(
            "In the left palette under Resources drag the files type onto the canvas. "
            "A shared branch files block appears — a PDF catalog can be reused across "
            "steps. The model context resource (llm context) is covered in a separate guide."
        ),
    )

    resource_node_id = await _ensure_resource_node()
    await flows_open_node_editor(page, resource_node_id)
    files_editor = page.locator("flows-files-resource-editor:visible").last
    await expect(files_editor).to_be_visible()
    storage_fields = files_editor.locator(".body platform-field:visible")
    bucket_field = storage_fields.first
    prefix_field = storage_fields.nth(1)
    await flows_set_platform_field(bucket_field, "green-garden-catalogs")
    await flows_set_platform_field(prefix_field, "spring-2026")
    textboxes = files_editor.get_by_role("textbox")
    await expect(textboxes.nth(0)).to_have_value("green-garden-catalogs")
    await expect(textboxes.nth(1)).to_have_value("spring-2026")
    await scenario.step(
        "Укажите хранилище каталога",
        page,
        screenshot_name="catalog-storage-configured",
        label_en="Configure the catalog storage",
        details=(
            "Откройте свойства ресурса и укажите bucket «green-garden-catalogs» "
            "и префикс «spring-2026». Эти поля направляют агент к нужной папке "
            "объектного хранилища, где лежит актуальный каталог."
        ),
        details_en=(
            "Open the resource properties and set the bucket to “green-garden-catalogs” "
            "and the prefix to “spring-2026”. These fields point the agent to the exact "
            "object-storage folder containing the current catalog."
        ),
    )

    resource_node_id = await _ensure_resource_node()
    await flows_open_node_editor(page, "agent")
    resources_heading = page.locator("flows-llm-node-editor").get_by_text(
        re.compile(r"ресурс|resource", re.I)
    ).first
    await expect(resources_heading).to_be_visible(timeout=15_000)
    await scenario.step(
        "Откройте агента и проверьте ресурсы",
        page,
        screenshot_name="agent-resources-section",
        label_en="Open the agent and review resources",
        details=(
            "Откройте главную ноду агента и найдите блок ресурсов. Здесь видно, какие "
            "общие файлы и настройки подключены к этой ветке графа."
        ),
        details_en=(
            "Open the main agent node and find the resources block. Here you see which "
            "shared files and settings are attached to this graph branch."
        ),
    )

    await flows_publish_editor(page)
    persisted = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    assert persisted.get("resources"), "flow resources must be persisted after publish"
    await scenario.step(
        "Опубликуйте агента с ресурсом",
        page,
        screenshot_name="resource-published",
        label_en="Publish the agent with the resource",
        details=(
            "**Демонстрация результата.** Блок файлов сохранён в ветке графа — "
            "его можно переиспользовать в нескольких нодах без повторной загрузки.\n\n"
            "**Итог.** Теперь вы умеете добавлять ресурс файлов на канву и подключать "
            "общие материалы к агенту."
        ),
        details_en=(
            "**Result demonstration.** The files block is saved on the graph branch — "
            "you can reuse it across nodes without re-uploading.\n\n"
            "**Summary.** You can add a files resource to the canvas and attach shared "
            "materials to the agent."
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
        has=page.locator("platform-icon[name='plus']")
    ).first
    await expect(add_btn).to_be_visible(timeout=15_000)
    await add_btn.evaluate("(el) => el.click()")
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
    greeting_row = modal.get_by_text("greeting", exact=False).first
    await expect(greeting_row).to_be_visible(timeout=15_000)
    await scenario.step(
        "Проверьте переменную в списке",
        page,
        screenshot_name="variable-greeting-listed",
        label_en="Verify the variable in the list",
        details=(
            "После сохранения переменная greeting появляется в таблице модального окна. "
            "Так вы убеждаетесь, что значение доступно всему графу до правки промпта."
        ),
        details_en=(
            "After saving, the greeting variable appears in the modal table. "
            "This confirms the value is available to the whole graph before editing the prompt."
        ),
    )

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


@pytest.mark.scenario(
    service="flows",
    tag="data",
    doc_slug="llm-context-resource",
    title="Подключаем ресурс контекста модели",
    description=(
        "**Для чего:** эта инструкция поможет задать общий ресурс контекста модели "
        "и привязать его к ноде ответа.\n\n"
        "**Какие проблемы решает:** лимиты окна и политики контекста копируют в каждую "
        "ноду — удобнее один ресурс на ветке.\n\n"
        "**Результат:** у агента выбран ресурс контекста «Зелёного сада»."
    ),
    title_en="Attach a model context resource",
    description_en=(
        "**What for:** this guide helps you define a shared model context resource and "
        "attach it to the answer node.\n\n"
        "**Problems it solves:** window limits and context policies get copied into every "
        "node — one branch resource is cleaner.\n\n"
        "**Result:** the agent uses the Green Garden context resource."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_flows_llm_context_resource(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    flow_id = flows_doc_flow_id("llm_ctx", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(
            flow_id,
            name=GREEN_GARDEN_AGENT_NAME,
            prompt="Отвечай с учётом политики контекста магазина.",
        ),
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, flow_id)
    await flows_e2e_ensure_canvas_layout(page)
    await scenario.step(
        "Откройте агента на схеме",
        page,
        screenshot_name="llm-context-editor-opened",
        label_en="Open the agent on the canvas",
        details=(
            "Откройте «Помощника Зелёного сада» на канве. Ресурс контекста модели "
            "живёт рядом с файлами и другими ресурсами ветки."
        ),
        details_en=(
            "Open the Green Garden Assistant on the canvas. The model context resource "
            "lives next to files and other branch resources."
        ),
    )

    await flows_drop_resource_type(page, "llm_context", x=640, y=400)
    resource_ids = await flows_canvas_node_ids_of_type(page, "resource")
    if not resource_ids:
        raise AssertionError("llm_context resource node missing after palette drop")
    await scenario.step(
        "Добавьте ресурс контекста на канву",
        page,
        screenshot_name="llm-context-resource-dropped",
        label_en="Drop a context resource on the canvas",
        details=(
            "В палитре ресурсов перетащите тип контекста модели. Появится блок, в котором "
            "задаются политики окна и профиля для нескольких нод."
        ),
        details_en=(
            "From the resources palette drag the model context type. A block appears for "
            "window and profile policies shared across nodes."
        ),
    )

    resource_node_id = resource_ids[0]
    await flows_open_node_editor(page, resource_node_id)
    name_field = page.locator("flows-base-resource-editor platform-field").first
    if await name_field.count() > 0:
        await flows_set_platform_field(name_field, "Контекст Зелёного сада")
    await expect(page.locator("platform-llm-context-editor").first).to_be_visible(
        timeout=30_000
    )
    await scenario.step(
        "Назовите ресурс и откройте редактор контекста",
        page,
        screenshot_name="llm-context-resource-named",
        label_en="Name the resource and open the context editor",
        details=(
            "Задайте имя вроде «Контекст Зелёного сада». Внутри виден редактор политик "
            "контекста — здесь настраивают окно диалога без правки каждой ноды."
        ),
        details_en=(
            "Set a name such as Green Garden context. Inside you see the context policy "
            "editor — configure the dialog window without editing every node."
        ),
    )

    resource_keys = await page.locator("flows-flow-canvas").evaluate(
        """
        (el) => {
            const data = el._branchData();
            return Object.keys(data.resources || {});
        }
        """
    )
    if not isinstance(resource_keys, list) or not resource_keys:
        raise AssertionError("branch resources empty after llm_context drop")
    context_key = str(resource_keys[0])

    await flows_open_node_editor(page, "agent")
    context_field = page.locator("flows-llm-node-editor platform-field").filter(
        has_text=re.compile(r"Ресурс контекста|Context resource", re.I)
    ).first
    await expect(context_field).to_be_visible(timeout=30_000)
    await context_field.evaluate(
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
        context_key,
    )
    await scenario.step(
        "Привяжите ресурс к ноде ответа",
        page,
        screenshot_name="llm-context-attached-to-node",
        label_en="Attach the resource to the answer node",
        details=(
            "Откройте ноду ответа и в блоке контекста выберите ресурс «Контекст "
            "Зелёного сада». Так нода явно использует общую политику."
        ),
        details_en=(
            "Open the answer node and in the context block pick Green Garden context. "
            "The node then uses the shared policy explicitly."
        ),
    )

    await flows_publish_editor(page)
    persisted = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    agent = persisted["nodes"]["agent"]
    assert agent.get("llm_context_resource_key") == context_key, agent
    await flows_open_node_editor(page, "agent")
    await expect(context_field).to_be_visible(timeout=15_000)
    await scenario.step(
        "Опубликуйте и проверьте привязку",
        page,
        screenshot_name="llm-context-published",
        label_en="Publish and verify the attachment",
        details=(
            "**Демонстрация результата.** После публикации у ноды выбран ресурс "
            "контекста — политика сохранена в агенте.\n\n"
            "**Итог.** Вы умеете добавлять ресурс контекста модели и подключать его к "
            "ноде ответа."
        ),
        details_en=(
            "**Result demonstration.** After publish the node still has the context "
            "resource selected — the policy is saved on the agent.\n\n"
            "**Summary.** You can add a model context resource and attach it to the "
            "answer node."
        ),
    )
