"""Сценарии документации консоли компании (сервис frontend) и инструментов
оболочки (сервис platform): приглашения, профиль, почта, календарь, поиск,
переменные, оплата, API-ключи, расписания и встраиваемые виджеты.

Каждый сценарий — реальный маршрут: навигация по консоли, открытие модалки или
страницы и действие, которое сделал бы обычный пользователь. Показанные данные
настоящие (ящик и письмо посеяны в общей БД, приглашение настоящее, ключ API
настоящий): никаких подставных состояний.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest
from playwright.async_api import Page, ViewportSize, expect
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from tests.ui.harness import AppUI, ui_set_platform_field
from tests.ui.scenario_doc import ScenarioRecorder

_DESKTOP = ViewportSize(width=1440, height=900)


async def _open_user_menu(page: Page):
    button = page.locator("platform-user button.user-button").first
    await expect(button).to_be_visible(timeout=30_000)
    await button.click()
    menu = page.locator("platform-user .user-menu").first
    await expect(menu).to_be_visible(timeout=30_000)
    return menu


async def _seed_mailbox_with_message(frontend_di, unique_id: str) -> None:
    """ACTIVE-ящик (default) + INBOX-папка + одно письмо в общей БД (почта local-first)."""
    from core.mail.models import MailboxBinding, StoredMailboxFolder, StoredMailMessage
    from core.mail.models.contracts import MailFolderRole
    from tests.ui.e2e.flows_e2e_helpers import flows_seed_ui_mail_mailbox

    binding = await flows_seed_ui_mail_mailbox(frontend_di, unique_id=unique_id)
    # Модалка открывает дефолтный ящик: ящики накапливаются между прогонами,
    # поэтому свежий ящик сценария явно делаем default для пользователя.
    binding.is_default = True
    _ = await binding.save()
    if binding.user_id is None:
        raise ValueError("user mailbox binding requires user_id")
    await MailboxBinding.clear_defaults_for_user(
        binding.company_id, binding.user_id, except_binding_id=binding.mailbox_binding_id
    )
    now = datetime.now(timezone.utc)
    _ = await StoredMailboxFolder.objects.create(
        instance=StoredMailboxFolder(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder_name="INBOX",
            company_id=binding.company_id,
            role=MailFolderRole.INBOX,
            message_count=1,
            unseen_count=1,
            sort_index=0,
        )
    )
    _ = await StoredMailMessage.upsert_by_binding_folder_uid(
        StoredMailMessage(
            mail_message_id=f"mm_doc_{unique_id}",
            company_id=binding.company_id,
            mailbox_binding_id=binding.mailbox_binding_id,
            user_id=binding.user_id,
            folder="INBOX",
            uid=11,
            message_id=f"<doc-{unique_id}@example.com>",
            thread_id=f"th_doc_{unique_id}",
            subject="Подтверждение заказа 1042 — счёт во вложении",
            from_address="client@rossisrl.example.com",
            to_addresses=[binding.email_address],
            date_at=now,
            unread=True,
            snippet="Добрый день, подтверждаем заказ 1042. Подписанный счёт во вложении.",
            body_text=(
                "Добрый день,\n\nподтверждаем заказ 1042 с доставкой в "
                "пятницу. Подписанный счёт во вложении.\n\n"
                "С уважением,\nотдел закупок Rossi Srl"
            ),
            synced_at=now,
            created_at=now,
        )
    )


@pytest.mark.scenario(
    service="frontend",
    tag="general",
    doc_slug="invite-team-member",
    title="Пригласить коллегу по ссылке",
    title_en="Invite a colleague with a link",
    description=(
        "**Для чего:** добавить коллегу в компанию без технических "
        "настроек: создаётся ссылка-приглашение, которую можно отправить "
        "как угодно (почта, чат, SMS).\n\n"
        "**Какие проблемы решает:** у нового сотрудника ещё нет аккаунта; "
        "по ссылке он регистрируется сам и входит с выбранной ролью.\n\n"
        "**Результат:** ссылка-приглашение скопирована в буфер обмена и "
        "готова к отправке коллеге."
    ),
    description_en=(
        "**Purpose:** add a colleague to the company with no technical "
        "setup: generate an invite link and send it any way you like "
        "(mail, chat, SMS).\n\n"
        "**Problems solved:** the new hire has no account yet; with the "
        "link they sign up on their own and join with the role you picked.\n\n"
        "**Result:** an invite link copied to the clipboard, ready to send."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_frontend_invite_team_member(
    scenario: ScenarioRecorder,
    frontend_ui: AppUI,
    ui_page_system: Page,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)
    await frontend_ui.open(page)
    await page.goto(f"{frontend_ui.origin}/dashboard", wait_until="domcontentloaded")
    await expect(page.locator("platform-user button.user-button")).to_be_visible(timeout=30_000)

    await page.goto(f"{frontend_ui.origin}/team", wait_until="domcontentloaded")
    await expect(page.locator("frontend-team-page")).to_be_visible(timeout=30_000)
    await expect(page.locator(".invite-toolbar .btn-invite")).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте страницу «Команда»",
        page,
        screenshot_name="team-page",
        label_en="Open the Team page",
        details=(
            "В консоли откройте «Команда»: таблица показывает всех "
            "сотрудников компании и их роли (владелец, админ, разработчик, "
            "наблюдатель). Над списком — строка приглашения."
        ),
        details_en=(
            "In the console open «Team»: the table lists every company "
            "member with their roles (owner, admin, developer, viewer). "
            "Above the list is the invite row."
        ),
    )

    await ui_set_platform_field(page.locator(".invite-toolbar .invite-role"), "viewer")
    await scenario.step(
        "Выберите роль нового коллеги",
        page,
        screenshot_name="invite-role",
        label_en="Pick the new colleague's role",
        details=(
            "Слева выберите, с какой ролью войдёт человек по ссылке: "
            "«наблюдатель» смотрит без изменений, «разработчик» работает, "
            "«админ» управляет. Здесь выбираем «наблюдатель» — самый "
            "осторожный вариант для новичка."
        ),
        details_en=(
            "On the left pick the role whoever uses the link will get: "
            "«viewer» can look but not change, «developer» works, "
            "«admin» manages. Here we choose «viewer», the safest for "
            "someone starting out."
        ),
    )

    await page.locator(".invite-toolbar .btn-invite").click()
    toast = (
        page.locator("glass-toast")
        .filter(has_text=re.compile(r"скопир|copied|приглаш|invite", re.I))
        .first
    )
    await expect(toast).to_be_visible(timeout=30_000)
    await scenario.step(
        "Нажмите «Копировать приглашение» и отправьте ссылку",
        page,
        screenshot_name="invite-copied",
        label_en="Press «Copy invite» and send the link",
        details=(
            "**Демонстрация результата.** Кнопка создаёт ссылку (в первый "
            "раз) и копирует её в буфер обмена: сообщение подтверждает, "
            "что ссылка готова. Вставьте её в письмо или в чат: открывший "
            "её человек регистрируется и входит в компанию с выбранной "
            "ролью.\n\n"
            "**Итог.** Приглашение готово: пароль сообщать не нужно, "
            "коллега делает всё сам по ссылке."
        ),
        details_en=(
            "**Result demonstration.** The button creates the link (first "
            "time) and copies it to the clipboard: the message confirms "
            "the link is ready. Paste it into an email or chat: whoever "
            "opens it signs up and joins the company with the chosen "
            "role.\n\n"
            "**Summary.** Invite ready: no password to share, the "
            "colleague does everything from the link."
        ),
    )


@pytest.mark.scenario(
    service="platform",
    tag="tools",
    doc_slug="profile-and-settings",
    title="Ваш профиль и настройки компании",
    title_en="Your profile and company settings",
    description=(
        "**Для чего:** посмотреть и исправить свои данные (имя, язык) и "
        "найти настройки компании в одном месте.\n\n"
        "**Какие проблемы решает:** имя, которое видят коллеги, "
        "неправильное или неполное; либо нужно узнать тариф и статус "
        "подписки.\n\n"
        "**Результат:** профиль сохранён, страница настроек открыта на "
        "вкладке компании."
    ),
    description_en=(
        "**Purpose:** view and fix your details (name, language) and "
        "find the company settings in one place.\n\n"
        "**Problems solved:** the name shown to colleagues is wrong or "
        "incomplete, or you need the subscription plan and status.\n\n"
        "**Result:** profile saved and the settings page open on the "
        "company tab."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_platform_profile_and_settings(
    scenario: ScenarioRecorder,
    frontend_ui: AppUI,
    ui_page_system: Page,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)
    await frontend_ui.open(page)
    await page.goto(f"{frontend_ui.origin}/dashboard", wait_until="domcontentloaded")
    await expect(page.locator("platform-user button.user-button")).to_be_visible(timeout=30_000)

    menu = await _open_user_menu(page)
    await menu.locator("[data-menu-action='profile']").click()
    modal = page.locator("platform-user-info-modal")
    await expect(modal).to_be_visible(timeout=30_000)
    await expect(modal.get_by_role("textbox").first).to_be_visible(timeout=30_000)
    await scenario.step(
        "В меню пользователя откройте «Профиль»",
        page,
        screenshot_name="profile-modal",
        label_en="From the user menu open «Profile»",
        details=(
            "Нажмите на своё имя справа вверху и выберите «Профиль»: "
            "окно показывает имя, фамилию, email и язык. Это карточка, "
            "которую коллеги видят рядом с вашим именем."
        ),
        details_en=(
            "Click your name at the top right, then «Profile»: the "
            "window shows first name, last name, email and language. "
            "This is the card colleagues see next to your name."
        ),
    )

    await (
        modal.locator("platform-button")
        .filter(has_text=re.compile(r"Сохранить|Save", re.I))
        .first.click()
    )
    toast = page.locator("glass-toast").filter(has_text=re.compile(r"сохран|saved", re.I)).first
    await expect(toast).to_be_visible(timeout=30_000)
    await scenario.step(
        "Исправьте и нажмите «Сохранить»",
        page,
        screenshot_name="profile-saved",
        label_en="Fix and press «Save»",
        details=(
            "Если что-то не так (имя сокращено, язык не тот) — исправьте "
            "поле и нажмите «Сохранить»: сообщение подтверждает, что "
            "профиль обновлён, и коллеги сразу видят новое имя."
        ),
        details_en=(
            "If something is off (shortened name, wrong language) fix "
            "the field and press «Save»: the message confirms the "
            "profile is updated and colleagues immediately see the new "
            "name."
        ),
    )

    await expect(modal).not_to_be_visible(timeout=15_000)
    await page.goto(f"{frontend_ui.origin}/settings", wait_until="domcontentloaded")
    await expect(page.locator("frontend-settings-page")).to_be_visible(timeout=30_000)
    await expect(page.locator("section").first).to_be_visible(timeout=30_000)
    await scenario.step(
        "Настройки компании: вкладка «Компания»",
        page,
        screenshot_name="settings-company",
        label_en="Company settings: the «Company» tab",
        details=(
            "**Демонстрация результата.** На странице «Настройки» вверху "
            "вкладки; «Компания» показывает идентификатор, статус, "
            "владельца и тариф. Остальные вкладки (безопасность, "
            "интеграции, хранилища) нужны администратору.\n\n"
            "**Итог.** Теперь вы знаете, где исправить свой профиль и "
            "где прочитать данные подписки компании."
        ),
        details_en=(
            "**Result demonstration.** The «Settings» page has tabs on "
            "top; «Company» shows identifier, status, owner and tariff "
            "plan. The other tabs (security, integrations, storage) are "
            "for the administrator.\n\n"
            "**Summary.** You know where to fix your profile and where "
            "to read the company subscription details."
        ),
    )


@pytest.mark.scenario(
    service="platform",
    tag="tools",
    doc_slug="mail-connect-and-inbox",
    title="Почта компании в меню пользователя",
    title_en="Company mail from the user menu",
    description=(
        "**Для чего:** читать почту компании, не открывая другую "
        "программу: окно «Почта» показывает папки, письма и позволяет "
        "ответить.\n\n"
        "**Какие проблемы решает:** рабочие письма приходят на адрес "
        "компании; из меню пользователя их можно читать там же, где "
        "работаете.\n\n"
        "**Результат:** ящик открыт, входящие письма видны, письмо "
        "прочитано в области чтения."
    ),
    description_en=(
        "**Purpose:** read company mail without opening another "
        "program: the «Mail» window shows folders, messages, and lets "
        "you reply.\n\n"
        "**Problems solved:** work mail arrives on a company address; "
        "from the user menu you read it where you already work.\n\n"
        "**Result:** the mailbox open with incoming messages and a "
        "message read in the reading pane."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_platform_mail_inbox(
    scenario: ScenarioRecorder,
    frontend_ui: AppUI,
    frontend_di,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    await _seed_mailbox_with_message(frontend_di, unique_id)

    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)
    await frontend_ui.open(page)
    await page.goto(f"{frontend_ui.origin}/dashboard", wait_until="domcontentloaded")
    await expect(page.locator("platform-user button.user-button")).to_be_visible(timeout=30_000)

    menu = await _open_user_menu(page)
    await menu.locator("[data-menu-action='mail']").click()
    modal = page.locator("platform-mail-modal")
    await expect(modal).to_be_visible(timeout=30_000)
    row = modal.locator(".msg-row").filter(has_text="Подтверждение заказа 1042").first
    await expect(row).to_be_visible(timeout=60_000)
    await scenario.step(
        "В меню пользователя откройте «Почту»",
        page,
        screenshot_name="mail-inbox",
        label_en="From the user menu open «Mail»",
        details=(
            "Нажмите на своё имя справа вверху и выберите «Почта»: "
            "слева папки (входящие, отправленные, черновики, корзина), "
            "в центре — список писем. Жирным выделено ещё не прочитанное."
        ),
        details_en=(
            "Click your name at the top right, then «Mail»: folders on "
            "the left (inbox, sent, drafts, trash), the message list in "
            "the middle. Bold messages are unread."
        ),
    )

    await row.click()
    await expect(modal.locator(".mail-thread, .mail-reader, .mail-message").first).to_be_visible(
        timeout=30_000
    )
    await expect(modal).to_contain_text("Подписанный счёт", timeout=30_000)
    await scenario.step(
        "Нажмите на письмо, чтобы прочитать",
        page,
        screenshot_name="mail-read",
        label_en="Click the message to read it",
        details=(
            "**Демонстрация результата.** Один клик открывает письмо "
            "справа: отправитель, тема и полный текст. Отсюда можно "
            "ответить или переслать; папка обновляется сама, когда "
            "приходит новая почта.\n\n"
            "**Итог.** Почта компании читается и обрабатывается внутри "
            "платформы, в том же окне, что и другие инструменты."
        ),
        details_en=(
            "**Result demonstration.** One click opens the message on "
            "the right: sender, subject and full body. From here you "
            "reply or forward; the folder updates itself when new mail "
            "arrives.\n\n"
            "**Summary.** Company mail is read and managed inside the "
            "platform, in the same window as the other tools."
        ),
    )


@pytest.mark.scenario(
    service="platform",
    tag="tools",
    doc_slug="calendar-modal",
    title="Календарь из меню пользователя",
    title_en="The calendar from the user menu",
    description=(
        "**Для чего:** проверять встречи и сроки, не меняя приложение: "
        "календарь открывается из меню пользователя в один клик.\n\n"
        "**Какие проблемы решает:** во время работы нужен быстрый "
        "взгляд на день или неделю без потери открытой страницы.\n\n"
        "**Результат:** календарь открыт поверх работы, готов к "
        "просмотру и закрытию."
    ),
    description_en=(
        "**Purpose:** check appointments and deadlines without "
        "switching apps: the calendar opens from the user menu in one "
        "click.\n\n"
        "**Problems solved:** while working you need a quick glance at "
        "the day or week without losing the page you are on.\n\n"
        "**Result:** the calendar open over your work, ready to "
        "consult and close."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_platform_calendar_modal(
    scenario: ScenarioRecorder,
    frontend_ui: AppUI,
    ui_page_system: Page,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)
    await frontend_ui.open(page)
    await page.goto(f"{frontend_ui.origin}/dashboard", wait_until="domcontentloaded")
    await expect(page.locator("platform-user button.user-button")).to_be_visible(timeout=30_000)

    menu = await _open_user_menu(page)
    await menu.locator("[data-menu-action='calendar']").click()
    modal = page.locator("platform-calendar-modal")
    await expect(modal).to_be_visible(timeout=30_000)
    await expect(modal.locator(".calendar-shell")).to_be_visible(timeout=30_000)
    await scenario.step(
        "В меню пользователя откройте «Календарь»",
        page,
        screenshot_name="calendar-open",
        label_en="From the user menu open «Calendar»",
        details=(
            "Нажмите на своё имя справа вверху и выберите «Календарь»: "
            "окно открывается поверх работы без смены страницы. Текущий "
            "месяц показывает встречи недели."
        ),
        details_en=(
            "Click your name at the top right, then «Calendar»: the "
            "window opens over your work without changing page. The "
            "current month shows the week's appointments."
        ),
    )

    await scenario.step(
        "Посмотрите и закройте",
        page,
        screenshot_name="calendar-view",
        label_en="Consult and close",
        details=(
            "**Демонстрация результата.** Календарь общий с почтой "
            "компании: события из писем и встречи появляются здесь. "
            "Когда закончили — закройте окно и вернитесь туда, где "
            "были.\n\n"
            "**Итог.** Повестка всегда в одном клике, без лишних окон."
        ),
        details_en=(
            "**Result demonstration.** The calendar is shared with "
            "company mail: events from emails and appointments appear "
            "here. When done, close the window and get back to where "
            "you were.\n\n"
            "**Summary.** Agenda always one click away, no extra "
            "windows."
        ),
    )


@pytest.mark.scenario(
    service="frontend",
    tag="general",
    doc_slug="search-everything",
    title="Поиск встроенным движком платформы",
    title_en="Search with the platform engine",
    description=(
        "**Для чего:** страница «Поиск» в консоли ищет информацию в "
        "интернете встроенным движком.\n\n"
        "**Какие проблемы решает:** нужен быстрый ответ, не открывая "
        "другой сайт: поиск показывает использованные источники и "
        "результаты.\n\n"
        "**Результат:** поиск выполнен, результаты и источники видны "
        "под строкой запроса."
    ),
    description_en=(
        "**Purpose:** use the console's «Search» page to find "
        "information on the web with the built-in engine.\n\n"
        "**Problems solved:** you need a quick answer without opening "
        "another site: search shows the sources used and the results.\n\n"
        "**Result:** a search run with results and sources listed "
        "below the box."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_frontend_search_everything(
    scenario: ScenarioRecorder,
    frontend_ui: AppUI,
    frontend_di,
    ui_page_system: Page,
    search_worker_prerequisites: None,
    unique_id: str,
) -> None:
    # Платформенный индекс runet читает RAG-неймспейс runet:platform; сид
    # идёт тем же путём, что index-provider: контекст системного админа,
    # регистрация namespace и ingest через RagClient (ServiceClient-контракт).
    from core.clients.rag_client import RagClient
    from core.context import clear_context, set_context
    from core.identity.system_bootstrap import build_system_admin_job_context

    _ = set_context(
        await build_system_admin_job_context(
            trace_id=f"ui_doc_search_{unique_id}",
            session_id=f"ui_doc_search_{unique_id}",
            channel="ui_e2e",
        )
    )
    try:
        _ = await frontend_di.namespace_service.get_or_create(
            "runet:platform", description="Платформенный индекс русскоязычного веба"
        )
        source_url = f"https://nalog.example/{unique_id}/hours"
        _ = await RagClient().ingest_text(
            "runet:platform",
            (
                "Налоговая инспекция работает в будние дни с 9:00 до 18:00, "
                "в субботу — с 10:00 до 15:00, воскресенье — выходной. "
                "Приём без записи, электронная очередь в зале обслуживания."
            ),
            document_name=f"nalog-hours-{unique_id}.md",
            metadata={"source_url": source_url, "collection_id": "runet"},
        )
    finally:
        clear_context()

    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)
    await frontend_ui.open(page)
    await page.goto(f"{frontend_ui.origin}/dashboard", wait_until="domcontentloaded")
    await expect(page.locator("platform-user button.user-button")).to_be_visible(timeout=30_000)

    await page.goto(f"{frontend_ui.origin}/search", wait_until="domcontentloaded")
    search_page = page.locator("public-search-page, frontend-search-page")
    await expect(search_page).to_be_visible(timeout=30_000)
    cookie_panel = page.locator("cookie-consent-banner .panel")
    try:
        await cookie_panel.wait_for(state="visible", timeout=10_000)
    except PlaywrightTimeoutError:
        pass
    else:
        await page.locator("cookie-consent-banner .cosmic-btn--primary").click()
        await expect(cookie_panel).not_to_be_visible(timeout=30_000)
    box = page.locator("input[type='search']").first
    await expect(box).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте страницу «Поиск»",
        page,
        screenshot_name="search-home",
        label_en="Open the «Search» page",
        details=(
            "В консоли откройте «Поиск»: одна строка по центру, как у "
            "привычных поисковиков. Ниже — источники, которые будет "
            "использовать движок."
        ),
        details_en=(
            "In the console open «Search»: a single box in the "
            "middle, like the engines you already know. Below it lists "
            "the sources the engine will use."
        ),
    )

    await box.fill("часы работы налоговой инспекции")
    await box.press("Enter")
    results = page.locator(".serp-item, .serp-result, .result-item, article").first
    await expect(results).to_be_visible(timeout=120_000)
    await scenario.step(
        "Напишите вопрос и нажмите Enter",
        page,
        screenshot_name="search-results",
        label_en="Type the question and press Enter",
        details=(
            "**Демонстрация результата.** Написали вопрос и нажали "
            "Enter — результаты появляются под строкой: заголовок, "
            "адрес источника и выдержка. Один клик открывает "
            "оригинальную страницу.\n\n"
            "**Итог.** Поиск внутри консоли: движок отвечает, источники "
            "читаются не выходя."
        ),
        details_en=(
            "**Result demonstration.** Once the question is typed and "
            "Enter pressed, results arrive below the box with title, "
            "source address and an excerpt. One click opens the "
            "original page.\n\n"
            "**Summary.** Search lives inside the console: query the "
            "engine and read the sources without leaving."
        ),
    )


@pytest.mark.scenario(
    service="frontend",
    tag="general",
    doc_slug="company-variables",
    title="Переменные компании",
    title_en="Company variables",
    description=(
        "**Для чего:** переменные компании — общие настройки, которые "
        "используют агенты и автоматизации (названия служб, часы работы, "
        "стандартные ответы).\n\n"
        "**Какие проблемы решает:** значение, используемое во многих "
        "местах, изменилось: исправляете один раз — все агенты берут "
        "новое.\n\n"
        "**Результат:** переменная создана и видна в списке."
    ),
    description_en=(
        "**Purpose:** company variables are shared settings used by "
        "agents and automations (service names, hours, standard "
        "replies).\n\n"
        "**Problems solved:** a value used in many places changes: fix "
        "it once and every agent uses the new one.\n\n"
        "**Result:** a variable created and visible in the list."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_frontend_company_variables(
    scenario: ScenarioRecorder,
    frontend_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)
    await frontend_ui.open(page)
    await page.goto(f"{frontend_ui.origin}/dashboard", wait_until="domcontentloaded")
    await expect(page.locator("platform-user button.user-button")).to_be_visible(timeout=30_000)

    await page.goto(f"{frontend_ui.origin}/company-variables", wait_until="domcontentloaded")
    await expect(page.locator("frontend-company-variables-page")).to_be_visible(timeout=30_000)
    panel = page.locator("platform-company-variables-panel")
    await expect(panel).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте «Переменные компании»",
        page,
        screenshot_name="variables-page",
        label_en="Open «Company variables»",
        details=(
            "Страница перечисляет уже заданные переменные: ключ, "
            "название и кто их видит. Справа — справка, которая "
            "объясняет, для чего они нужны."
        ),
        details_en=(
            "The page lists the variables already defined: key, title "
            "and who can see them. On the right a guide explains what "
            "they are for."
        ),
    )

    await panel.locator(".toolbar platform-button").first.click()
    editor = page.locator("platform-company-variable-editor-modal")
    await expect(editor).to_be_visible(timeout=30_000)
    await ui_set_platform_field(
        editor.locator("platform-field").first, f"DOC_{unique_id[:10].upper()}"
    )
    await editor.locator("platform-variable-value-editor").evaluate(
        """el => el.dispatchEvent(new CustomEvent('change', {
            detail: { value_kind: 'static', value: 'Пн–Пт 9:00–18:00',
                      expression: '' }, bubbles: true, composed: true }))"""
    )
    await scenario.step(
        "Нажмите «Создать» и заполните ключ и значение",
        page,
        screenshot_name="variable-editor",
        label_en="Press «Create» and fill key and value",
        details=(
            "В окне укажите ключ (техническое имя, например CHASY_RABOTY) "
            "и значение. «Секретные» переменные остаются скрытыми даже "
            "здесь — в безопасности."
        ),
        details_en=(
            "In the window set the key (the technical name, e.g. "
            "WORK_HOURS) and the value. «Secret» variables stay hidden "
            "even here, kept safe."
        ),
    )

    await editor.locator("button.header-save-btn").click()
    await expect(editor).not_to_be_visible(timeout=30_000)
    row = panel.locator("tr, .variable-row").filter(has_text=f"DOC_{unique_id[:10].upper()}").first
    await expect(row).to_be_visible(timeout=30_000)
    await scenario.step(
        "Переменная в списке",
        page,
        screenshot_name="variable-created",
        label_en="The variable in the list",
        details=(
            "**Демонстрация результата.** После сохранения переменная "
            "появляется в таблице: её видно всем агентам компании, и "
            "изменение значения здесь сразу действует везде.\n\n"
            "**Итог.** Одна правка — и все автоматизации используют "
            "новое значение."
        ),
        details_en=(
            "**Result demonstration.** After saving, the variable "
            "appears in the table: all company agents see it, and "
            "editing the value here takes effect everywhere at once.\n\n"
            "**Summary.** One edit — and every automation uses the new "
            "value."
        ),
    )


@pytest.mark.scenario(
    service="frontend",
    tag="general",
    doc_slug="billing-and-limits",
    title="Подписка, расход и счета",
    title_en="Subscription, usage and invoices",
    description=(
        "**Для чего:** проверить тариф, расход за месяц и историю счетов "
        "компании на странице «Оплата».\n\n"
        "**Какие проблемы решает:** понять, сколько тратится и где "
        "скачать счета, не обращаясь в поддержку.\n\n"
        "**Результат:** тариф, счётчики расхода и история видны сразу."
    ),
    description_en=(
        "**Purpose:** check the company plan, this month's usage, and "
        "invoice history from the «Billing» page.\n\n"
        "**Problems solved:** understand how much is being spent and "
        "download invoices without writing to support.\n\n"
        "**Result:** plan, usage meters and history visible at a glance."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_frontend_billing_and_limits(
    scenario: ScenarioRecorder,
    frontend_ui: AppUI,
    ui_page_system: Page,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)
    await frontend_ui.open(page)
    await page.goto(f"{frontend_ui.origin}/dashboard", wait_until="domcontentloaded")
    await expect(page.locator("platform-user button.user-button")).to_be_visible(timeout=30_000)

    await page.goto(f"{frontend_ui.origin}/billing", wait_until="domcontentloaded")
    billing = page.locator("frontend-billing-page")
    await expect(billing).to_be_visible(timeout=30_000)
    await expect(billing.locator("glass-card").first).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте «Оплату»: тариф и баланс",
        page,
        screenshot_name="billing-overview",
        label_en="Open «Billing»: plan and balance",
        details=(
            "Вверху карточки с активным тарифом, балансом и лимитами "
            "периода. Если расход приближается к лимиту, вы увидите это "
            "здесь до того, как работа замедлится."
        ),
        details_en=(
            "At the top, cards show the active plan, balance and "
            "period limits. If a usage nears its limit you see it here "
            "before it slows the work."
        ),
    )

    usage_section = billing.locator("section").first
    await usage_section.scroll_into_view_if_needed()
    await scenario.step(
        "Расход за месяц по статьям",
        page,
        screenshot_name="billing-usage",
        label_en="This month's usage, item by item",
        details=(
            "Ниже раздел расхода детализирует, сколько использовано "
            "каждого платного сервиса (агенты, распознавание документов, "
            "звонки). Цифры обновляются сами."
        ),
        details_en=(
            "Scrolling down, the usage section details how much of "
            "each paid service was used (agents, document recognition, "
            "calls). The figures update by themselves."
        ),
    )

    await scenario.step(
        "История счетов",
        page,
        screenshot_name="billing-history",
        label_en="Invoice history",
        details=(
            "**Демонстрация результата.** Внизу таблица истории "
            "перечисляет движения и прошлые счета с датой и суммой: один "
            "взгляд отвечает на «когда мы платили».\n\n"
            "**Итог.** Полный контроль: тариф, расход и счета на одной "
            "странице, без запросов в поддержку."
        ),
        details_en=(
            "**Result demonstration.** At the bottom the history table "
            "lists past transactions and invoices with date and "
            "amount: one glance answers «when did we pay».\n\n"
            "**Summary.** Full control: plan, usage and invoices on "
            "one page, no support requests needed."
        ),
    )


@pytest.mark.scenario(
    service="frontend",
    tag="general",
    doc_slug="api-keys-create",
    title="Создать ключ API",
    title_en="Create an API key",
    description=(
        "**Для чего:** ключ API позволяет внешней программе "
        "(учётной системе, сайту, скрипту) обращаться к платформе от "
        "имени компании.\n\n"
        "**Какие проблемы решает:** технари или поставщик просят "
        "«ключ» для подключения своего ПО: здесь он создаётся и "
        "передаётся один раз.\n\n"
        "**Результат:** новый ключ с выбранными правами, секрет "
        "скопирован (показывается один раз)."
    ),
    description_en=(
        "**Purpose:** an API key lets an external program (ERP, "
        "website, script) talk to the platform on the company's "
        "behalf.\n\n"
        "**Problems solved:** the tech office or the supplier asks "
        "for «the key» to connect their software: here you generate "
        "and hand it over once.\n\n"
        "**Result:** a new key with the chosen permissions and the "
        "secret copied (shown only once)."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_frontend_api_keys_create(
    scenario: ScenarioRecorder,
    frontend_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)
    await frontend_ui.open(page)
    await page.goto(f"{frontend_ui.origin}/dashboard", wait_until="domcontentloaded")
    await expect(page.locator("platform-user button.user-button")).to_be_visible(timeout=30_000)

    await page.goto(f"{frontend_ui.origin}/api-keys", wait_until="domcontentloaded")
    keys_page = page.locator("frontend-api-keys-page")
    await expect(keys_page).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте «Ключи API»",
        page,
        screenshot_name="api-keys-page",
        label_en="Open «API keys»",
        details=(
            "Страница перечисляет активные ключи: имя, префикс, права "
            "и дата. Рамка вверху напоминает: секрет виден только при "
            "создании."
        ),
        details_en=(
            "The page lists active keys with name, prefix, scopes "
            "and date. The banner on top reminds you the secret is "
            "shown only at creation."
        ),
    )

    await (
        keys_page.locator("button.btn")
        .filter(has_text=re.compile(r"Создать|Create|Новый|New", re.I))
        .first.click()
    )
    modal = page.locator("frontend-create-api-key-modal")
    await expect(modal).to_be_visible(timeout=30_000)
    await ui_set_platform_field(modal.locator("platform-field").first, f"doc-{unique_id[:8]}")
    await modal.locator("platform-switch").first.click()
    await modal.locator(".modal-content").evaluate("el => el.scrollTop = 0")
    await scenario.step(
        "Имя и права ключа",
        page,
        screenshot_name="api-key-form",
        label_en="Key name and permissions",
        details=(
            "В окне напишите имя, по которому понятно, кто будет "
            "пользоваться (например «учётная система»), и отметьте "
            "только нужные права: чем меньше ключ умеет, тем он "
            "безопаснее."
        ),
        details_en=(
            "In the window write a name that recalls who will use "
            "it (e.g. «erp») and tick only the permissions needed: "
            "the less a key can do, the safer it is."
        ),
    )

    await modal.locator("button").filter(has_text=re.compile(r"Создать|Create", re.I)).last.click()
    banner = keys_page.locator(".secret-banner")
    await expect(banner).to_be_visible(timeout=30_000)
    await expect(banner.locator("code")).to_be_visible(timeout=30_000)
    await scenario.step(
        "Скопируйте секрет: он показывается один раз",
        page,
        screenshot_name="api-key-secret",
        label_en="Copy the secret: shown only once",
        details=(
            "**Демонстрация результата.** Зелёная рамка показывает "
            "только что созданный секрет: скопируйте и сразу передайте "
            "тому, кто будет им пользоваться. После закрытия его не "
            "восстановить — если потерян, ключ отзывается и создаётся "
            "новый.\n\n"
            "**Итог.** Внешняя программа подключена; список помнит "
            "ключ, и его можно отозвать в один клик."
        ),
        details_en=(
            "**Result demonstration.** The green banner shows the "
            "just-created secret: copy it and hand it to whoever "
            "will use it right away. After closing it can't be "
            "recovered — if lost, revoke the key and create "
            "another.\n\n"
            "**Summary.** The external program is connected; the "
            "list keeps track of the key and it can be revoked in "
            "one click."
        ),
    )


@pytest.mark.scenario(
    service="frontend",
    tag="general",
    doc_slug="scheduler-tasks",
    title="Запланированные операции",
    title_en="Scheduled operations",
    description=(
        "**Для чего:** страница «Расписания» показывает работы, "
        "которые платформа выполняет сама в заданное время "
        "(синхронизации, очистки, проверки).\n\n"
        "**Какие проблемы решает:** понять, запустилась ли "
        "автоматическая операция, стоит ли на паузе или отменена — "
        "без обращения в поддержку.\n\n"
        "**Результат:** список расписаний со статусом и действиями "
        "(пауза, запустить сейчас, отменить) на виду."
    ),
    description_en=(
        "**Purpose:** the «Schedules» page shows the jobs the "
        "platform runs by itself at fixed times (syncs, cleanups, "
        "checks).\n\n"
        "**Problems solved:** know whether an automatic operation "
        "ran, is paused or was cancelled without calling support.\n\n"
        "**Result:** the schedule list with status and actions "
        "(pause, run now, cancel) visible."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_frontend_scheduler_tasks(
    scenario: ScenarioRecorder,
    frontend_ui: AppUI,
    ui_page_system: Page,
    scheduler_client_http,
    auth_headers_system: dict[str, str],
) -> None:
    # Расписание создаётся продуктовым REST — та же op, что и кнопка «Создать»
    # в UI: строка попадает в список компании с реальным schedule_id в Redis.
    create = await scheduler_client_http.post(
        "/scheduler/api/v1/schedules",
        json={
            "target_service": "idle",
            "task_name": "calendar_sync_tick",
            "queue_name": "idle",
            "schedule_type": "cron",
            "cron": "0 6 * * *",
            "timezone": "UTC",
            "payload": {},
        },
        headers={"Host": "linnex.io", **auth_headers_system},
    )
    assert create.status_code == 200, create.text

    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)
    await frontend_ui.open(page)
    await page.goto(f"{frontend_ui.origin}/dashboard", wait_until="domcontentloaded")
    await expect(page.locator("platform-user button.user-button")).to_be_visible(timeout=30_000)

    await page.goto(f"{frontend_ui.origin}/scheduler-tasks", wait_until="domcontentloaded")
    sched = page.locator("frontend-scheduler-tasks-page")
    await expect(sched).to_be_visible(timeout=30_000)
    row = sched.locator("tr").filter(has_text="calendar_sync_tick").first
    await expect(row).to_be_visible(timeout=30_000)
    await expect(row.locator(".status-tag.pending")).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте «Расписания»",
        page,
        screenshot_name="scheduler-page",
        label_en="Open «Schedules»",
        details=(
            "Страница перечисляет запланированные операции: имя, "
            "следующий запуск и статус. Фильтры вверху сужают список "
            "по типу или статусу, когда он длинный."
        ),
        details_en=(
            "The page lists scheduled operations: name, next run "
            "and status. The filters on top narrow by type or "
            "status when the list is long."
        ),
    )

    await row.locator("button").filter(has_text=re.compile(r"Пауза|Pause", re.I)).first.click()
    await expect(row.locator(".status-tag.paused")).to_be_visible(timeout=30_000)
    await scenario.step(
        "Статус и действия каждой строки",
        page,
        screenshot_name="scheduler-actions",
        label_en="Status and actions on each row",
        details=(
            "**Демонстрация результата.** Нажали «Пауза» — статус "
            "работы сменился на «paused»: она не запустится, пока её "
            "не вернуть кнопкой «Возобновить». Рядом — «Запустить "
            "сейчас» и «Отменить».\n\n"
            "**Итог.** Автоматические операции под контролем: вы их "
            "видите и можете остановить или запустить сами."
        ),
        details_en=(
            "**Result demonstration.** Pressing «Pause» flips the "
            "job status to «paused»: it will not fire until «Resume» "
            "brings it back. Next to it are «Run now» and «Cancel».\n\n"
            "**Summary.** Automatic operations are under control: "
            "you see them, and you can stop or start them yourself."
        ),
    )


@pytest.mark.scenario(
    service="frontend",
    tag="general",
    doc_slug="embed-widget",
    title="Чат с агентом на вашем сайте",
    title_en="Agent chat on your site",
    description=(
        "**Для чего:** страница «Встраиваемые виджеты» создаёт окно чата "
        "с агентом компании, которое ставится на любой сайт одной строкой "
        "кода.\n\n"
        "**Какие проблемы решает:** посетители сайта сразу спрашивают "
        "агента — без регистрации и установки чего-либо.\n\n"
        "**Результат:** готовый фрагмент кода для вставки и виджет в "
        "общем списке."
    ),
    description_en=(
        "**Purpose:** the «Embed widgets» page creates a chat window "
        "with a company agent that goes onto any site with one line "
        "of code.\n\n"
        "**Problems solved:** site visitors ask the agent right away — "
        "no signup, nothing to install.\n\n"
        "**Result:** a ready-to-paste code snippet and the widget in "
        "the shared list."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_frontend_embed_widget(
    scenario: ScenarioRecorder,
    frontend_ui: AppUI,
    flows_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    # Агент для привязки — настоящий flow компании, созданный продуктовым REST.
    from tests.ui.e2e.flows_e2e_helpers import flows_api_create_flow, flows_llm_payload

    flow_id = f"doc_widget_agent_{unique_id[:8]}"
    await flows_api_create_flow(
        flows_ui.origin,
        auth_token_system,
        flows_llm_payload(
            flow_id,
            name="Помощник сайта",
            prompt="Отвечай посетителям сайта о компании и продуктах.",
        ),
    )

    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)
    await frontend_ui.open(page)
    _ = await page.goto(f"{frontend_ui.origin}/dashboard", wait_until="domcontentloaded")
    await expect(page.locator("platform-user button.user-button")).to_be_visible(timeout=30_000)

    _ = await page.goto(f"{frontend_ui.origin}/embed-configs", wait_until="domcontentloaded")
    widgets_page = page.locator("frontend-embed-configs-page")
    await expect(widgets_page).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте «Встраиваемые виджеты»",
        page,
        screenshot_name="embed-widgets-page",
        label_en="Open «Embed widgets»",
        details=(
            "Страница перечисляет виджеты компании: название, "
            "идентификатор, привязанный агент и статус. Кнопка "
            "«Создать виджет» открывает настройки нового окна чата."
        ),
        details_en=(
            "The page lists company widgets: name, identifier, the "
            "bound agent and status. The «Create widget» button opens "
            "the new chat window settings."
        ),
    )

    await (
        widgets_page.locator("button")
        .filter(has_text=re.compile(r"Создать виджет|Create widget", re.I))
        .first.click()
    )
    modal = page.locator("frontend-create-embed-modal")
    await expect(modal).to_be_visible(timeout=30_000)
    await ui_set_platform_field(
        modal.locator("platform-field").first, f"doc-widget-{unique_id[:8]}"
    )
    flow_field = modal.locator("platform-field[type='enum']").first
    await flow_field.locator("input").first.click()
    option = page.locator("li.enum-option").filter(has_text="Помощник сайта").first
    await expect(option).to_be_visible(timeout=30_000)
    await option.click()
    share_field = modal.locator("platform-field[type='boolean']").nth(-2)
    await share_field.locator("platform-switch").click()
    await modal.locator(".modal-content").evaluate("el => el.scrollTop = 0")
    await scenario.step(
        "Имя, агент и тумблеры виджета",
        page,
        screenshot_name="embed-widget-form",
        label_en="Widget name, agent and toggles",
        details=(
            "В окне напишите понятное название (например «чат на "
            "сайте») и выберите агента, который будет отвечать "
            "посетителям. Тумблеры ниже включают голос и сохранение "
            "диалога для посетителя — включайте только нужное."
        ),
        details_en=(
            "In the window write a clear name (e.g. «site chat») "
            "and pick the agent that will answer visitors. The "
            "toggles below enable voice and conversation restore "
            "for the visitor — turn on only what you need."
        ),
    )

    await modal.locator("button.btn-primary").click()
    row = widgets_page.locator("tr").filter(has_text=f"doc-widget-{unique_id[:8]}").first
    await expect(row).to_be_visible(timeout=30_000)
    await (
        row.locator("button")
        .filter(has_text=re.compile(r"Получить код|Get code", re.I))
        .first.click()
    )
    code_modal = page.locator("frontend-embed-code-modal")
    await expect(code_modal).to_be_visible(timeout=30_000)
    await expect(code_modal.locator("pre").first).to_be_visible(timeout=30_000)
    await scenario.step(
        "Вставьте код на сайт",
        page,
        screenshot_name="embed-widget-code",
        label_en="Paste the code into your site",
        details=(
            "**Демонстрация результата.** Виджет создан и появился в "
            "списке, а кнопка «Получить код» показывает готовый "
            "фрагмент: скопируйте его и отдайте тому, кто занимается "
            "сайтом — чат с агентом появится в углу страницы.\n\n"
            "**Итог.** Посетители сайта говорят с вашим агентом; "
            "виджет можно изменить или удалить в этом же списке."
        ),
        details_en=(
            "**Result demonstration.** The widget is created and "
            "listed, and «Get code» shows a ready snippet: copy it "
            "and hand it to whoever maintains the site — the agent "
            "chat appears in the page corner.\n\n"
            "**Summary.** Site visitors talk to your agent; the "
            "widget can be edited or deleted right in this list."
        ),
    )
