"""Документационные сценарии CRM: заметки и AI-предложения.

Маршруты пользователя: дневник заметок и очередь фоновых
AI-предложений пространства.
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime

import httpx2
import pytest
from playwright.async_api import Page, ViewportSize, expect

from apps.crm.tasks.task_names import CRM_GENERATE_NAMESPACE_SUGGESTS
from core.tasks import enqueue
from tests.ui.e2e.crm_activity_tasks_helpers import (
    crm_api_create_entity,
    crm_api_ensure_entity_type,
    crm_api_ensure_namespace,
    crm_api_list_suggests,
    crm_api_origin,
)
from tests.ui.e2e.sync_e2e_helpers import sync_e2e_activate_namespace_for_next_load
from tests.ui.e2e_worker import ui_e2e_company_id, ui_e2e_scope_headers
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

_DESKTOP = ViewportSize(width=1440, height=900)


@pytest.mark.scenario(
    service="crm",
    tag="notes",
    doc_slug="daily-notes",
    title="Ежедневные заметки: дневник рабочего дня",
    title_en="Daily notes: working day diary",
    description=(
        "**Для чего:** фиксировать итоги дня — звонки, договорённости, "
        "мысли — пока они свежие, и находить их потом по дате.\n\n"
        "**Какие проблемы решает:** договорённости теряются в чатах и "
        "голове. Заметка за день занимает минуту, а потом легко "
        "вспомнить, что и когда обсуждали.\n\n"
        "**Результат:** заметка сохранена и лежит в ленте за свою дату — "
        "к ней можно вернуться и привязать к записям."
    ),
    description_en=(
        "**Purpose:** capture the day's outcomes — calls, agreements, "
        "thoughts — while fresh, and find them later by date.\n\n"
        "**Problems solved:** agreements get lost in chats and memory. A "
        "daily note takes a minute, then it is easy to recall what was "
        "discussed and when.\n\n"
        "**Result:** the note is saved in the feed under its date — you "
        "can come back and link it to records."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120, func_only=True)
async def test_crm_daily_notes(
    crm_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
    scenario: ScenarioRecorder,
) -> None:
    page = ui_page_system
    note_text = f"Созвон с поставщиком {unique_id[:4]}: договорились о скидке 10%."

    await crm_ui.open(page)
    await page.set_viewport_size(_DESKTOP)

    await page.goto(f"{crm_ui.origin}/crm/notes", wait_until="domcontentloaded")
    notes_page = page.locator("crm-daily-notes-page")
    await expect(notes_page).to_be_visible(timeout=60_000)
    await scenario.step(
        "Дневник заметок",
        page,
        screenshot_name="notes-feed",
        label_en="Notes diary",
        details=(
            "Раздел «Заметки» — лента записей по дням. Сверху — выбор "
            "периода и диктовка голосом, кнопка «Добавить заметку» "
            "открывает редактор."
        ),
        details_en=(
            "The Notes section is a feed of entries by day. On top — a "
            "period picker and voice dictation; the Add note button "
            "opens the editor."
        ),
    )

    create_btn = notes_page.locator(".cta-btn").first
    await expect(create_btn).to_be_visible(timeout=15_000)
    await create_btn.click()

    note_page = page.locator("crm-note-page")
    await expect(note_page).to_be_visible(timeout=30_000)
    editor = note_page.locator("platform-markdown-editor")
    await expect(editor).to_be_visible(timeout=30_000)
    await editor.locator("[contenteditable], textarea, .pm-editor").first.click()
    await page.keyboard.type(note_text)
    await scenario.step(
        "Пишем заметку",
        page,
        screenshot_name="note-editor",
        label_en="Writing a note",
        details=(
            "Редактор поддерживает разметку: заголовки, списки, ссылки на "
            "записи через «@». Пишите как в обычном блокноте — что "
            "обсуждали, о чём договорились, что сделать завтра."
        ),
        details_en=(
            "The editor supports markup: headings, lists, record links "
            "via @. Write like in a regular notepad — what was "
            "discussed, what was agreed, what to do tomorrow."
        ),
    )

    save_btn = note_page.locator("button.pill-btn").last
    await expect(save_btn).to_be_enabled(timeout=10_000)
    await save_btn.click()
    await expect(
        note_page.get_by_text(note_text, exact=False)
    ).to_be_visible(timeout=30_000)
    await scenario.step(
        "Заметка сохранена",
        page,
        screenshot_name="note-saved",
        label_en="Note saved",
        details=(
            "После сохранения заметка открывается в режиме чтения — "
            "дата проставлена автоматически. Ниже можно привязать её к "
            "записям клиентов и сделок."
        ),
        details_en=(
            "After saving the note opens in read mode — the date is set "
            "automatically. Below you can link it to customer and deal "
            "records."
        ),
    )

    await page.goto(f"{crm_ui.origin}/crm/notes", wait_until="domcontentloaded")
    await expect(notes_page).to_be_visible(timeout=60_000)
    await expect(
        notes_page.get_by_text(note_text, exact=False)
    ).to_be_visible(timeout=30_000)
    await scenario.step(
        "Заметка в ленте",
        page,
        screenshot_name="note-in-feed",
        label_en="Note in the feed",
        details=(
            "Заметка появилась в ленте под своей датой. Дальше её можно "
            "дополнить, привязать к клиенту или попросить платформу "
            "разобрать её на записи."
        ),
        details_en=(
            "The note appeared in the feed under its date. You can amend "
            "it, link it to a customer, or ask the platform to break it "
            "down into records."
        ),
    )


@pytest.mark.scenario(
    service="crm",
    tag="entities",
    doc_slug="suggests-quick-add",
    title="AI-предложения: применить разбор заметки одной кнопкой",
    title_en="AI suggestions: apply a note breakdown in one click",
    description=(
        "**Для чего:** платформа сама разбирает заметки на записи и "
        "дубли — остаётся только подтвердить.\n\n"
        "**Какие проблемы решает:** после анализа заметки её черновик "
        "может остаться неприменённым — записи не появятся в картотеке. "
        "Очередь AI-предложений показывает такие случаи и позволяет "
        "применить или скрыть каждый.\n\n"
        "**Результат:** черновик применён — записи из заметки появились "
        "в картотеке, а предложение закрылось."
    ),
    description_en=(
        "**Purpose:** the platform breaks notes into records and "
        "catches duplicates on its own — you only confirm.\n\n"
        "**Problems solved:** after a note analysis its draft may stay "
        "unapplied — records never reach the card index. The AI "
        "suggestions queue surfaces these cases and lets you apply or "
        "dismiss each.\n\n"
        "**Result:** the draft is applied — records from the note "
        "appear in the card index, and the suggestion is closed."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240, func_only=True)
async def test_crm_suggests_quick_add_scenario(
    scenario: ScenarioRecorder,
    crm_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    page = ui_page_system
    namespace = f"s_{unique_id}"
    note_name = f"Заметка о встрече {unique_id[:6]}"
    contact_name = f"Пётр Сидоров {unique_id[:6]}"

    await crm_api_ensure_namespace(crm_ui.origin, auth_token_system, namespace=namespace)
    await crm_api_ensure_entity_type(
        crm_ui.origin,
        auth_token_system,
        type_id="contact",
        name="Контакт",
        namespace=namespace,
    )
    await crm_api_create_entity(
        crm_ui.origin, auth_token_system,
        entity_type="note", name=note_name, namespace=namespace,
        attributes={
            "ai_analysis_draft": {
                "draft_version": 1,
                "updated_at": datetime.now(UTC).isoformat(),
                "entities": [
                    {
                        "draft_entity_id": "d1",
                        "entity_type": "contact",
                        "name": contact_name,
                    }
                ],
                "relationships": [],
            }
        },
    )

    await enqueue(
        CRM_GENERATE_NAMESPACE_SUGGESTS,
        company_id=ui_e2e_company_id(),
        namespace=namespace,
        background_kind="background",
    )
    deadline = asyncio.get_event_loop().time() + 120
    pending: list[dict] = []
    while asyncio.get_event_loop().time() < deadline:
        pending = [
            item
            for item in await crm_api_list_suggests(
                crm_ui.origin,
                auth_token_system,
                namespace=namespace,
                status="pending",
            )
            if item.get("suggest_type") == "missed_entity"
        ]
        if pending:
            break
        await asyncio.sleep(2)
    if not pending:
        raise AssertionError("missed_entity suggest was not generated")

    await sync_e2e_activate_namespace_for_next_load(page, namespace)
    await crm_ui.open(page)
    await page.set_viewport_size(_DESKTOP)
    await page.goto(f"{crm_ui.origin}/crm/suggests", wait_until="domcontentloaded")
    suggests_page = page.locator("crm-suggests-page")
    await expect(suggests_page).to_be_visible(timeout=60_000)
    await expect(
        suggests_page.get_by_text(
            re.compile("Неприменённый AI-черновик|Unapplied AI draft")
        ).first
    ).to_be_visible(timeout=60_000)
    await scenario.step(
        "Очередь AI-предложений",
        page,
        screenshot_name="suggests-queue",
        label_en="AI suggestions queue",
        details=(
            "Раздел «AI-предложения» собирает фоновые находки платформы: "
            "неприменённые черновики разбора заметок и возможные дубли "
            "записей. У каждого предложения — две кнопки: «Применить» "
            "и «Скрыть»."
        ),
        details_en=(
            "The AI suggestions section collects the platform's "
            "background findings: unapplied note-analysis drafts and "
            "possible record duplicates. Each suggestion has two "
            "buttons: Apply and Dismiss."
        ),
    )

    resolve_button = suggests_page.get_by_role(
        "button", name=re.compile("^Применить$|^Apply$")
    ).first
    await expect(resolve_button).to_be_visible(timeout=30_000)
    await resolve_button.click()
    confirm = page.locator("platform-confirm-modal")
    await expect(confirm).to_be_visible(timeout=30_000)
    await scenario.step(
        "Подтверждение применения",
        page,
        screenshot_name="suggest-resolve-confirm",
        label_en="Apply confirmation",
        details=(
            "Перед применением платформа показывает, что именно будет "
            "сделано: черновик заметки развернётся в записи картотеки."
        ),
        details_en=(
            "Before applying, the platform shows exactly what will "
            "happen: the note draft unfolds into card-index records."
        ),
    )
    confirm_button = confirm.get_by_role(
        "button", name=re.compile("^Применить$|^Apply$")
    )
    await expect(confirm_button).to_be_visible(timeout=10_000)
    await confirm_button.click()

    deadline = asyncio.get_event_loop().time() + 60
    resolved = False
    while asyncio.get_event_loop().time() < deadline:
        resolved_items = [
            item
            for item in await crm_api_list_suggests(
                crm_ui.origin,
                auth_token_system,
                namespace=namespace,
                status="resolved",
            )
            if item.get("suggest_type") == "missed_entity"
        ]
        if resolved_items:
            resolved = True
            break
        await asyncio.sleep(2)
    if not resolved:
        raise AssertionError("missed_entity suggest was not resolved")

    await page.goto(
        f"{crm_ui.origin}/crm/entities", wait_until="domcontentloaded"
    )
    entities_page = page.locator("crm-entities-page")
    await expect(entities_page).to_be_visible(timeout=60_000)
    await expect(
        entities_page.get_by_text(contact_name, exact=False).first
    ).to_be_visible(timeout=60_000)
    await scenario.step(
        "Записи из черновика в картотеке",
        page,
        screenshot_name="suggest-applied-entity",
        label_en="Draft records in the card index",
        details=(
            f"Черновик применён: запись «{contact_name}» появилась в "
            "картотеке как полноценный объект — её можно открыть, "
            "связать и вести по ней задачи.\n\n"
            "**Итог.** AI-предложения превращают заметки в живую "
            "картотеку одним подтверждением."
        ),
        details_en=(
            f"The draft is applied: the record {contact_name} appeared "
            "in the card index as a first-class object — you can open "
            "it, link it and track tasks against it.\n\n"
            "**Summary.** AI suggestions turn notes into a live card "
            "index with a single confirmation."
        ),
    )


@pytest.mark.scenario(
    service="crm",
    tag="notes",
    doc_slug="ai-note-analysis",
    title="AI-разбор заметки: записи и связи из текста",
    title_en="AI note analysis: records and links from text",
    description=(
        "**Для чего:** написать заметку свободным текстом, а записи "
        "картотеки получить готовыми — AI сам находит людей, компании "
        "и связи между ними.\n\n"
        "**Какие проблемы решает:** после встречи лень заводить "
        "карточки руками — договорённости оседают в тексте и "
        "теряются. AI-разбор предлагает готовый список записей: "
        "проверил — применил одним кликом.\n\n"
        "**Результат:** из заметки созданы записи и связи, заметка "
        "получила AI-резюме."
    ),
    description_en=(
        "**Purpose:** write a note in free text and get ready-made "
        "card-index records — AI finds people, companies and links "
        "between them.\n\n"
        "**Problems solved:** after a meeting nobody wants to file "
        "cards by hand — agreements sink into text and get lost. AI "
        "analysis proposes a ready record list: review it, apply in "
        "one click.\n\n"
        "**Result:** records and links were created from the note, "
        "and the note got an AI summary."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180, func_only=True)
async def test_crm_ai_note_analysis_scenario(
    scenario: ScenarioRecorder,
    crm_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    import json as _json

    from core.clients.llm.mock import setup_mock_responses_redis
    from core.clients.redis_client import RedisClient
    from core.config import get_settings
    from core.test_scope import TEST_SCOPE_STATIC_E2E

    page = ui_page_system
    namespace = f"e_{unique_id}"
    note_title = f"Встреча с «Альфа-Логистик» {unique_id[:6]}"
    contact_name = f"Антон Верников {unique_id[:6]}"

    await crm_api_ensure_namespace(crm_ui.origin, auth_token_system, namespace=namespace)
    note_id = await crm_api_create_entity(
        crm_ui.origin,
        auth_token_system,
        entity_type="note",
        name=note_title,
        namespace=namespace,
        attributes={},
    )
    # Текст заметки — то, что разберёт AI.
    description = (
        "Встретились с Антоном Верниковым из «Альфа-Логистик». "
        "Обсудили поставку в марте: он подтвердил скидку 12% и прислал "
        "спецификацию. Договорились созвониться в пятницу."
    )
    async with httpx2.AsyncClient(
        base_url=crm_api_origin(crm_ui.origin),
        cookies={"auth_token": auth_token_system},
        headers=ui_e2e_scope_headers(),
        timeout=60.0,
    ) as client:
        upd = await client.put(
            f"/crm/api/v1/entities/{note_id}", json={"description": description}
        )
        if upd.status_code != 200:
            raise AssertionError(f"PUT note failed: {upd.status_code} {upd.text}")

    ai_payload = _json.dumps({
        "note": {
            "entity_type": "note",
            "name": note_title,
            "description": "Встреча с поставщиком: скидка 12%, спецификация, созвон в пятницу.",
            "attributes": {},
            "confidence": 0.92,
        },
        "entities": [
            {
                "entity_type": "contact",
                "name": contact_name,
                "description": "Менеджер «Альфа-Логистик» по оптовым поставкам",
                "attributes": {"role": "менеджер"},
                "confidence": 0.9,
            },
            {
                "entity_type": "organization",
                "name": f"Альфа-Логистик {unique_id[:6]}",
                "description": "Поставщик логистических услуг",
                "attributes": {},
                "confidence": 0.88,
            },
        ],
        "relationships": [
            {
                "source_type": "note",
                "source_name": note_title,
                "target_type": "contact",
                "target_name": contact_name,
                "relationship_type": "mentions",
                "weight": 1.0,
                "confidence": 0.9,
            },
            {
                "source_type": "contact",
                "source_name": contact_name,
                "target_type": "organization",
                "target_name": f"Альфа-Логистик {unique_id[:6]}",
                "relationship_type": "belongs_to",
                "weight": 1.0,
                "confidence": 0.9,
            },
        ],
        "metadata": {"dates_mentioned": [], "places_mentioned": [], "key_topics": ["поставка", "скидка"]},
        "attachment_summaries": [],
    })
    # Клик по кнопке анализа идёт WS-командой без X-Test-Scope — MockLLM воркера
    # читает очередь дефолтного scope `test_e2e_static` (core/test_scope.py).
    redis_client = RedisClient(get_settings().database.redis_url)
    try:
        await setup_mock_responses_redis(
            redis_client,
            [{"type": "text", "content": ai_payload}] * 6,
            test_scope=TEST_SCOPE_STATIC_E2E,
        )
    finally:
        await redis_client.close()

    await sync_e2e_activate_namespace_for_next_load(page, namespace)
    await crm_ui.open(page)
    await page.set_viewport_size(_DESKTOP)
    await page.goto(
        f"{crm_ui.origin}/crm/notes/{note_id}", wait_until="domcontentloaded"
    )
    note_page = page.locator("crm-note-page")
    await expect(note_page).to_be_visible(timeout=60_000)
    await expect(
        note_page.get_by_text(note_title, exact=False).first
    ).to_be_visible(timeout=60_000)
    await scenario.step(
        "Заметка после встречи",
        page,
        screenshot_name="note-page",
        label_en="Note after meeting",
        details=(
            "Заметка записана обычным текстом — без форм и карточек. "
            "Рядом с резюме — круглая кнопка обновления: она запускает "
            "AI-разбор текста."
        ),
        details_en=(
            "The note is written in plain text — no forms or cards. "
            "Next to the summary sits a round refresh button: it "
            "starts the AI analysis of the text."
        ),
    )

    refresh = note_page.locator(".summary-card .round-btn")
    await expect(refresh).to_be_visible(timeout=30_000)
    await refresh.click()
    analysis_modal = page.locator("crm-ai-analysis-modal")
    await expect(analysis_modal).to_be_visible(timeout=120_000)
    await expect(
        analysis_modal.get_by_text(contact_name, exact=False).first
    ).to_be_visible(timeout=60_000)
    await scenario.step(
        "AI нашёл записи и связи",
        page,
        screenshot_name="ai-analysis-modal",
        label_en="AI found records and links",
        details=(
            "AI-разбор показывает, что он понял из текста: резюме "
            "заметки, предложенные записи (контакт, компания) и связи "
            "между ними. Каждую строку можно поправить прямо здесь, "
            "прежде чем записи попадут в картотеку."
        ),
        details_en=(
            "AI analysis shows what it understood from the text: a "
            "note summary, suggested records (contact, company) and "
            "links between them. Each row can be edited right here "
            "before the records reach the card index."
        ),
    )

    apply_btn = analysis_modal.get_by_role(
        "button", name=re.compile("Применить|Apply")
    )
    await expect(apply_btn).to_be_visible(timeout=30_000)
    await apply_btn.click()
    await expect(
        analysis_modal.get_by_text(
            re.compile("Применено|Applied", re.I), exact=False
        ).first
    ).to_be_visible(timeout=60_000)

    await page.goto(
        f"{crm_ui.origin}/crm/entities", wait_until="domcontentloaded"
    )
    entities_page = page.locator("crm-entities-page")
    await expect(entities_page).to_be_visible(timeout=60_000)
    await expect(
        entities_page.get_by_text(contact_name, exact=False).first
    ).to_be_visible(timeout=60_000)
    await scenario.step(
        "Записи в картотеке",
        page,
        screenshot_name="ai-created-entity",
        label_en="Records in the card index",
        details=(
            f"«{contact_name}» уже в картотеке — вместе с компанией "
            "и связью к заметке. AI сделал черновую работу, вы только "
            "проверили.\n\n"
            "**Итог.** Пишите заметки как удобно — картотека "
            "заполнится сама."
        ),
        details_en=(
            f"{contact_name} is already in the card index — with the "
            "company and a link to the note. AI did the rough work, "
            "you only reviewed it.\n\n"
            "**Summary.** Write notes the way you like — the card "
            "index fills itself in."
        ),
    )
