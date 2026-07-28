"""E2E: работа со страницами базы знаний."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.wiki_e2e_helpers import (
    wiki_api_create_page,
    wiki_e2e_open_page,
    wiki_e2e_open_with_namespace,
    wiki_e2e_set_locale_ru,
    wiki_e2e_title_input,
    wiki_e2e_tree_row,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="wiki",
    tag="pages",
    doc_slug="create-and-edit-page",
    title="Wiki: создание и правка страницы",
    title_en="Wiki: create and edit a page",
    description="Создание страницы из сайдбара, ввод заголовка и текста, автосохранение.",
    description_en="Creating a page from the sidebar, typing a title and body, autosave.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(90)
async def test_wiki_create_and_edit_page(
    scenario: ScenarioRecorder,
    wiki_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    _ = await wiki_e2e_open_with_namespace(wiki_ui, page, unique_id, suffix="edit")
    await scenario.step("Открыта база знаний", page)

    await page.locator("wiki-sidebar [data-wiki-create-page]").click()
    title_input = wiki_e2e_title_input(page)
    await expect(title_input).to_be_visible(timeout=30_000)
    await scenario.step("Создана пустая страница", page)

    title = f"Регламент {unique_id}"
    await title_input.fill(title)
    editor = page.locator("wiki-page-view .pm-editor")
    await expect(editor).to_be_visible(timeout=30_000)
    await editor.click()
    await page.keyboard.type("Первый абзац регламента.")

    save_state = page.locator("wiki-page-view .save-state")
    await expect(save_state).to_have_attribute("data-state", "done", timeout=30_000)
    await scenario.step("Заголовок и текст сохранены", page)

    _ = await page.reload(wait_until="domcontentloaded")
    await expect(wiki_e2e_title_input(page)).to_have_value(title, timeout=30_000)
    await expect(page.locator("wiki-page-view .pm-editor")).to_contain_text(
        "Первый абзац регламента."
    )
    await scenario.step("После перезагрузки содержимое на месте", page)


@pytest.mark.scenario(
    service="wiki",
    tag="pages",
    doc_slug="navigate-tree",
    title="Wiki: навигация по дереву страниц",
    title_en="Wiki: navigating the page tree",
    description="Раскрытие раздела в дереве и переход к вложенной странице.",
    description_en="Expanding a section in the tree and opening a nested page.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(90)
async def test_wiki_navigate_tree(
    scenario: ScenarioRecorder,
    wiki_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    page = ui_page_system
    namespace = await wiki_e2e_open_with_namespace(wiki_ui, page, unique_id, suffix="tree")

    parent_id = await wiki_api_create_page(
        wiki_ui.origin,
        auth_token_system,
        namespace=namespace,
        title=f"Раздел {unique_id}",
    )
    child_id = await wiki_api_create_page(
        wiki_ui.origin,
        auth_token_system,
        namespace=namespace,
        title=f"Вложенная {unique_id}",
        parent_page_id=parent_id,
    )

    _ = await page.reload(wait_until="domcontentloaded")
    parent_row = wiki_e2e_tree_row(page, parent_id)
    await expect(parent_row).to_be_visible(timeout=30_000)
    await scenario.step("В дереве появился раздел", page)

    await parent_row.locator(f'[data-twisty="{parent_id}"]').click()
    child_row = wiki_e2e_tree_row(page, child_id)
    await expect(child_row).to_be_visible(timeout=15_000)
    await scenario.step("Раздел раскрыт, видна вложенная страница", page)

    await child_row.click()
    await expect(wiki_e2e_title_input(page)).to_have_value(
        f"Вложенная {unique_id}", timeout=30_000
    )
    await scenario.step("Вложенная страница открыта", page)


@pytest.mark.scenario(
    service="wiki",
    tag="search",
    doc_slug="search-pages",
    title="Wiki: поиск по базе знаний",
    title_en="Wiki: searching the knowledge base",
    description="Поиск страницы по тексту и переход к результату.",
    description_en="Finding a page by text and opening the result.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(90)
async def test_wiki_search_pages(
    scenario: ScenarioRecorder,
    wiki_ui: AppUI,
    ui_page_system: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    page = ui_page_system
    namespace = await wiki_e2e_open_with_namespace(wiki_ui, page, unique_id, suffix="search")

    marker = f"кофемолка{unique_id}"
    page_id = await wiki_api_create_page(
        wiki_ui.origin,
        auth_token_system,
        namespace=namespace,
        title=f"Инструкция {unique_id}",
        markdown=f"# Инструкция\n\nОбслуживание {marker} по регламенту.",
    )

    _ = await page.goto(f"{wiki_ui.origin}/wiki/search")
    search_input = page.locator("wiki-search-page [data-wiki-search-input]")
    await expect(search_input).to_be_visible(timeout=30_000)
    await scenario.step("Открыт поиск", page)

    await search_input.fill(marker)
    hit = page.locator(f'wiki-search-page [data-wiki-hit="{page_id}"]')
    await expect(hit).to_be_visible(timeout=30_000)
    await scenario.step("Страница найдена по тексту", page)

    await hit.click()
    await expect(wiki_e2e_title_input(page)).to_have_value(
        f"Инструкция {unique_id}", timeout=30_000
    )
    await scenario.step("Результат поиска открыт", page)


@pytest.mark.scenario(
    service="wiki",
    tag="access",
    doc_slug="public-link",
    title="Wiki: публичная ссылка на раздел",
    title_en="Wiki: public link to a section",
    description="Включение публичной ссылки и чтение раздела с подстраницами без входа в систему.",
    description_en="Enabling a public link and reading a section with subpages without signing in.",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_wiki_public_link(
    scenario: ScenarioRecorder,
    wiki_ui: AppUI,
    ui_page_system: Page,
    ui_page_anonymous: Page,
    auth_token_system: str,
    unique_id: str,
) -> None:
    page = ui_page_system
    namespace = await wiki_e2e_open_with_namespace(wiki_ui, page, unique_id, suffix="public")

    page_id = await wiki_api_create_page(
        wiki_ui.origin,
        auth_token_system,
        namespace=namespace,
        title=f"Публичная {unique_id}",
        markdown="Этот текст открыт по ссылке.",
    )
    child_title = f"Глава {unique_id}"
    _ = await wiki_api_create_page(
        wiki_ui.origin,
        auth_token_system,
        namespace=namespace,
        title=child_title,
        parent_page_id=page_id,
        markdown="Текст подстраницы раздела.",
    )
    await wiki_e2e_open_page(page, wiki_ui.origin, page_id)

    await page.locator("wiki-page-view [data-wiki-page-menu]").click()
    await page.locator('platform-menu [data-menu-item="access"]').click()
    access_modal = page.locator("wiki-page-access-modal")
    await expect(access_modal).to_be_visible(timeout=15_000)
    await scenario.step("Открыто окно доступа", page)

    await access_modal.locator("[data-wiki-public-link]").click()
    await expect(access_modal.locator("[data-wiki-copy-link]")).to_be_visible(timeout=15_000)
    link_url = await access_modal.locator("[data-wiki-link-url]").inner_text()
    await scenario.step("Публичная ссылка включена", page)

    await wiki_e2e_set_locale_ru(ui_page_anonymous)
    _ = await ui_page_anonymous.goto(link_url.strip(), wait_until="domcontentloaded")
    site = ui_page_anonymous.locator("wiki-public-preview-page")
    await expect(site).to_contain_text("Этот текст открыт по ссылке.", timeout=30_000)
    await scenario.step(
        "Раздел открыт без входа в систему",
        ui_page_anonymous,
        label_en="Section opened without signing in",
    )

    await site.locator("platform-tree").get_by_text(child_title).click()
    await expect(site).to_contain_text("Текст подстраницы раздела.", timeout=30_000)
    await expect(site.locator("platform-breadcrumbs")).to_contain_text(
        f"Публичная {unique_id}", timeout=15_000
    )
    await scenario.step(
        "Подстраница открыта по той же ссылке",
        ui_page_anonymous,
        label_en="Subpage opened via the same link",
    )
