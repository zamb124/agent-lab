"""UI E2E инструкции Flows: триггеры (обзор + все типы, поля простым языком)."""

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
    flows_click_platform_button,
    flows_doc_flow_id,
    flows_llm_payload,
    flows_open_editor,
    flows_open_triggers_modal,
    flows_seed_ui_mail_mailbox,
    flows_set_platform_field,
    flows_trigger_editor_apply_email_filter_preset,
    flows_trigger_editor_click_email_mailbox,
    flows_trigger_editor_click_mapping_example,
    flows_trigger_editor_configure_cron,
    flows_trigger_editor_configure_platform_event,
    flows_trigger_editor_configure_telegram,
    flows_trigger_editor_configure_webhook,
    flows_trigger_editor_expect_ready_curl,
    flows_trigger_editor_expect_sample_panel,
    flows_trigger_editor_fill_identity,
    flows_trigger_editor_open_tab,
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
    doc_slug="agent-triggers-overview",
    title="Что такое триггеры и как начать их настраивать",
    description=(
        "**Для чего:** эта инструкция покажет, где у агента живут автозапуски и какие "
        "пять типов триггеров доступны.\n\n"
        "**Какие проблемы решает:** новичок не знает, чем webhook отличается от "
        "расписания и с чего начать — сначала нужен сам агент и список триггеров.\n\n"
        "**Результат:** «Помощник Зелёного сада» создан, открыт список триггеров и "
        "форма создания с общими полями."
    ),
    title_en="What triggers are and how to start configuring them",
    description_en=(
        "**What for:** this guide shows where an agent keeps automatic runs and which "
        "five trigger types exist.\n\n"
        "**Problems it solves:** beginners do not know how a webhook differs from a "
        "schedule or where to start — first you need the agent and the triggers list.\n\n"
        "**Result:** the Green Garden Assistant is created, the triggers list is open, "
        "and the create form shows the shared fields."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_flows_agent_triggers_overview(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.goto(f"{flows_ui.origin}/flows/", wait_until="domcontentloaded")
    await expect(page.locator("flows-home-page")).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте каталог агентов",
        page,
        screenshot_name="catalog-before-triggers",
        label_en="Open the agent catalog",
        details=(
            "На главной Flows слева — каталог. Триггеры настраивают у конкретного агента, "
            "поэтому сначала создайте или откройте помощника магазина."
        ),
        details_en=(
            "On the Flows home the catalog is on the left. Triggers belong to a specific "
            "agent, so create or open the store assistant first."
        ),
    )

    create_button = page.locator("flows-catalog-list [data-action='create-flow']").first
    await expect(create_button).to_be_visible(timeout=30_000)
    await create_button.click()
    modal = page.locator("flows-flow-create-modal").first
    await expect(modal).to_be_visible(timeout=30_000)
    preset = modal.locator("platform-picker-card[value='react']").first
    await expect(preset).to_be_visible(timeout=15_000)
    await preset.click()
    fields = modal.locator("platform-field")
    await expect(fields.first).to_be_visible(timeout=15_000)
    flow_id = flows_doc_flow_id("trig_ov", unique_id)
    await flows_set_platform_field(fields.nth(0), flow_id)
    if await fields.count() > 1:
        await flows_set_platform_field(fields.nth(1), GREEN_GARDEN_AGENT_NAME)
    if await fields.count() > 2:
        await flows_set_platform_field(
            fields.nth(2),
            "Агент магазина для автозапусков по почте, Telegram и webhook",
        )
    await scenario.step(
        "Создайте агента из шаблона",
        page,
        screenshot_name="agent-created-for-triggers",
        label_en="Create an agent from a template",
        details=(
            "Выберите шаблон обычного агента, укажите идентификатор и название "
            "«Помощник Зелёного сада». После создания откроется редактор с готовой "
            "нодой ответа."
        ),
        details_en=(
            "Pick the plain agent template, set an identifier and the name Green Garden "
            "Assistant. The editor opens with a ready answer node."
        ),
    )
    await flows_click_platform_button(modal, "Создать", "Create", "Готово", "Done")
    studio_sections = page.get_by_role(
        "group", name=re.compile(r"Agent editor sections", re.I)
    )
    canvas = page.locator("flows-flow-canvas").first
    try:
        await expect(studio_sections.first).to_be_visible(timeout=15_000)
    except AssertionError:
        await expect(canvas.locator("svg.canvas-host")).to_be_visible(timeout=30_000)

    await flows_open_triggers_modal(page)
    await expect(page.locator("flows-triggers-modal")).to_be_visible(timeout=15_000)
    await scenario.step(
        "Откройте список триггеров",
        page,
        screenshot_name="triggers-list-empty",
        label_en="Open the triggers list",
        details=(
            "В меню редактора выберите «Триггеры». Здесь появятся все автозапуски: "
            "расписание, Telegram, webhook, почта и события платформы. Пока список "
            "пустой — это нормально для нового агента."
        ),
        details_en=(
            "In the editor menu choose Triggers. All automatic runs appear here: "
            "schedule, Telegram, webhook, email, and platform events. An empty list is "
            "normal for a new agent."
        ),
    )

    await flows_triggers_click_create(page)
    editor = page.locator("flows-trigger-editor-modal").first
    await expect(editor).to_be_visible(timeout=15_000)
    await expect(editor.locator(".trigger-type-option")).to_have_count(5, timeout=10_000)
    await scenario.step(
        "Посмотрите пять типов триггера",
        page,
        screenshot_name="five-trigger-types",
        label_en="Look at the five trigger types",
        details=(
            "Нажмите «+». Карточки типов: Cron — по времени; Telegram — сообщения бота; "
            "Webhook — HTTP от внешней системы; Почта — входящие письма ящика; "
            "Событие платформы — действия в CRM, задачах и других сервисах."
        ),
        details_en=(
            "Click +. Type cards: Cron — on a schedule; Telegram — bot messages; "
            "Webhook — HTTP from an external system; Email — inbound mailbox mail; "
            "Platform event — actions in CRM, tasks, and other services."
        ),
    )

    await flows_trigger_editor_select_type(page, "cron")
    await flows_trigger_editor_fill_identity(
        page,
        trigger_id=f"overview_{unique_id[:8]}",
        name="Черновик для знакомства",
    )
    await expect(editor.get_by_text(re.compile(r"Включён|Enabled", re.I))).to_be_visible(
        timeout=10_000
    )
    await scenario.step(
        "Изучите общие поля любой формы триггера",
        page,
        screenshot_name="common-trigger-fields",
        label_en="Learn the shared fields on any trigger form",
        details=(
            "**Демонстрация результата.** У каждого триггера есть идентификатор (латиница "
            "для системы), название (для людей в списке), переключатель «Включён» и выбор "
            "ветки сценария. Дальше откройте отдельную инструкцию по нужному типу и "
            "заполните его поля.\n\n"
            "**Итог.** Вы умеете создать агента, открыть триггеры и выбрать тип автозапуска."
        ),
        details_en=(
            "**Result demonstration.** Every trigger has an identifier (Latin for the "
            "system), a name (for people in the list), an Enabled switch, and a scenario "
            "branch picker. Next open the guide for the type you need and fill its fields.\n\n"
            "**Summary.** You can create an agent, open triggers, and pick an automatic-run type."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="triggers",
    doc_slug="schedule-daily-run",
    title="Запускаем агента по расписанию (cron)",
    description=(
        "**Для чего:** настроить ежедневный автозапуск агента без ручного старта.\n\n"
        "**Какие проблемы решает:** сводку заказов нужно готовить каждое утро — "
        "расписание само запускает помощника в нужный час и часовой пояс.\n\n"
        "**Результат:** cron-триггер с выражением, поясом и стартовым текстом сохранён."
    ),
    title_en="Run the agent on a schedule (cron)",
    description_en=(
        "**What for:** configure a daily automatic agent run without manual starts.\n\n"
        "**Problems it solves:** an order summary is needed every morning — the schedule "
        "starts the assistant at the right hour and timezone.\n\n"
        "**Result:** a cron trigger with expression, timezone, and starter text is saved."
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
        "Откройте список триггеров агента",
        page,
        screenshot_name="triggers-modal-opened",
        label_en="Open the agent triggers list",
        details=(
            "В редакторе «Помощника Зелёного сада» откройте меню и выберите «Триггеры». "
            "Здесь хранятся все автозапуски, в том числе по расписанию."
        ),
        details_en=(
            "In the Green Garden Assistant editor open the menu and choose Triggers. "
            "All automatic runs live here, including schedules."
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
    await scenario.step(
        "Выберите Cron и задайте имя",
        page,
        screenshot_name="cron-type-and-name",
        label_en="Choose Cron and set the name",
        details=(
            "Нажмите «+», выберите карточку Cron. Идентификатор — латиницей для системы; "
            "название «Ежедневная сводка заказов» увидите в списке. Переключатель "
            "«Включён» оставьте активным, иначе расписание не будет срабатывать."
        ),
        details_en=(
            "Click +, pick the Cron card. The identifier is Latin for the system; the name "
            "Daily order summary appears in the list. Leave Enabled on, or the schedule "
            "will not fire."
        ),
    )

    await flows_trigger_editor_configure_cron(
        page,
        cron="0 9 * * *",
        timezone="Europe/Moscow",
        initial_content="Сформируй сводку заказов за прошлые сутки.",
    )
    editor = page.locator("flows-trigger-editor-modal").first
    await expect(editor.locator("platform-cron-field").first).to_be_visible(timeout=10_000)
    await scenario.step(
        "Заполните расписание, пояс и стартовый текст",
        page,
        screenshot_name="cron-fields-filled",
        label_en="Fill schedule, timezone, and starter text",
        details=(
            "Выражение cron «0 9 * * *» — каждый день в 9:00 (минута, час, день, месяц, "
            "день недели). Часовой пояс Europe/Moscow — чтобы 9:00 было московским, а не "
            "UTC. «Начальный текст» — фраза, с которой агент начнёт работу, будто ей "
            "написали в чат."
        ),
        details_en=(
            "The cron expression 0 9 * * * means every day at 09:00 (minute, hour, day, "
            "month, weekday). Timezone Europe/Moscow keeps 09:00 Moscow time, not UTC. "
            "Initial text is the phrase the agent starts with, as if someone wrote it in chat."
        ),
    )

    await flows_trigger_editor_expect_sample_panel(page)
    await scenario.step(
        "Откройте Mapping и посмотрите пример данных",
        page,
        screenshot_name="cron-mapping-sample",
        label_en="Open Mapping and inspect the sample data",
        details=(
            "Вкладка Mapping показывает, какие поля придут при срабатывании (время и "
            "пояс). Примеры путей можно добавить одним кликом — они связывают входящие "
            "данные с тем, что увидит агент."
        ),
        details_en=(
            "The Mapping tab shows which fields arrive when the schedule fires (time and "
            "timezone). Example paths can be added with one click — they connect inbound "
            "data to what the agent sees."
        ),
    )

    await flows_trigger_editor_save(page)
    trigger_row = page.locator("flows-triggers-modal").get_by_text(
        re.compile(r"Ежедневная|daily|сводк", re.I)
    ).first
    await expect(trigger_row).to_be_visible(timeout=30_000)
    persisted = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    triggers = persisted.get("triggers") or {}
    assert trigger_id in triggers
    saved = triggers[trigger_id]
    assert isinstance(saved, dict)
    assert saved.get("type") == "cron"
    await scenario.step(
        "Сохраните и найдите расписание в списке",
        page,
        screenshot_name="cron-trigger-published",
        label_en="Save and find the schedule in the list",
        details=(
            "**Демонстрация результата.** Строка «Ежедневная сводка заказов» видна в "
            "списке триггеров — агент будет запускаться каждое утро по заданному "
            "расписанию.\n\n"
            "**Итог.** Вы умеете настроить cron: имя, выражение, часовой пояс и стартовый текст."
        ),
        details_en=(
            "**Result demonstration.** The Daily order summary row appears in the "
            "triggers list — the agent will run each morning on the set schedule.\n\n"
            "**Summary.** You can configure cron: name, expression, timezone, and starter text."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="triggers",
    doc_slug="telegram-auto-reply",
    title="Подключаем Telegram-бота к агенту",
    description=(
        "**Для чего:** входящие сообщения Telegram-бота будут запускать агента и "
        "получать ответ.\n\n"
        "**Какие проблемы решает:** покупатели пишут в бот магазина, а отвечать должен "
        "помощник — без ручного копирования чатов.\n\n"
        "**Результат:** Telegram-триггер с токеном из секрета и фильтром user_id сохранён."
    ),
    title_en="Connect a Telegram bot to the agent",
    description_en=(
        "**What for:** inbound Telegram bot messages will start the agent and get a reply.\n\n"
        "**Problems it solves:** customers message the store bot, and the assistant must "
        "answer — without copying chats by hand.\n\n"
        "**Result:** a Telegram trigger with a secret token and a user_id filter is saved."
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
        "Откройте триггеры в редакторе",
        page,
        screenshot_name="telegram-triggers-modal-opened",
        label_en="Open triggers in the editor",
        details=(
            "Откройте «Триггеры» у «Помощника Зелёного сада». Здесь подключают бота "
            f"{GREEN_GARDEN_TELEGRAM_BOT}, чтобы сообщения покупателей шли в агента."
        ),
        details_en=(
            "Open Triggers on the Green Garden Assistant. Here you connect the bot "
            f"{GREEN_GARDEN_TELEGRAM_BOT} so customer messages reach the agent."
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
        "Выберите Telegram и назовите триггер",
        page,
        screenshot_name="telegram-type-and-name",
        label_en="Choose Telegram and name the trigger",
        details=(
            "Карточка Telegram — для входящих Update от Bot API. Задайте короткий id и "
            "понятное название «Автоответ в Telegram». Оставьте триггер включённым."
        ),
        details_en=(
            "The Telegram card is for inbound Bot API Updates. Set a short id and a clear "
            "name such as Telegram auto-reply. Leave the trigger enabled."
        ),
    )

    token_value = f"@var:{secret_key}"
    await flows_trigger_editor_configure_telegram(
        page,
        bot_token=token_value,
        allowed_users=[10001],
    )
    editor = page.locator("flows-trigger-editor-modal").first
    await expect(
        editor.get_by_text(re.compile(r"Токен бота|Bot token", re.I))
    ).to_be_visible(timeout=10_000)
    await scenario.step(
        "Укажите токен бота и разрешённых пользователей",
        page,
        screenshot_name="telegram-token-and-users",
        label_en="Set the bot token and allowed users",
        details=(
            "В «Токен бота» укажите ссылку вида @var:telegram_bot_token — значение "
            "берётся из секретов компании, сам токен в интерфейс не копируют. "
            "«Разрешённые user_id» — числовые id Telegram через запятую; пустое поле "
            "принимает всех. Рядом — проверка конфигурации и перерегистрация webhook."
        ),
        details_en=(
            "In Bot token set a reference like @var:telegram_bot_token — the value comes "
            "from company secrets; do not paste the raw token into the UI. Allowed user "
            "ids are numeric Telegram ids, comma-separated; empty means everyone. Nearby "
            "are verify and webhook re-register actions."
        ),
    )

    await flows_trigger_editor_click_mapping_example(page, index=0)
    await flows_trigger_editor_expect_sample_panel(page)
    await scenario.step(
        "Свяжите текст сообщения с ответом агента",
        page,
        screenshot_name="telegram-mapping",
        label_en="Map message text to the agent reply",
        details=(
            "На вкладке Mapping нажмите пример пути — обычно текст сообщения попадает в "
            "content, а chat_id нужен, чтобы ответ ушёл обратно в тот же чат. Sample "
            "JSON показывает форму данных Telegram."
        ),
        details_en=(
            "On the Mapping tab click a path example — usually message text goes to "
            "content, and chat_id is needed so the reply returns to the same chat. "
            "Sample JSON shows the Telegram data shape."
        ),
    )

    await flows_trigger_editor_save(page)
    await expect(page.locator("flows-triggers-modal")).to_contain_text(
        re.compile(r"Автоответ|Telegram", re.I),
        timeout=30_000,
    )
    persisted = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    triggers = persisted.get("triggers") or {}
    assert trigger_id in triggers
    await scenario.step(
        "Сохраните автоответ и проверьте список",
        page,
        screenshot_name="telegram-trigger-published",
        label_en="Save the auto-reply and check the list",
        details=(
            "**Демонстрация результата.** Триггер «Автоответ в Telegram» есть в списке — "
            f"агент готов отвечать в {GREEN_GARDEN_TELEGRAM_BOT}.\n\n"
            "**Итог.** Вы умеете подключить бота: токен через секрет, фильтр user_id и mapping."
        ),
        details_en=(
            "**Result demonstration.** The Telegram auto-reply trigger is in the list — "
            f"the agent is ready to reply in {GREEN_GARDEN_TELEGRAM_BOT}.\n\n"
            "**Summary.** You can connect a bot: token via secret, user_id filter, and mapping."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="triggers",
    doc_slug="webhook-trigger",
    title="Запускаем агента по HTTP webhook",
    description=(
        "**Для чего:** внешняя система магазина сможет запускать агента обычным "
        "HTTP POST.\n\n"
        "**Какие проблемы решает:** события склада или CRM приходят не из Telegram и "
        "не по расписанию — нужен защищённый URL с секретом.\n\n"
        "**Результат:** webhook с секретом, заголовком, IP-фильтром и mapping сохранён."
    ),
    title_en="Run the agent from an HTTP webhook",
    description_en=(
        "**What for:** an external store system can start the agent with a plain HTTP POST.\n\n"
        "**Problems it solves:** warehouse or CRM events arrive neither from Telegram nor "
        "on a schedule — you need a protected URL with a secret.\n\n"
        "**Result:** a webhook with secret, header, IP filter, and mapping is saved."
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
            "В меню редактора выберите «Триггеры». Webhook создают здесь же — рядом с "
            "расписанием и Telegram."
        ),
        details_en=(
            "In the editor menu choose Triggers. Create a webhook here alongside "
            "schedule and Telegram."
        ),
    )

    await flows_triggers_click_create(page)
    await flows_trigger_editor_select_type(page, "webhook")
    trigger_id = f"wh_{unique_id[:8]}"
    await flows_trigger_editor_fill_identity(
        page,
        trigger_id=trigger_id,
        name="События склада",
    )
    await scenario.step(
        "Выберите Webhook и задайте имя",
        page,
        screenshot_name="webhook-type-and-name",
        label_en="Choose Webhook and set the name",
        details=(
            "Тип Webhook принимает JSON по HTTP POST (это не чат A2A). Укажите id и "
            "название «События склада». Ниже появится URL endpoint — его копируют во "
            "внешнюю систему."
        ),
        details_en=(
            "Webhook accepts JSON over HTTP POST (not an A2A chat). Set an id and the "
            "name Warehouse events. The endpoint URL appears below — copy it into the "
            "external system."
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
        "Настройте секрет, заголовок и разрешённые IP",
        page,
        screenshot_name="webhook-security-filled",
        label_en="Configure secret, header, and allowed IPs",
        details=(
            "Секрет — пароль запроса: без него платформа отклонит вызов. Заголовок "
            "секрета (здесь Authorization) — имя HTTP-заголовка, куда внешняя система "
            "кладёт этот пароль. Разрешённые IP — теги адресов; пусто = без фильтра. "
            "Готовый curl можно скопировать для проверки."
        ),
        details_en=(
            "The secret is the request password — without it the platform rejects the call. "
            "Secret header (here Authorization) is the HTTP header name that carries that "
            "password. Allowed IPs are address tags; empty means no filter. Ready curl can "
            "be copied for a smoke test."
        ),
    )

    await flows_trigger_editor_click_mapping_example(page, index=0)
    await flows_trigger_editor_expect_sample_panel(page)
    await scenario.step(
        "Добавьте mapping из примера",
        page,
        screenshot_name="webhook-mapping-example",
        label_en="Add mapping from an example",
        details=(
            "На вкладке Mapping нажмите пример — например content ← body.text. Так текст "
            "из JSON склада станет входом агента. Sample payload показывает ожидаемую форму."
        ),
        details_en=(
            "On the Mapping tab click an example — for example content ← body.text. That "
            "turns warehouse JSON text into the agent input. Sample payload shows the "
            "expected shape."
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
        "Сохраните webhook и найдите его в списке",
        page,
        screenshot_name="webhook-saved-in-list",
        label_en="Save the webhook and find it in the list",
        details=(
            "**Демонстрация результата.** «События склада» видны в списке — внешняя "
            "система может вызывать агента по защищённому URL.\n\n"
            "**Итог.** Вы умеете настроить webhook: URL, секрет, заголовок, IP и mapping."
        ),
        details_en=(
            "**Result demonstration.** Warehouse events appears in the list — an external "
            "system can call the agent on a protected URL.\n\n"
            "**Summary.** You can configure a webhook: URL, secret, header, IPs, and mapping."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="triggers",
    doc_slug="email-orders-trigger",
    title="Запускаем агента по входящим письмам",
    description=(
        "**Для чего:** письма на ящик платформы смогут запускать агента по теме или "
        "отправителю.\n\n"
        "**Какие проблемы решает:** заказы и счета приходят почтой — не хочется "
        "перечитывать ящик вручную и запускать помощника отдельно.\n\n"
        "**Результат:** почтовый триггер на выбранном ящике с пресетом фильтра по теме сохранён."
    ),
    title_en="Run the agent from inbound email",
    description_en=(
        "**What for:** messages to a platform mailbox can start the agent by subject or "
        "sender.\n\n"
        "**Problems it solves:** orders and invoices arrive by mail — you do not want to "
        "read the inbox by hand and start the assistant separately.\n\n"
        "**Result:** an email trigger on a chosen mailbox with a subject filter preset is saved."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_flows_email_orders_trigger(
    scenario: ScenarioRecorder,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    frontend_di,
    unique_id: str,
    secrets_service,
    taskiq_worker,
) -> None:
    _ = secrets_service, taskiq_worker
    binding = await flows_seed_ui_mail_mailbox(frontend_di, unique_id=unique_id)
    email_address = binding.email_address

    flow_id = flows_doc_flow_id("email_trig", unique_id)
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(
            flow_id,
            name=GREEN_GARDEN_AGENT_NAME,
            prompt="Кратко опиши входящее письмо о заказе.",
        ),
    )

    page = ui_page_system
    await flows_open_editor(page, flows_ui, flow_id)
    await flows_open_triggers_modal(page)
    await scenario.step(
        "Откройте триггеры агента",
        page,
        screenshot_name="email-triggers-modal",
        label_en="Open the agent triggers",
        details=(
            "В меню редактора выберите «Триггеры». Почтовый автозапуск слушает ящик, "
            "уже подключённый в почте платформы."
        ),
        details_en=(
            "In the editor menu choose Triggers. An email automatic run listens to a "
            "mailbox already connected in platform mail."
        ),
    )

    await flows_triggers_click_create(page)
    await flows_trigger_editor_select_type(page, "email")
    trigger_id = f"mail_{unique_id[:8]}"
    await flows_trigger_editor_fill_identity(
        page,
        trigger_id=trigger_id,
        name="Письма о заказах",
    )
    await scenario.step(
        "Выберите тип «Почта» и задайте название",
        page,
        screenshot_name="email-type-and-name",
        label_en="Choose Email and set the name",
        details=(
            "Карточка «Почта» подписывает агента на входящие письма. Укажите id и "
            "название «Письма о заказах». Если ящиков ещё нет, форма предложит открыть "
            "настройки почты — здесь ящик уже подготовлен."
        ),
        details_en=(
            "The Email card subscribes the agent to inbound mail. Set an id and the name "
            "Order emails. If no mailboxes exist yet, the form offers mail settings — "
            "here a mailbox is already prepared."
        ),
    )

    await flows_trigger_editor_click_email_mailbox(page, email_address=email_address)
    await expect(
        page.locator("flows-trigger-editor-modal article.email-chip.active").first
    ).to_be_visible(timeout=10_000)
    await scenario.step(
        "Выберите ящик одним кликом",
        page,
        screenshot_name="email-mailbox-selected",
        label_en="Pick the mailbox with one click",
        details=(
            "Нажмите чип с адресом нужного ящика. Активный чип означает, что триггер "
            "слушает именно его. Бейдж «основной» помечает ящик по умолчанию."
        ),
        details_en=(
            "Click the chip with the mailbox address you need. An active chip means the "
            "trigger listens to that mailbox. The default badge marks the primary mailbox."
        ),
    )

    await flows_trigger_editor_apply_email_filter_preset(
        page,
        preset_label=re.compile(r"заказ|order", re.I),
    )
    editor = page.locator("flows-trigger-editor-modal").first
    await expect(
        editor.get_by_text(re.compile(r"Тема содержит|Subject contains", re.I))
    ).to_be_visible(timeout=10_000)
    await scenario.step(
        "Выберите пресет фильтра по теме",
        page,
        screenshot_name="email-filter-preset",
        label_en="Choose a subject filter preset",
        details=(
            "Пресеты одним кликом заполняют фильтр: «Все письма», тема с «заказ»/«счёт»/"
            "alert или только noreply. Поля «Отправители» и «Тема содержит» можно "
            "править вручную — пустые поля означают все письма выбранного ящика."
        ),
        details_en=(
            "Presets fill the filter in one click: All mail, subject with order/invoice/"
            "alert, or noreply only. Senders and Subject contains can still be edited — "
            "empty fields mean every message for the selected mailbox."
        ),
    )

    await flows_trigger_editor_click_mapping_example(page, index=0)
    await flows_trigger_editor_expect_sample_panel(page)
    await scenario.step(
        "Настройте Mapping по sample письма",
        page,
        screenshot_name="email-mapping-sample",
        label_en="Configure Mapping from the mail sample",
        details=(
            "На вкладке Mapping видны from, subject, body. Нажмите пример — тема или "
            "текст письма станет входом агента. После сохранения можно проверить "
            "mapping кнопкой sample → Test."
        ),
        details_en=(
            "On Mapping you see from, subject, and body. Click an example — subject or "
            "body becomes the agent input. After saving you can verify mapping with "
            "sample → Test."
        ),
    )

    await flows_trigger_editor_save(page)
    trigger_row = page.locator("flows-triggers-modal").get_by_text(
        re.compile(r"Письма о заказах|Order emails|mail", re.I)
    ).first
    await expect(trigger_row).to_be_visible(timeout=30_000)
    persisted = await flows_api_get_flow(flows_ui.origin, auth_token_system, flow_id)
    triggers = persisted.get("triggers") or {}
    saved = triggers.get(trigger_id)
    assert isinstance(saved, dict), f"email trigger missing: {triggers!r}"
    assert saved.get("type") == "email"
    saved_config = saved.get("config") or {}
    assert saved_config.get("mailbox_binding_id") == binding.mailbox_binding_id
    await scenario.step(
        "Сохраните почтовый триггер и проверьте список",
        page,
        screenshot_name="email-trigger-saved",
        label_en="Save the email trigger and check the list",
        details=(
            "**Демонстрация результата.** «Письма о заказах» есть в списке — агент "
            "сработает на письма выбранного ящика с нужной темой.\n\n"
            "**Итог.** Вы умеете выбрать ящик, пресет фильтра и mapping для почтового триггера."
        ),
        details_en=(
            "**Result demonstration.** Order emails is in the list — the agent will fire "
            "on matching mail for the selected mailbox and subject.\n\n"
            "**Summary.** You can pick a mailbox, a filter preset, and mapping for an email trigger."
        ),
    )


@pytest.mark.scenario(
    service="flows",
    tag="triggers",
    doc_slug="platform-event-filters",
    title="Запускаем агента по событию платформы с фильтром",
    description=(
        "**Для чего:** агент реагирует только на нужные события из других сервисов "
        "(CRM, задачи, комментарии).\n\n"
        "**Какие проблемы решает:** без фильтра flow сработает на каждое событие "
        "типа — условие по полям сужает подписку до полезных случаев.\n\n"
        "**Результат:** триггер события платформы с условием на роль комментария сохранён."
    ),
    title_en="Run the agent on a platform event with a filter",
    description_en=(
        "**What for:** the agent reacts only to matching events from other services "
        "(CRM, tasks, comments).\n\n"
        "**Problems it solves:** without a filter the flow would fire on every event of "
        "that type — a field condition narrows the subscription to useful cases.\n\n"
        "**Result:** a platform event trigger with a comment-role condition is saved."
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
            prompt="Кратко подтверди событие платформы.",
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
        details=(
            "В меню редактора выберите «Триггеры». Событие платформы подключает агента "
            "к действиям в других сервисах без отдельного webhook."
        ),
        details_en=(
            "In the editor menu choose Triggers. A platform event connects the agent to "
            "actions in other services without a separate webhook."
        ),
    )

    await flows_triggers_click_create(page)
    await flows_trigger_editor_select_type(page, "platform_event")
    trigger_id = f"pe_{unique_id[:8]}"
    await flows_trigger_editor_fill_identity(
        page,
        trigger_id=trigger_id,
        name="Комментарий оператора",
    )
    await scenario.step(
        "Выберите «Событие платформы» и задайте имя",
        page,
        screenshot_name="platform-event-type-selected",
        label_en="Choose Platform event and set the name",
        details=(
            "Этот тип слушает каталог событий (CRM, задачи, почта и др.). Укажите id и "
            "название вроде «Комментарий оператора». Дальше выберите точный тип события."
        ),
        details_en=(
            "This type listens to the event catalog (CRM, tasks, mail, and more). Set an "
            "id and a name such as Operator comment. Next pick the exact event type."
        ),
    )

    await flows_trigger_editor_configure_platform_event(
        page,
        event_type="worktracker/work_item/comment_created",
        filters=[{"path": "comment.role", "op": "eq", "value": "operator"}],
    )
    editor = page.locator("flows-trigger-editor-modal").first
    await expect(editor.locator(".event-filter-row").first).to_be_visible(timeout=15_000)
    await scenario.step(
        "Выберите тип события и условие фильтра",
        page,
        screenshot_name="platform-event-filters-filled",
        label_en="Pick the event type and a filter condition",
        details=(
            "Тип события — из каталога (список с автодополнением). Фильтр — строка "
            "«поле / операция / значение»: поле берётся из каталога события, операция "
            "«равно» / «не равно» / «содержит», значение — например роль operator. "
            "Без условий агент сработает на каждое событие этого типа."
        ),
        details_en=(
            "Event type comes from the catalog (autocomplete list). A filter row is "
            "field / operator / value: the field comes from the event catalog, the "
            "operator is equals / not equals / contains, and the value might be the "
            "operator role. With no conditions the agent fires on every event of that type."
        ),
    )

    await flows_trigger_editor_open_tab(page, "mapping")
    await flows_trigger_editor_expect_sample_panel(page)
    await scenario.step(
        "Проверьте sample payload на вкладке Mapping",
        page,
        screenshot_name="platform-event-mapping-sample",
        label_en="Check the sample payload on Mapping",
        details=(
            "Sample показывает оболочку события: тип, компания, полезные поля payload. "
            "Примеры путей помогают передать нужные данные в content агента."
        ),
        details_en=(
            "The sample shows the event envelope: type, company, and useful payload "
            "fields. Path examples help pass the right data into the agent content."
        ),
    )

    await flows_trigger_editor_save(page)
    trigger_row = page.locator("flows-triggers-modal").get_by_text(
        re.compile(r"Комментарий оператора|Operator comment|platform", re.I)
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
    assert filters[0].get("value") == "operator"
    await scenario.step(
        "Сохраните триггер и найдите его в списке",
        page,
        screenshot_name="platform-event-saved-in-list",
        label_en="Save the trigger and find it in the list",
        details=(
            "**Демонстрация результата.** «Комментарий оператора» в списке — агент "
            "ответит только когда в задаче появится комментарий с ролью operator.\n\n"
            "**Итог.** Вы умеете подписаться на событие платформы и сузить его фильтром."
        ),
        details_en=(
            "**Result demonstration.** Operator comment is in the list — the agent "
            "reacts only when a work item gets a comment with role operator.\n\n"
            "**Summary.** You can subscribe to a platform event and narrow it with a filter."
        ),
    )
