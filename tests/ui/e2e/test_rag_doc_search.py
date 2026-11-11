"""Документационные сценарии RAG: загрузка документов и умный поиск.

L2-маршруты поверх getting-started: отдельно показываем карточку
документа со статусом индексации (число страниц) и страницу поиска
с оценкой совпадения и фрагментом текста.
"""

from __future__ import annotations

import pytest
from playwright.async_api import Page, ViewportSize, expect

from tests.ui.harness import AppUI, ui_set_platform_field
from tests.ui.scenario_doc import ScenarioRecorder

_DESKTOP = ViewportSize(width=1440, height=900)

_DOC_TEXT = (
    "Регламент доставки. Самовывоз со склада — будни 10:00–19:00. "
    "Курьерская доставка по городу — в день заказа при оформлении до 15:00. "
    "Хрупкий товар дополнительно обматываем пупырчатой плёнкой."
)


async def _rag_nav(page: Page, index: int, *, page_selector: str) -> None:
    item = page.locator("rag-sidebar .nav-item").nth(index)
    await expect(item).to_be_visible(timeout=10_000)
    await item.click()
    await expect(page.locator(page_selector)).to_be_visible(timeout=15_000)


async def _rag_create_namespace(page: Page, name: str) -> None:
    """Создаёт пространство через модалку и открывает его карточку."""
    await expect(page.locator("rag-namespaces-page")).to_be_visible(timeout=30_000)
    await page.locator(
        "rag-namespaces-page page-header .btn-primary"
    ).first.click()
    modal = page.locator("rag-namespace-create-modal")
    await expect(modal).to_be_visible(timeout=15_000)
    await ui_set_platform_field(
        modal.locator("platform-field[type='string']").first, name
    )
    create_btn = modal.locator(".footer-actions .btn-primary")
    await expect(create_btn).to_be_enabled(timeout=10_000)
    await create_btn.click()
    await expect(modal).to_be_hidden(timeout=30_000)

    card = page.locator("namespace-card", has_text=name).first
    await expect(card).to_be_visible(timeout=15_000)
    await card.evaluate("(el) => el.shadowRoot.querySelector('.card').click()")
    await expect(page.locator("rag-namespace-page")).to_be_visible(timeout=15_000)


async def _rag_upload(page: Page, tmp_path, filename: str = "reglament.txt") -> None:
    doc_path = tmp_path / filename
    doc_path.write_text(_DOC_TEXT, encoding="utf-8")
    await page.locator("rag-namespace-page input[type=file]").set_input_files(
        str(doc_path)
    )
    await expect(
        page.locator("rag-namespace-page .document-card")
    ).to_be_visible(timeout=60_000)


@pytest.mark.scenario(
    service="rag",
    tag="documents",
    doc_slug="upload-and-index-documents",
    title="Загружаем документ и ждём, пока он проиндексируется",
    title_en="Upload a document and wait for it to be indexed",
    description=(
        "**Для чего:** добавить файл в пространство знаний и понять, "
        "когда поиск по нему уже работает.\n\n"
        "**Какие проблемы решает:** после загрузки непонятно, готов ли "
        "документ к умному поиску. Здесь показано, где смотреть статус.\n\n"
        "**Результат:** карточка документа показывает статус "
        "«Проиндексирован» — файл участвует в поиске."
    ),
    description_en=(
        "**Purpose:** add a file to a knowledge space and see when "
        "search over it is ready.\n\n"
        "**Problems solved:** after upload it is unclear whether the "
        "document is indexed. Here is where to check the status.\n\n"
        "**Result:** the document card shows «Indexed» status — the "
        "file is searchable."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_rag_upload_and_index(
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

    namespace_name = f"kb-{unique_id[:6]}"
    await _rag_create_namespace(page, namespace_name)
    await _rag_upload(page, tmp_path)

    # Статус «Проиндексирован» появляется после завершения индексации.
    doc_status = page.locator("rag-namespace-page .doc-status").first
    await expect(doc_status).to_contain_text("Indexed", timeout=90_000)
    await scenario.step(
        "Дождитесь индексации документа",
        page,
        screenshot_name="document-indexed",
        label_en="Wait for the document to be indexed",
        details=(
            "Откройте пространство и загрузите файл кнопкой «Загрузить» "
            "или перетащите его в пунктирную зону. Под именем файла "
            "появится статус: сначала «Индексируется…», затем "
            "«Проиндексирован» — с этого момента документ участвует "
            "в поиске."
        ),
        details_en=(
            "Open the space and upload a file with the «Upload» button "
            "or drag it into the dashed zone. Under the file name a "
            "status appears: first «Indexing…», then «Indexed» — from "
            "that moment the document is searchable."
        ),
    )

    remove_btn = page.locator("rag-namespace-page .document-actions .btn-icon")
    await scenario.step(
        "При необходимости удалите документ",
        page,
        screenshot_name="document-card-actions",
        label_en="Delete the document if needed",
        details=(
            "У каждой карточки есть кнопка корзины справа: она убирает "
            "документ из пространства и из поиска. Нажимать её сейчас не "
            "нужно — просто знайте, где она.\n\n"
            "**Итог.** Вы умеете загружать файлы и понимать по статусу "
            "«Проиндексирован», что документ готов к поиску."
        ),
        details_en=(
            "Each card has a trash button on the right: it removes the "
            "document from the space and from search. No need to click "
            "it now — just know where it is.\n\n"
            "**Summary.** You can upload files and tell from the "
            "«Indexed» status that a document is ready for search."
        ),
    )
    await expect(remove_btn).to_be_visible(timeout=10_000)


@pytest.mark.scenario(
    service="rag",
    tag="search",
    doc_slug="semantic-search-demo",
    title="Ищем документ по смыслу: оценка совпадения и фрагмент",
    title_en="Find a document by meaning: match score and excerpt",
    description=(
        "**Для чего:** найти нужное в документах обычной фразой и "
        "понять, насколько результат подходит.\n\n"
        "**Какие проблемы решает:** точные слова из документа не "
        "вспомнить. Поиск по смыслу находит нужный фрагмент и честно "
        "показывает процент совпадения.\n\n"
        "**Результат:** карточка результата с процентом совпадения и "
        "фрагментом текста документа."
    ),
    description_en=(
        "**Purpose:** find things in documents with a plain phrase and "
        "see how well each result fits.\n\n"
        "**Problems solved:** you rarely remember the exact wording. "
        "Semantic search finds the right passage and honestly shows a "
        "match percentage.\n\n"
        "**Result:** a result card with a match percentage and the "
        "document excerpt."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_rag_semantic_search(
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

    namespace_name = f"kb-{unique_id[:6]}"
    await _rag_create_namespace(page, namespace_name)
    await _rag_upload(page, tmp_path)
    # Дождаться индексации — иначе поиск ещё ничего не вернёт.
    await expect(
        page.locator("rag-namespace-page .doc-status").first
    ).to_contain_text("Indexed", timeout=90_000)

    await _rag_nav(page, 1, page_selector="rag-search-page")
    await ui_set_platform_field(
        page.locator("rag-search-page platform-field").first,
        namespace_name,
    )
    await ui_set_platform_field(
        page.locator("rag-search-page .query-field"),
        "как упаковывают бьющийся товар",
    )
    await scenario.step(
        "Задайте вопрос своими словами",
        page,
        screenshot_name="search-query",
        label_en="Ask in your own words",
        details=(
            "Откройте «Поиск» в меню слева, выберите пространство и "
            "напишите вопрос как спросили бы коллегу — например, «как "
            "упаковывают бьющийся товар». Точных слов «пупырчатая плёнка» "
            "в запросе нет — умный поиск ищет по смыслу."
        ),
        details_en=(
            "Open «Search» in the left menu, pick the space and type "
            "the question as you would ask a colleague — e.g. «how do "
            "they pack fragile goods». The exact words «bubble wrap» "
            "are not in the query — semantic search works by meaning."
        ),
    )

    result_card = page.locator("rag-search-page .result-card").first
    for _ in range(30):
        await page.locator("rag-search-page .search-btn").click()
        try:
            await expect(result_card).to_be_visible(timeout=5_000)
            break
        except AssertionError:
            continue
    await expect(result_card).to_be_visible(timeout=10_000)
    await expect(result_card.locator(".result-score")).to_contain_text("%")
    await expect(result_card.locator(".result-content")).to_contain_text(
        "пупырчатой"
    )
    await scenario.step(
        "Прочитайте оценку и фрагмент",
        page,
        screenshot_name="search-result",
        label_en="Read the score and the excerpt",
        details=(
            "**Демонстрация результата.** Каждая карточка показывает "
            "процент совпадения — насколько фрагмент подходит к вопросу — "
            "и сам фрагмент из документа. По проценту видно, стоит ли "
            "открывать файл целиком.\n\n"
            "**Итог.** Поиск по смыслу находит нужное даже без точных "
            "слов, а оценка подсказывает, какому результату доверять."
        ),
        details_en=(
            "**Result demonstration.** Each card shows a match "
            "percentage — how well the passage fits the question — and "
            "the document excerpt itself. The percentage tells you "
            "whether it is worth opening the file.\n\n"
            "**Summary.** Meaning-based search finds things without "
            "exact words, and the score tells you which result to trust."
        ),
    )
