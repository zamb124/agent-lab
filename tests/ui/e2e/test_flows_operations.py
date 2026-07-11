"""UI E2E сценарии Flows: публикация, ветки и настройки агента."""

from __future__ import annotations

import os
import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_e2e_helpers import (
    GREEN_GARDEN_AGENT_NAME,
    GREEN_GARDEN_BRANCH,
    flows_api_create_flow,
    flows_api_get_flow,
    flows_click_platform_button,
    flows_create_branch,
    flows_doc_flow_id,
    flows_llm_payload,
    flows_open_editor,
    flows_open_flow_edit_modal,
    flows_open_flow_property_panel,
    flows_open_node_editor,
    flows_open_raw_json_modal,
    flows_open_sessions_modal,
    flows_publish_editor,
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
@pytest.mark.timeout(180)
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
    await flows_open_editor(page, flows_ui, flow_id)
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

    await flows_create_branch(page, branch_id, GREEN_GARDEN_BRANCH)
    await flows_select_branch_tab(page, re.escape(GREEN_GARDEN_BRANCH))
    await expect(page).to_have_url(re.compile(rf"/branch/{re.escape(branch_id)}"), timeout=30_000)
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
    await flows_set_selected_llm_prompt(page, _BRANCH_PROMPT)
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
    await flows_open_editor(page, flows_ui, flow_id, branch_id=branch_id)
    branch_editor = await flows_open_node_editor(page, "agent")
    await expect(branch_editor).to_contain_text("скид", timeout=15_000)
    base_flow = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    base_prompt = base_flow["nodes"]["agent"]["prompt"]
    assert "скид" not in base_prompt.lower()
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
    await flows_open_editor(page, flows_ui, flow_id)
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

    modal = await flows_open_flow_edit_modal(page)
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
            "В меню редактора откройте «Настройки агента» и измените название с описанием. "
            "Эти поля видны в каталоге и в чате."
        ),
        details_en=(
            "In the editor menu, open Agent settings and change the name and description. "
            "These fields appear in the catalog and chat."
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
