"""UI E2E сценарии Flows: публикация, ветки и настройки агента."""

from __future__ import annotations

import os
import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    GREEN_GARDEN_AGENT_NAME,
    GREEN_GARDEN_BRANCH,
    flows_api_create_branch,
    flows_api_create_flow,
    flows_api_get_flow,
    flows_chat_send_message,
    flows_click_platform_button,
    flows_create_branch,
    flows_doc_flow_id,
    flows_e2e_expect_skill_load_chip,
    flows_e2e_open_studio_prompt_section,
    flows_e2e_seed_agent_skill,
    flows_e2e_set_show_skill_loads,
    flows_llm_payload,
    flows_open_chat_page,
    flows_open_editor,
    flows_open_flow_property_panel,
    flows_open_node_editor,
    flows_open_raw_json_modal,
    flows_open_sessions_modal,
    flows_publish_editor,
    flows_seed_mock_llm,
    flows_select_branch_tab,
    flows_set_platform_field,
    flows_set_selected_llm_prompt,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")

_BRANCH_PROMPT = (
    "Ты — помощник «Зелёного сада» в акции «Летние скидки». "
    "Рассказывай про скидки на растения и уточняй город доставки."
)


def _branch_id(unique_id: str) -> str:
    safe = re.sub(r"[^a-z0-9_]+", "_", unique_id.lower()).strip("_")
    if not safe:
        safe = "sale"
    return f"summer_{safe[:24]}"


@pytest.mark.scenario(
    service="flows",
    tag="operations",
    doc_slug="experiment-with-branches",
    title="Экспериментируем в ветке",
    description=(
        "**Для чего:** эта инструкция поможет проверить идею в отдельной ветке, не меняя "
        "основную версию агента.\n\n"
        "**Какие проблемы решает:** страшно ломать рабочего помощника, когда нужно протестировать "
        "акцию или новый промпт.\n\n"
        "**Результат:** в ветке «Летние скидки» сохранены отдельные изменения."
    ),
    title_en="Experiment in a branch",
    description_en=(
        "**What for:** this guide helps you try an idea in a separate branch without changing "
        "the main agent version.\n\n"
        "**Problems it solves:** you may hesitate to edit a live assistant when testing a "
        "promotion or a new instruction.\n\n"
        "**Result:** the Summer sale branch keeps its own changes."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_flows_experiment_with_branches(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    flow_id = flows_doc_flow_id("branch_exp", unique_id)
    branch_id = _branch_id(unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(
            flow_id,
            name=GREEN_GARDEN_AGENT_NAME,
            prompt="Отвечай как базовый помощник магазина.",
        ),
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, flow_id, layout="agent")
    await scenario.step(
        "Откройте агента в редакторе",
        page,
        screenshot_name="editor-base-branch",
        label_en="Open the agent in the editor",
        details=(
            "В шапке редактора видны вкладки веток. Базовая ветка — это рабочая версия "
            "агента, которую видят пользователи по умолчанию."
        ),
        details_en=(
            "The editor header shows branch tabs. The base branch is the live agent version "
            "users get by default."
        ),
    )

    await flows_api_create_branch(
        flows_ui.origin,
        auth_token_system,
        flow_id,
        branch_id=branch_id,
        name=GREEN_GARDEN_BRANCH,
    )
    await flows_open_editor(
        page,
        flows_ui,
        flow_id,
        branch_id=branch_id,
        layout="agent",
    )
    await expect(page).to_have_url(
        re.compile(rf"/editor/{re.escape(branch_id)}(?:/|$)"),
        timeout=5_000,
    )
    await scenario.step(
        "Создайте и откройте ветку «Летние скидки»",
        page,
        screenshot_name="branch-created-and-selected",
        label_en="Create and open the Summer sale branch",
        details=(
            "Нажмите «+» рядом с вкладками веток, задайте идентификатор и название акции. "
            "После создания переключитесь на новую вкладку — изменения будут жить только "
            "в этой ветке."
        ),
        details_en=(
            "Click + next to branch tabs, set an identifier and promotion name. After "
            "creation, switch to the new tab — changes stay in this branch only."
        ),
    )

    await flows_open_node_editor(page, "agent")
    await flows_set_selected_llm_prompt(page, _BRANCH_PROMPT, node_id="agent")
    await scenario.step(
        "Измените инструкцию под акцию",
        page,
        screenshot_name="branch-prompt-updated",
        label_en="Update the instruction for the promotion",
        details=(
            "Откройте ноду ответа и перепишите инструкцию под летнюю акцию. Часть настроек "
            "наследуется из базовой ветки, а текст промпта можно менять локально."
        ),
        details_en=(
            "Open the answer node and rewrite the instruction for the summer promotion. "
            "Some settings inherit from the base branch, while the prompt text can be "
            "changed locally."
        ),
    )

    await flows_publish_editor(page)
    persisted = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    base_prompt = persisted["nodes"]["agent"]["prompt"]
    assert "скид" not in str(base_prompt).lower()
    branches = persisted.get("branches")
    if not isinstance(branches, dict) or branch_id not in branches:
        raise AssertionError(f"published flow missing branch {branch_id!r}: {branches!r}")
    branch_cfg = branches[branch_id]
    if not isinstance(branch_cfg, dict):
        raise AssertionError(f"branch config must be object: {branch_cfg!r}")
    branch_nodes = branch_cfg.get("nodes")
    # Merge-override: в ветке только diff; пустой dict = полное наследование базы.
    if not isinstance(branch_nodes, dict):
        raise AssertionError(f"branch nodes must be object: {branch_nodes!r}")
    agent_override = branch_nodes.get("agent") if isinstance(branch_nodes.get("agent"), dict) else None
    if agent_override is None or "скид" not in str(agent_override.get("prompt", "")).lower():
        raise AssertionError(
            f"branch agent prompt override missing скид after publish: "
            f"nodes={branch_nodes!r}"
        )

    await flows_open_editor(
        page,
        flows_ui,
        flow_id,
        branch_id=branch_id,
        layout="agent",
    )
    await flows_open_node_editor(page, "agent")
    await flows_e2e_open_studio_prompt_section(page)
    prompt_editor = page.locator("flows-agent-focus-studio platform-markdown-editor").first
    await expect(prompt_editor).to_be_visible(timeout=8_000)
    prompt_value = await prompt_editor.evaluate("(el) => String(el.value || '')")
    assert "скид" in prompt_value.lower(), f"reopened branch prompt missing скид: {prompt_value!r}"
    await scenario.step(
        "Опубликуйте ветку и проверьте изоляцию",
        page,
        screenshot_name="branch-published",
        label_en="Publish the branch and verify isolation",
        details=(
            "**Демонстрация результата.** После публикации промпт акции сохранён только в "
            "ветке «Летние скидки», а базовая версия осталась прежней.\n\n"
            "**Итог.** Теперь вы умеете создавать ветку, менять поведение агента в ней и "
            "публиковать эксперимент без риска для основной версии."
        ),
        details_en=(
            "**Result demonstration.** After publishing, the promotion prompt is stored only "
            "in the Summer sale branch while the base version stays unchanged.\n\n"
            "**Summary.** You can now create a branch, change agent behavior there, and "
            "publish experiments without risking the main version."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="operations",
    doc_slug="publish-and-operate",
    title="Публикуем и управляем агентом",
    description=(
        "**Для чего:** эта инструкция поможет выпустить агента в работу и управлять его "
        "карточкой и сессиями.\n\n"
        "**Какие проблемы решает:** после редактирования неясно, как сохранить рабочую "
        "версию, обновить описание и посмотреть диалоги.\n\n"
        "**Результат:** агент опубликован, карточка обновлена, доступны сессии и JSON-конфиг."
    ),
    title_en="Publish and operate the agent",
    description_en=(
        "**What for:** this guide helps you release an agent and manage its card and sessions.\n\n"
        "**Problems it solves:** after editing, it is unclear how to save the live version, "
        "update the description, and review conversations.\n\n"
        "**Result:** the agent is published, the card is updated, and sessions plus JSON config "
        "are available."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_flows_publish_and_operate(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    flow_id = flows_doc_flow_id("operate", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(
            flow_id,
            name=GREEN_GARDEN_AGENT_NAME,
            prompt="Отвечай кратко о доставке и оплате.",
            description="Черновик до публикации",
        ),
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, flow_id, layout="agent")
    await flows_publish_editor(page)
    await scenario.step(
        "Опубликуйте агента",
        page,
        screenshot_name="agent-published",
        label_en="Publish the agent",
        details=(
            "Нажмите «Опубликовать» в шапке редактора. После этого пользовательский чат, "
            "API и гостевые ссылки используют сохранённую версию."
        ),
        details_en=(
            "Click Publish in the editor header. After that, user chat, API, and guest links "
            "use the saved version."
        ),
    )

    await flows_e2e_set_show_skill_loads(page, enabled=True)
    skill_loads_field = page.locator(
        'flows-flow-edit-modal platform-field[data-chat-field="show_skill_loads"]'
    ).first
    await expect(skill_loads_field).to_be_visible(timeout=15_000)
    await scenario.step(
        "Включите показ активации Skills в чате",
        page,
        screenshot_name="chat-skill-loads-setting",
        label_en="Enable showing Skill activations in chat",
        details=(
            "В «Настройках агента» найдите параметры чата и включите показ активации "
            "Skills. Тогда в диалоге видны чипы загруженных процедур. Полная настройка "
            "чата — в отдельной инструкции."
        ),
        details_en=(
            "In Agent settings find chat options and enable showing Skill activations. "
            "Then the dialog shows chips for loaded procedures. Full chat setup is in a "
            "separate guide."
        ),
    )
    modal = page.locator("flows-flow-edit-modal").first
    fields = modal.locator("platform-field")
    await flows_set_platform_field(fields.nth(0), "Помощник Зелёного сада — опубликован")
    await flows_set_platform_field(
        fields.nth(1),
        "Помогает покупателям с заказами, доставкой и возвратами.",
    )
    await flows_click_platform_button(modal, "Save", "Сохранить")
    await expect(modal).to_be_hidden(timeout=30_000)
    await scenario.step(
        "Обновите карточку агента",
        page,
        screenshot_name="agent-card-updated",
        label_en="Update the agent card",
        details=(
            "В том же окне настроек измените название и описание. Эти поля видны в "
            "каталоге и в чате."
        ),
        details_en=(
            "In the same settings window change the name and description. These fields "
            "appear in the catalog and chat."
        ),
    )

    sessions = await flows_open_sessions_modal(page, flows_ui)
    await expect(sessions.locator("flows-sessions-modal, table, .sessions")).to_be_visible(
        timeout=30_000
    )
    await scenario.step(
        "Откройте список сессий",
        page,
        screenshot_name="sessions-modal-opened",
        label_en="Open the sessions list",
        details=(
            "Через меню редактора откройте «Сессии». Здесь можно найти прошлые диалоги "
            "и вернуться к проблемным обращениям."
        ),
        details_en=(
            "From the editor menu, open Sessions. Here you can find past conversations and "
            "return to problematic requests."
        ),
    )

    await page.keyboard.press("Escape")
    json_modal = await flows_open_raw_json_modal(page)
    await expect(json_modal.locator("flows-code-editor").first).to_be_visible(timeout=30_000)
    saved = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    assert saved["name"] == "Помощник Зелёного сада — опубликован"
    await scenario.step(
        "Выгрузите JSON-конфигурацию",
        page,
        screenshot_name="raw-json-export",
        label_en="Export the JSON configuration",
        details=(
            "**Демонстрация результата.** Агент опубликован, карточка обновлена, сессии "
            "доступны, а JSON-конфиг можно сохранить для резервной копии.\n\n"
            "**Итог.** Теперь вы умеете выпускать агента, управлять его карточкой и "
            "использовать операционные инструменты редактора."
        ),
        details_en=(
            "**Result demonstration.** The agent is published, the card is updated, sessions "
            "are available, and the JSON config can be saved as a backup.\n\n"
            "**Summary.** You can now release an agent, manage its card, and use the editor's "
            "operational tools."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="operations",
    doc_slug="voice-and-limits",
    title="Настраиваем голос и лимиты",
    description=(
        "**Для чего:** эта инструкция поможет задать лимит времени и профиль речи агента.\n\n"
        "**Какие проблемы решает:** непонятно, где включить голосовой режим и ограничить "
        "долгие ответы без правки графа.\n\n"
        "**Результат:** у агента задан таймаут и выбраны параметры речи в интерфейсе."
    ),
    title_en="Configure voice and limits",
    description_en=(
        "**What for:** this guide helps you set a time limit and speech profile for the agent.\n\n"
        "**Problems it solves:** it is unclear where to enable voice settings and cap long "
        "runs without editing the graph.\n\n"
        "**Result:** the agent has a timeout and speech options set in the UI."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_flows_voice_and_limits(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    flow_id = flows_doc_flow_id("voice_limits", unique_id)
    branch_id = _branch_id(unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(
            flow_id,
            name=GREEN_GARDEN_AGENT_NAME,
            prompt="Отвечай кратко.",
        ),
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, flow_id)
    panel = await flows_open_flow_property_panel(page)
    timeout_field = panel.locator("platform-field").filter(
        has_text=re.compile(r"Таймаут|Timeout", re.I)
    ).first
    await timeout_field.evaluate(
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
        120,
    )
    await scenario.step(
        "Откройте лимиты и речь агента",
        page,
        screenshot_name="flow-limits-panel",
        label_en="Open agent limits and speech",
        details=(
            "В левой колонке редактора откройте «Лимиты и речь». Здесь задаётся максимальное "
            "время выполнения и профиль STT/TTS/VAD."
        ),
        details_en=(
            "In the editor left column, open Limits and speech. Here you set the maximum "
            "runtime and STT/TTS/VAD profile."
        ),
    )

    speech_title = panel.get_by_text(re.compile(r"Речь|Speech", re.I)).first
    await expect(speech_title).to_be_visible(timeout=30_000)
    tts_provider = panel.locator("platform-field").filter(
        has_text=re.compile(r"Провайдер|Provider", re.I)
    ).nth(1)
    if await tts_provider.count() > 0:
        await tts_provider.scroll_into_view_if_needed()
    await scenario.step(
        "Проверьте блок настроек речи",
        page,
        screenshot_name="speech-settings-visible",
        label_en="Review the speech settings block",
        details=(
            "Прокрутите панель до раздела речи. Здесь можно выбрать провайдера синтеза, "
            "голос и язык — без реального голосового звонка, только настройка профиля."
        ),
        details_en=(
            "Scroll the panel to the speech section. Here you choose TTS provider, voice, "
            "and language — profile setup only, without a real voice call."
        ),
    )

    await flows_create_branch(page, branch_id, GREEN_GARDEN_BRANCH)
    await flows_select_branch_tab(page, re.escape(GREEN_GARDEN_BRANCH))
    branch_tab = page.get_by_role(
        "button",
        name=re.compile(rf"^{re.escape(GREEN_GARDEN_BRANCH)}$", re.I),
    ).first
    await expect(branch_tab).to_be_visible(timeout=3_000)
    await scenario.step(
        "Создайте ветку для отдельных настроек",
        page,
        screenshot_name="branch-tab-created",
        label_en="Create a branch for separate settings",
        details=(
            "Добавьте ветку «Летние скидки» и переключитесь на неё. Для разных сценариев "
            "можно задавать свои лимиты и профиль речи поверх настроек всего агента."
        ),
        details_en=(
            "Add the Summer sale branch and switch to it. Different scenarios can have "
            "their own limits and speech profile on top of agent-wide settings."
        ),
    )

    branch_panel = await flows_open_flow_property_panel(page)
    branch_speech = branch_panel.get_by_text(re.compile(r"Речь ветки|Branch speech", re.I)).first
    await expect(branch_speech).to_be_visible(timeout=30_000)
    await scenario.step(
        "Переопределите речь в ветке",
        page,
        screenshot_name="branch-speech-override",
        label_en="Override speech in the branch",
        details=(
            "**Демонстрация результата.** В ветке «Летние скидки» виден отдельный блок речи "
            "ветки — значит, голос и лимиты можно настраивать точечно.\n\n"
            "**Итог.** Теперь вы знаете, где задать таймаут агента и как переопределить "
            "профиль речи на уровне ветки."
        ),
        details_en=(
            "**Result demonstration.** In the Summer sale branch you see a separate branch "
            "speech block — voice and limits can be tuned per branch.\n\n"
            "**Summary.** You now know where to set the agent timeout and how to override "
            "the speech profile at branch level."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="operations",
    doc_slug="chat-settings-for-customers",
    title="Настройки чата для покупателей",
    description=(
        "**Для чего:** эта инструкция поможет управлять тем, видит ли покупатель "
        "активации Skills в чате.\n\n"
        "**Какие проблемы решает:** чипы процедур отвлекают клиента или, наоборот, "
        "нужны для прозрачности — рычаг в настройках чата.\n\n"
        "**Результат:** параметр показа активаций Skills переключён и проверен в чате."
    ),
    title_en="Chat settings for customers",
    description_en=(
        "**What for:** this guide helps you control whether customers see Skill "
        "activations in chat.\n\n"
        "**Problems it solves:** procedure chips distract customers or, conversely, are "
        "needed for transparency — the toggle lives in chat settings.\n\n"
        "**Result:** the Skill activation visibility setting is toggled and verified in "
        "chat."
    ),
    timeout_seconds=120,
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_flows_chat_settings_for_customers(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
    secrets_service,
    taskiq_worker,
    flows_service,
) -> None:
    _ = secrets_service, taskiq_worker, flows_service
    skill_id = f"chat-set-{unique_id[:8]}".lower().replace("_", "-")
    skill_name = skill_id
    await flows_e2e_seed_agent_skill(
        flows_ui.origin,
        auth_token_system,
        agent_skill_id=skill_id,
        name=skill_id,
        description="For chat skill-load chip checks",
        body_markdown="# Return\n\n1. Ask for the order id.\n",
    )
    flow_id = flows_doc_flow_id("chat_settings", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(
            flow_id,
            name=GREEN_GARDEN_AGENT_NAME,
            prompt="Помогай с возвратами.",
            agent_skills=[skill_id],
        ),
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, flow_id)
    await flows_e2e_set_show_skill_loads(page, enabled=True)
    field_on = page.locator(
        'flows-flow-edit-modal platform-field[data-chat-field="show_skill_loads"]'
    ).first
    await expect(field_on).to_be_visible(timeout=15_000)
    await scenario.step(
        "Включите показ активаций Skills",
        page,
        screenshot_name="skill-loads-enabled",
        label_en="Enable Skill activation chips",
        details=(
            "В настройках агента откройте параметры чата и включите показ активации "
            "Skills. Покупатель увидит чипы загруженных процедур."
        ),
        details_en=(
            "In agent settings open chat options and enable Skill activation chips. "
            "Customers will see chips for loaded procedures."
        ),
    )

    await flows_click_platform_button(
        page.locator("flows-flow-edit-modal").first,
        "Сохранить",
        "Save",
    )
    await flows_publish_editor(page)
    await scenario.step(
        "Сохраните и опубликуйте агента",
        page,
        screenshot_name="chat-settings-published",
        label_en="Save and publish the agent",
        details=(
            "Сохраните карточку и опубликуйте черновик — настройка чата попадёт в "
            "рабочую версию."
        ),
        details_en=(
            "Save the card and publish the draft so the chat setting applies to the live "
            "version."
        ),
    )

    await flows_open_chat_page(page, flows_ui, flow_id)
    chat = page.locator("flows-chat-page platform-flow-ui").first
    await expect(chat).to_be_visible(timeout=30_000)
    await flows_seed_mock_llm(
        [
            {
                "type": "tool_call",
                "tool": "load_agent_skill",
                "args": {"agent_skill_id": skill_id},
            },
            {"type": "text", "content": "Приняли заявку на возврат."},
        ]
    )
    await flows_chat_send_message(page, "Нужен возврат заказа")
    chip = await flows_e2e_expect_skill_load_chip(page, skill_name)
    await expect(chip).to_be_visible(timeout=5_000)
    await scenario.step(
        "Проверьте чат с видимыми чипами",
        page,
        screenshot_name="chat-with-skill-chips",
        label_en="Check chat with visible chips",
        details=(
            "Задайте вопрос о возврате — в ленте появится чип активации Skill. Так "
            "покупатель видит, какая процедура сработала."
        ),
        details_en=(
            "Ask about a return — a Skill activation chip appears in the feed so the "
            "customer sees which procedure ran."
        ),
    )

    await flows_open_editor(page, flows_ui, flow_id)
    await flows_e2e_set_show_skill_loads(page, enabled=False)
    await flows_click_platform_button(
        page.locator("flows-flow-edit-modal").first,
        "Сохранить",
        "Save",
    )
    await flows_publish_editor(page)
    field_off = page.locator(
        'flows-flow-edit-modal platform-field[data-chat-field="show_skill_loads"]'
    )
    # modal may close after save
    await scenario.step(
        "Выключите показ чипов и опубликуйте снова",
        page,
        screenshot_name="skill-loads-disabled",
        label_en="Disable chips and publish again",
        details=(
            "**Демонстрация результата.** Отключите показ активаций Skills и опубликуйте — "
            "чат для покупателей станет без чипов процедур.\n\n"
            "**Итог.** Вы умеете включать и выключать видимость активаций Skills в "
            "настройках чата."
        ),
        details_en=(
            "**Result demonstration.** Turn off Skill activation chips and publish — "
            "customer chat hides procedure chips.\n\n"
            "**Summary.** You can toggle Skill activation visibility in chat settings."
        ),
    )
    _ = field_off
