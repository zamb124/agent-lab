"""Документационный сценарий RAG: первое пространство знаний.

Маршрут пользователя: создать пространство, загрузить документ и найти его
семантическим поиском. Поиск повторяется, пока индексация не даст первый
результат — это и есть демонстрация готовности.
"""

from __future__ import annotations

import pytest
from playwright.async_api import Page, ViewportSize, expect

from tests.ui.harness import AppUI, ui_set_platform_field
from tests.ui.scenario_doc import ScenarioRecorder

_DESKTOP = ViewportSize(width=1440, height=900)

_DOC_TEXT = (
    "Устав кофейни «Зерно». График работы: будни 8:00–21:00, "
    "выходные 9:00–22:00. Дресс-код бариста — фартук цвета тёмной обжарки. "
    "Секретный ингредиент фирменного рафа — щепотка морской соли."
)


async def _rag_nav(page: Page, index: int, *, page_selector: str) -> None:
    item = page.locator("rag-sidebar .nav-item").nth(index)
    await expect(item).to_be_visible(timeout=10_000)
    await item.click()
    await expect(page.locator(page_selector)).to_be_visible(timeout=15_000)


@pytest.mark.scenario(
    service="rag",
    tag="getting-started",
    doc_slug="rag-first-namespace",
    title="Первое пространство знаний: загрузка и умный поиск",
    title_en="First knowledge space: upload and smart search",
    description=(
        "**Для чего:** научить платформу отвечать по вашим документам — "
        "создать пространство знаний, загрузить файл и найти нужное "
        "по смыслу, а не по точным словам.\n\n"
        "**Какие проблемы решает:** документы разбросаны и ничего не "
        "найти. Здесь вы увидите, как за пару минут собрать базу знаний "
        "и задать ей вопрос обычной фразой.\n\n"
        "**Результат:** загруженный документ найден поиском по смыслу — "
        "запрос без точных слов из текста выдаёт нужную карточку."
    ),
    description_en=(
        "**Purpose:** teach the platform to answer from your documents — "
        "create a knowledge space, upload a file, and find it by meaning "
        "rather than exact words.\n\n"
        "**Problems solved:** scattered documents are hard to find. Here "
        "you will see how to build a knowledge base in minutes and ask it "
        "a question in plain words.\n\n"
        "**Result:** the uploaded document is found by semantic search — "
        "a query without the exact words still returns the right card."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_rag_first_namespace(
    scenario: ScenarioRecorder,
    rag_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
    tmp_path,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)
    await rag_ui.open(page)
    await rag_ui.expect_shell(page)

    namespace_name = f"База знаний {unique_id[:4]}"
    await expect(page.locator("rag-namespaces-page")).to_be_visible(timeout=30_000)
    await page.locator(
        "rag-namespaces-page page-header .btn-primary"
    ).first.click()
    modal = page.locator("rag-namespace-create-modal")
    await expect(modal).to_be_visible(timeout=15_000)
    await ui_set_platform_field(
        modal.locator("platform-field[type='string']").first, namespace_name
    )
    await modal.locator(".footer-actions .btn-primary").click()
    await expect(modal).to_be_hidden(timeout=30_000)
    await scenario.step(
        "Создайте пространство знаний",
        page,
        screenshot_name="namespace-created",
        label_en="Create a knowledge space",
        details=(
            "На странице «Пространства» нажмите «Создать» и дайте "
            "пространству понятное имя — например, «База знаний». "
            "Пространство — это отдельная полка для документов: уставы "
            "отдельно, инструкции отдельно."
        ),
        details_en=(
            "On the «Namespaces» page click «Create» and give the space a "
            "clear name — e.g. «Knowledge base». A namespace is a separate "
            "shelf for documents: charters here, manuals there."
        ),
    )

    card = page.locator("namespace-card", has_text=namespace_name).first
    await expect(card).to_be_visible(timeout=15_000)
    await card.click()
    await expect(page.locator("rag-namespace-page")).to_be_visible(timeout=15_000)

    doc_path = tmp_path / "ustav.txt"
    doc_path.write_text(_DOC_TEXT, encoding="utf-8")
    await page.locator("rag-namespace-page input[type=file]").set_input_files(
        str(doc_path)
    )
    await expect(
        page.locator("rag-namespace-page .document-card")
    ).to_be_visible(timeout=60_000)
    await scenario.step(
        "Загрузите документ в пространство",
        page,
        screenshot_name="document-uploaded",
        label_en="Upload a document into the space",
        details=(
            "Откройте пространство и нажмите «Загрузить» — или просто "
            "перетащите файл в окно. Документ появится в списке: система "
            "сразу начинает его индексировать — разбирать по смыслу для "
            "умного поиска."
        ),
        details_en=(
            "Open the space and click «Upload» — or simply drag the file "
            "into the window. The document appears in the list: the system "
            "starts indexing it right away — parsing it by meaning for "
            "smart search."
        ),
    )

    await _rag_nav(page, 1, page_selector="rag-search-page")
    await ui_set_platform_field(
        page.locator("rag-search-page platform-field").first,
        namespace_name,
    )
    await ui_set_platform_field(
        page.locator("rag-search-page .query-field"),
        "во сколько открывается кофейня в субботу",
    )
    # Индексация занимает время — повторяем поиск до первого результата.
    result_card = page.locator("rag-search-page .result-card").first
    for _ in range(30):
        await page.locator("rag-search-page .search-btn").click()
        try:
            await expect(result_card).to_be_visible(timeout=5_000)
            break
        except AssertionError:
            continue
    await expect(result_card).to_be_visible(timeout=10_000)
    await scenario.step(
        "Спросите поиск своими словами",
        page,
        screenshot_name="search-result",
        label_en="Ask search in your own words",
        details=(
            "**Демонстрация результата.** Откройте «Поиск», выберите "
            "пространство и напишите вопрос как спросили бы коллегу: «во "
            "сколько открывается кофейня в субботу». Точных слов «выходные "
            "9:00–22:00» в запросе нет — но поиск нашёл их в документе и "
            "выдал карточку с оценкой совпадения.\n\n"
            "**Итог.** Вы собрали пространство знаний: создали полку, "
            "загрузили документ и убедились, что умный поиск находит "
            "нужное по смыслу."
        ),
        details_en=(
            "**Result demonstration.** Open «Search», pick the space and "
            "write the question as you would ask a colleague: «when does "
            "the coffee shop open on Saturday». The exact words «weekends "
            "9:00–22:00» are not in the query — yet search found them in "
            "the document and returned a card with a match score.\n\n"
            "**Summary.** You built a knowledge space: created a shelf, "
            "uploaded a document and confirmed smart search finds things "
            "by meaning."
        ),
    )
