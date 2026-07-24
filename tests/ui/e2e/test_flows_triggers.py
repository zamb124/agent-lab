"""UI E2E сценарии Flows: триггеры расписания и Telegram."""

from __future__ import annotations

import os
import re

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
    flows_set_platform_field,
    flows_trigger_editor_click_mapping_example,
    flows_trigger_editor_configure_platform_event,
    flows_trigger_editor_configure_webhook,
    flows_trigger_editor_expect_ready_curl,
    flows_trigger_editor_expect_sample_panel,
    flows_trigger_editor_fill_identity,
    flows_trigger_editor_platform_event_change_type_clears_filters,
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
    trigger_row = page.locator("flows-triggers-modal").get_by_text(
        re.compile(r"Ежедневная|daily|сводк", re.I)
    ).first
    await expect(trigger_row).to_be_visible(timeout=30_000)
    await scenario.step(
        "Сохраните триггер в списке",
        page,
        screenshot_name="cron-trigger-saved",
        label_en="Save the trigger in the list",
        details=(
            "Нажмите «Сохранить» в редакторе триггера. Новая строка «Ежедневная сводка "
            "заказов» появится в списке автозапусков агента."
        ),
        details_en=(
            "Click Save in the trigger editor. The new Daily order summary row appears "
            "in the agent automatic runs list."
        ),
    )

    persisted = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    triggers = persisted.get("triggers") or {}
    assert trigger_id in triggers or len(triggers) >= 1
    await scenario.step(
        "Убедитесь, что расписание сохранено",
        page,
        screenshot_name="cron-trigger-published",
        label_en="Confirm the schedule is saved",
        details=(
            "**Демонстрация результата.** Триггер cron появился в списке и сохранён "
            "в агенте — ежедневная сводка будет запускаться автоматически.\n\n"
            "**Итог.** Теперь вы умеете открывать триггеры, задавать cron и сохранять "
            "расписание для «Помощника Зелёного сада»."
        ),
        details_en=(
            "**Result demonstration.** The cron trigger appears in the list and is saved "
            "on the agent — the daily summary will run automatically.\n\n"
            "**Summary.** You can open triggers, set a cron schedule, and save it "
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
    await scenario.step(
        "Откройте список триггеров",
        page,
        screenshot_name="telegram-triggers-modal-opened",
        label_en="Open the triggers list",
        details=(
            "В меню редактора выберите «Триггеры». Здесь настраиваются автозапуски "
            "агента — в том числе входящие сообщения Telegram-бота."
        ),
        details_en=(
            "In the editor menu choose Triggers. Here you configure automatic agent runs — "
            "including incoming Telegram bot messages."
        ),
    )

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
    await expect(page.locator("flows-triggers-modal")).to_contain_text(
        re.compile(r"Автоответ|Telegram", re.I),
        timeout=30_000,
    )
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
            "**Итог.** Теперь вы умеете настраивать Telegram-триггер и хранить токен "
            "в секрете."
        ),
        details_en=(
            "**Result demonstration.** The Telegram trigger is saved with a secret reference — "
            f"the agent is ready to reply in {GREEN_GARDEN_TELEGRAM_BOT}.\n\n"
            "**Summary.** You can configure a Telegram trigger and store the token as a "
            "secret."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="triggers",
    doc_slug="webhook-trigger",
    title="Запускаем агента по webhook",
    description=(
        "**Для чего:** эта инструкция настроит запуск агента по HTTP webhook от "
        "внешней системы магазина.\n\n"
        "**Какие проблемы решает:** нужно принимать события склада или CRM без "
        "Telegram и без ручного старта.\n\n"
        "**Результат:** webhook-триггер сохранён у «Помощника Зелёного сада»."
    ),
    title_en="Run the agent from a webhook",
    description_en=(
        "**What for:** this guide configures an agent run from an HTTP webhook from an "
        "external store system.\n\n"
        "**Problems it solves:** warehouse or CRM events must arrive without Telegram "
        "and without a manual start.\n\n"
        "**Result:** a webhook trigger is saved on the Green Garden Assistant."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_flows_webhook_trigger(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
    secrets_service,
    taskiq_worker,
) -> None:
    _ = secrets_service, taskiq_worker
    flow_id = flows_doc_flow_id("webhook_trig", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(
            flow_id,
            name=GREEN_GARDEN_AGENT_NAME,
            prompt="Обработай событие склада и кратко подтверди.",
        ),
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, flow_id)
    await flows_open_triggers_modal(page)
    await scenario.step(
        "Откройте список триггеров",
        page,
        screenshot_name="webhook-triggers-modal",
        label_en="Open the triggers list",
        details=(
            "В меню редактора выберите «Триггеры». Здесь же создают webhook — рядом с "
            "расписанием и Telegram."
        ),
        details_en=(
            "In the editor menu choose Triggers. Create a webhook here alongside "
            "schedule and Telegram."
        ),
    )

    await flows_triggers_click_create(page)
    await flows_trigger_editor_select_type(page, "webhook")
    await scenario.step(
        "Выберите тип Webhook",
        page,
        screenshot_name="webhook-type-selected",
        label_en="Choose the Webhook type",
        details=(
            "Нажмите создание и выберите Webhook. Платформа примет HTTP POST на "
            "endpoint агента."
        ),
        details_en=(
            "Click create and choose Webhook. The platform will accept an HTTP POST on "
            "the agent endpoint."
        ),
    )

    trigger_id = f"wh_{unique_id[:8]}"
    await flows_trigger_editor_fill_identity(
        page,
        trigger_id=trigger_id,
        name="События склада",
    )
    await scenario.step(
        "Задайте идентификатор и название",
        page,
        screenshot_name="webhook-identity-filled",
        label_en="Set id and name",
        details=(
            "Укажите короткий id и понятное имя вроде «События склада», чтобы найти "
            "триггер среди других автозапусков."
        ),
        details_en=(
            "Set a short id and a clear name such as Warehouse events so you can find "
            "the trigger among other autos."
        ),
    )

    secret_token = f"whsec_{unique_id[:8]}"
    await flows_trigger_editor_configure_webhook(
        page,
        secret_token=secret_token,
        secret_header="Authorization",
        allowed_ips=["127.0.0.1"],
    )
    await flows_trigger_editor_expect_ready_curl(page)
    await scenario.step(
        "Настройте секрет, заголовок и IP",
        page,
        screenshot_name="webhook-security-filled",
        label_en="Configure secret, header and IPs",
        details=(
            "Задайте секрет и заголовок, в котором внешняя система его передаст. "
            "Разрешённые IP — тегами, не строкой через запятую. Ниже — готовый curl."
        ),
        details_en=(
            "Set the secret and the header the external system will use. "
            "Allowed IPs are tags, not a comma-separated string. Ready curl is below."
        ),
    )

    await flows_trigger_editor_click_mapping_example(page, index=0)
    await flows_trigger_editor_expect_sample_panel(page)
    await scenario.step(
        "Добавьте маппинг одним кликом по примеру",
        page,
        screenshot_name="webhook-mapping-example",
        label_en="Add mapping by clicking an example",
        details=(
            "На вкладке Mapping нажмите пример — строка content → body.text появится сразу."
        ),
        details_en=(
            "On the Mapping tab click an example — a content → body.text row is added at once."
        ),
    )

    await flows_trigger_editor_save(page)
    trigger_row = page.locator("flows-triggers-modal").get_by_text(
        re.compile(r"События склада|webhook|Warehouse", re.I)
    ).first
    await expect(trigger_row).to_be_visible(timeout=30_000)
    persisted = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    triggers = persisted.get("triggers") or {}
    saved_trigger = triggers.get(trigger_id)
    assert isinstance(saved_trigger, dict), f"webhook trigger missing: {triggers!r}"
    assert saved_trigger.get("type") == "webhook"
    saved_config = saved_trigger.get("config") or {}
    assert saved_config.get("secret_header") == "Authorization"
    assert saved_config.get("allowed_ips") == ["127.0.0.1"]
    output_mapping = saved_trigger.get("output_mapping") or {}
    assert output_mapping.get("content") == "body.text"
    await scenario.step(
        "Сохраните и найдите webhook в списке",
        page,
        screenshot_name="webhook-saved-in-list",
        label_en="Save and find the webhook in the list",
        details=(
            "**Демонстрация результата.** Webhook «События склада» виден в списке "
            "триггеров — внешняя система может вызывать агента по HTTP.\n\n"
            "**Итог.** Вы умеете создавать webhook-триггер для внешних событий магазина."
        ),
        details_en=(
            "**Result demonstration.** The Warehouse events webhook appears in the "
            "triggers list — an external system can call the agent over HTTP.\n\n"
            "**Summary.** You can create a webhook trigger for external store events."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="triggers",
    doc_slug="platform-event-filters",
    title="Запускаем агента по событию платформы с фильтром",
    description=(
        "**Для чего:** агент реагирует только на нужные события шины "
        "(например создание CRM task).\n\n"
        "**Какие проблемы решает:** без фильтра flow сработает на каждое событие "
        "типа — фильтр по payload сужает подписку.\n\n"
        "**Результат:** триггер platform_event с условием entity_type=task сохранён."
    ),
    title_en="Run the agent on a platform event with a filter",
    description_en=(
        "**What for:** the agent reacts only to matching bus events "
        "(for example CRM task created).\n\n"
        "**Problems it solves:** without a filter the flow would fire on every event "
        "of that type — a payload filter narrows the subscription.\n\n"
        "**Result:** a platform_event trigger with entity_type=task is saved."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_flows_platform_event_filters(
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
    flow_id = flows_doc_flow_id("pe_trig", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(
            flow_id,
            name=GREEN_GARDEN_AGENT_NAME,
            prompt="Кратко подтверди событие CRM.",
        ),
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, flow_id)
    await flows_open_triggers_modal(page)
    await scenario.step(
        "Откройте список триггеров",
        page,
        screenshot_name="platform-event-triggers-modal",
        label_en="Open the triggers list",
        details="В меню редактора выберите «Триггеры» и создайте новый триггер.",
        details_en="In the editor menu choose Triggers and create a new trigger.",
    )

    await flows_triggers_click_create(page)
    await flows_trigger_editor_select_type(page, "platform_event")
    await scenario.step(
        "Выберите тип «Событие платформы»",
        page,
        screenshot_name="platform-event-type-selected",
        label_en="Choose Platform event type",
        details="Тип подписывает flow на шину platform:events.",
        details_en="This type subscribes the flow to the platform:events bus.",
    )

    trigger_id = f"pe_{unique_id[:8]}"
    await flows_trigger_editor_fill_identity(
        page,
        trigger_id=trigger_id,
        name="CRM task created",
    )
    await flows_trigger_editor_configure_platform_event(
        page,
        event_type="crm/entity/created",
        filters=[{"path": "entity_type", "op": "eq", "value": "task"}],
    )
    await scenario.step(
        "Выберите событие и условие entity_type = task",
        page,
        screenshot_name="platform-event-filters-filled",
        label_en="Pick event and entity_type = task filter",
        details=(
            "Тип события берётся из каталога. Условие path/op/value — только из "
            "filter_fields каталога (autocomplete)."
        ),
        details_en=(
            "Event type comes from the catalog. Path/op/value are only from catalog "
            "filter_fields (autocomplete)."
        ),
    )

    await flows_trigger_editor_platform_event_change_type_clears_filters(
        page,
        next_event_type="worktracker/work_item/comment_created",
    )
    await flows_trigger_editor_configure_platform_event(
        page,
        event_type="worktracker/work_item/comment_created",
        filters=[{"path": "comment.role", "op": "eq", "value": "operator"}],
    )
    await flows_trigger_editor_expect_sample_panel(page)
    await scenario.step(
        "Смените тип события — фильтры сбросятся; задайте comment.role = operator",
        page,
        screenshot_name="platform-event-enum-filter",
        label_en="Change event type clears filters; set comment.role = operator",
        details="Enum-значение роли берётся из catalog filter_fields.",
        details_en="The role enum value comes from catalog filter_fields.",
    )

    await flows_trigger_editor_save(page)
    trigger_row = page.locator("flows-triggers-modal").get_by_text(
        re.compile(r"CRM task created|platform_event|comment", re.I)
    ).first
    await expect(trigger_row).to_be_visible(timeout=30_000)

    persisted = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    triggers = persisted.get("triggers") or {}
    saved_trigger = triggers.get(trigger_id)
    assert isinstance(saved_trigger, dict), f"platform_event trigger missing: {triggers!r}"
    assert saved_trigger.get("type") == "platform_event"
    saved_config = saved_trigger.get("config") or {}
    assert saved_config.get("event_type") == "worktracker/work_item/comment_created"
    filters = saved_config.get("filters") or []
    assert isinstance(filters, list) and len(filters) == 1
    assert filters[0].get("path") == "comment.role"
    assert filters[0].get("op") == "eq"
    assert filters[0].get("value") == "operator"

    await scenario.step(
        "Сохраните и проверьте триггер в списке",
        page,
        screenshot_name="platform-event-saved-in-list",
        label_en="Save and verify the trigger in the list",
        details=(
            "**Демонстрация результата.** Триггер с фильтром comment.role=operator "
            "сохранён — агент среагирует только на комментарии оператора.\n\n"
            "**Итог.** Вы умеете подписывать flow на событие платформы с фильтром."
        ),
        details_en=(
            "**Result demonstration.** The trigger with comment.role=operator is "
            "saved — the agent reacts only to operator comments.\n\n"
            "**Summary.** You can subscribe a flow to a platform event with a filter."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="triggers",
    doc_slug="email-trigger-sample",
    title="Смотрим sample payload почтового триггера",
    description=(
        "**Для чего:** понять форму входящего письма для mapping.\n\n"
        "**Результат:** на вкладке Mapping виден sample JSON и how-to для /test."
    ),
    title_en="Inspect email trigger sample payload",
    description_en=(
        "**What for:** understand inbound mail shape for mapping.\n\n"
        "**Result:** Mapping tab shows sample JSON and how-to for /test."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_flows_email_trigger_sample_panel(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
    secrets_service,
    taskiq_worker,
) -> None:
    _ = secrets_service, taskiq_worker, auth_token_system
    flow_id = flows_doc_flow_id("email_trig", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(
            flow_id,
            name=GREEN_GARDEN_AGENT_NAME,
            prompt="Кратко опиши входящее письмо.",
        ),
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, flow_id)
    await flows_open_triggers_modal(page)
    await flows_triggers_click_create(page)
    await flows_trigger_editor_select_type(page, "email")
    await scenario.step(
        "Выберите тип «Почта»",
        page,
        screenshot_name="email-type-selected",
        label_en="Choose Email type",
        details="Тип подписывает flow на входящие письма platform mail.",
        details_en="This type subscribes the flow to inbound platform mail.",
    )
    await flows_trigger_editor_expect_sample_panel(page)
    await scenario.step(
        "Откройте Mapping и посмотрите sample payload",
        page,
        screenshot_name="email-sample-panel",
        label_en="Open Mapping and inspect the sample payload",
        details=(
            "**Демонстрация результата.** Виден пример JSON письма и подсказка, "
            "как проверить mapping через /test после сохранения.\n\n"
            "**Итог.** Вы знаете форму payload почтового триггера."
        ),
        details_en=(
            "**Result demonstration.** The sample mail JSON and /test how-to are "
            "visible on Mapping.\n\n"
            "**Summary.** You know the email trigger payload shape."
        ),
    )
