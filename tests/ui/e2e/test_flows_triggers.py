"""UI E2E сценарии Flows: триггеры расписания и Telegram."""

from __future__ import annotations

import os

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.flows_api_e2e_helpers import flows_seed_company_secret_var
from tests.ui.e2e.flows_e2e_helpers import (
    GREEN_GARDEN_AGENT_NAME,
    GREEN_GARDEN_TELEGRAM_BOT,
    flows_api_create_flow,
    flows_api_get_flow,
    flows_doc_flow_id,
    flows_llm_payload,
    flows_open_editor,
    flows_open_triggers_modal,
    flows_publish_editor,
    flows_set_platform_field,
    flows_trigger_editor_fill_identity,
    flows_trigger_editor_save,
    flows_trigger_editor_select_type,
    flows_triggers_click_create,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")


@pytest.mark.scenario(
    service="flows",
    tag="triggers",
    doc_slug="schedule-daily-run",
    title="Запускаем агента по расписанию",
    description=(
        "**Для чего:** эта инструкция настроит ежедневный запуск агента без ручного старта.\n\n"
        "**Какие проблемы решает:** сводку заказов нужно готовить каждое утро — "
        "cron-триггер делает это автоматически.\n\n"
        "**Результат:** триггер расписания с выражением cron сохранён в агенте."
    ),
    title_en="Run the agent on a schedule",
    description_en=(
        "**What for:** this guide configures a daily agent run without manual starts.\n\n"
        "**Problems it solves:** an order summary is needed every morning — "
        "a cron trigger automates it.\n\n"
        "**Result:** a schedule trigger with a cron expression is saved on the agent."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_flows_schedule_daily_run(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
    secrets_service,
    taskiq_worker,
) -> None:
    _ = secrets_service, taskiq_worker
    flow_id = flows_doc_flow_id("cron_trig", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(
            flow_id,
            name=GREEN_GARDEN_AGENT_NAME,
            prompt="Сформируй краткую сводку заказов за сутки.",
        ),
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, flow_id)
    await flows_open_triggers_modal(page)
    await scenario.step(
        "Откройте список триггеров",
        page,
        screenshot_name="triggers-modal-opened",
        label_en="Open the triggers list",
        details=(
            "В меню редактора выберите «Триггеры». Здесь видны все автозапуски агента — "
            "по расписанию, из Telegram или по webhook."
        ),
        details_en=(
            "In the editor menu choose Triggers. Here you see all automatic agent runs — "
            "on a schedule, from Telegram, or via webhook."
        ),
    )

    await flows_triggers_click_create(page)
    await flows_trigger_editor_select_type(page, "cron")
    trigger_id = f"daily_{unique_id[:8]}"
    await flows_trigger_editor_fill_identity(
        page,
        trigger_id=trigger_id,
        name="Ежедневная сводка заказов",
    )
    cron_field = page.locator("flows-trigger-editor-modal platform-cron-field").first
    await expect(cron_field).to_be_visible(timeout=15_000)
    await cron_field.evaluate(
        """
        (el) => {
            el.value = '0 9 * * *';
            if (typeof el.requestUpdate === 'function') el.requestUpdate();
            el.dispatchEvent(new CustomEvent('change', {
                detail: { value: '0 9 * * *' },
                bubbles: true,
                composed: true,
            }));
        }
        """
    )
    await scenario.step(
        "Создайте cron-триггер",
        page,
        screenshot_name="cron-trigger-configured",
        label_en="Create a cron trigger",
        details=(
            "Нажмите «+», выберите тип Cron и задайте расписание «0 9 * * *» — "
            "агент будет запускаться каждый день в 9:00."
        ),
        details_en=(
            "Click +, pick Cron, and set the schedule to 0 9 * * * — "
            "the agent runs every day at 9:00."
        ),
    )

    await flows_trigger_editor_save(page)
    await flows_publish_editor(page)
    persisted = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    triggers = persisted.get("triggers") or {}
    assert trigger_id in triggers or len(triggers) >= 1
    await scenario.step(
        "Сохраните и опубликуйте расписание",
        page,
        screenshot_name="cron-trigger-published",
        label_en="Save and publish the schedule",
        details=(
            "**Демонстрация результата.** Триггер cron появился в списке и сохранён "
            "в агенте — ежедневная сводка будет запускаться автоматически.\n\n"
            "**Итог.** Теперь вы умеете открывать триггеры, задавать cron и публиковать "
            "расписание для «Помощника Зелёного сада»."
        ),
        details_en=(
            "**Result demonstration.** The cron trigger appears in the list and is saved "
            "on the agent — the daily summary will run automatically.\n\n"
            "**Summary.** You can open triggers, set a cron schedule, and publish it "
            "for the Green Garden Assistant."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="triggers",
    doc_slug="telegram-auto-reply",
    title="Автоответы в Telegram",
    description=(
        "**Для чего:** эта инструкция подключит входящие сообщения Telegram-бота к агенту.\n\n"
        "**Какие проблемы решает:** покупатели пишут в «@zeleniy_sad_bot», "
        "а ответ должен формировать агент автоматически.\n\n"
        "**Результат:** триггер Telegram с токеном через переменную-секрет настроен."
    ),
    title_en="Auto-reply in Telegram",
    description_en=(
        "**What for:** this guide connects incoming Telegram bot messages to the agent.\n\n"
        "**Problems it solves:** customers message @zeleniy_sad_bot and the agent "
        "must reply automatically.\n\n"
        "**Result:** a Telegram trigger with bot token via a secret variable is configured."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_flows_telegram_auto_reply(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    auth_headers_system: dict[str, str],
    unique_id: str,
    secrets_service,
    taskiq_worker,
) -> None:
    _ = secrets_service, taskiq_worker
    secret_key = f"tg_bot_{unique_id[:12]}"
    await flows_seed_company_secret_var(
        auth_headers_system,
        secret_key,
        "demo-bot-token-for-ui",
        secret=True,
    )

    flow_id = flows_doc_flow_id("tg_trig", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(
            flow_id,
            name=GREEN_GARDEN_AGENT_NAME,
            prompt=f"Отвечай покупателям бота {GREEN_GARDEN_TELEGRAM_BOT}.",
        ),
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, flow_id)
    await flows_open_triggers_modal(page)
    await flows_triggers_click_create(page)
    await flows_trigger_editor_select_type(page, "telegram")
    trigger_id = f"telegram_{unique_id[:8]}"
    await flows_trigger_editor_fill_identity(
        page,
        trigger_id=trigger_id,
        name="Автоответ в Telegram",
    )
    await scenario.step(
        "Создайте триггер Telegram",
        page,
        screenshot_name="telegram-trigger-editor",
        label_en="Create a Telegram trigger",
        details=(
            "В списке триггеров нажмите «+» и выберите Telegram. Укажите id и название — "
            "так бот магазина будет принимать сообщения покупателей."
        ),
        details_en=(
            "In the triggers list click + and choose Telegram. Set id and name — "
            "the store bot will then accept customer messages."
        ),
    )

    editor = page.locator("flows-trigger-editor-modal").first
    token_input = editor.locator("platform-variable-input, platform-field").first
    await expect(token_input).to_be_visible(timeout=15_000)
    token_value = f"@var:{secret_key}"
    if await editor.locator("platform-variable-input").count() > 0:
        await editor.locator("platform-variable-input").first.evaluate(
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
            token_value,
        )
    else:
        await flows_set_platform_field(token_input, token_value)
    verify_btn = editor.locator(
        'platform-button[aria-label*="Проверить"], platform-button[aria-label*="Verify"]'
    ).first
    await expect(verify_btn).to_be_visible(timeout=15_000)
    await scenario.step(
        "Укажите токен бота через секрет",
        page,
        screenshot_name="telegram-token-var-set",
        label_en="Set the bot token via a secret",
        details=(
            f"В поле токена укажите @var:{secret_key} — значение возьмётся из защищённых "
            "переменных компании. Рядом доступны кнопки проверки и перерегистрации webhook."
        ),
        details_en=(
            f"In the token field set @var:{secret_key} — the value comes from protected "
            "company variables. Verify and re-register webhook buttons are nearby."
        ),
    )

    await flows_trigger_editor_save(page)
    await flows_publish_editor(page)
    persisted = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    triggers = persisted.get("triggers") or {}
    assert len(triggers) >= 1
    await scenario.step(
        "Сохраните автоответ Telegram",
        page,
        screenshot_name="telegram-trigger-published",
        label_en="Save the Telegram auto-reply",
        details=(
            "**Демонстрация результата.** Триггер Telegram сохранён с ссылкой на секрет — "
            f"агент готов отвечать в {GREEN_GARDEN_TELEGRAM_BOT}.\n\n"
            "**Итог.** Теперь вы умеете настраивать Telegram-триггер, хранить токен "
            "в секрете и публиковать автоответ."
        ),
        details_en=(
            "**Result demonstration.** The Telegram trigger is saved with a secret reference — "
            f"the agent is ready to reply in {GREEN_GARDEN_TELEGRAM_BOT}.\n\n"
            "**Summary.** You can configure a Telegram trigger, store the token as a secret, "
            "and publish auto-reply."
        ),
    )
