"""Общие шаги E2E базы знаний (`/wiki`)."""

from __future__ import annotations

from typing import cast

import httpx2
from playwright.async_api import Page, expect

from core.di.platform import PlatformDi
from tests.ui.e2e.sync_e2e_helpers import (
    sync_e2e_activate_namespace_for_next_load,
    sync_e2e_seed_namespace,
)
from tests.ui.e2e_worker import ui_e2e_company_id
from tests.ui.harness import AppUI


async def wiki_e2e_set_locale_ru(page: Page) -> None:
    _ = await page.add_init_script(
        """
        (() => {
            window.localStorage.setItem('platform_locale', 'ru');
            document.cookie = 'language=ru; path=/; SameSite=Lax';
            document.documentElement.lang = 'ru';
        })();
        """
    )


async def wiki_e2e_open_with_namespace(
    wiki_ui: AppUI,
    page: Page,
    unique_id: str,
    *,
    di: PlatformDi,
    suffix: str = "wiki",
) -> str:
    """Готовит пространство и открывает SPA сразу в нём."""
    company_id = ui_e2e_company_id()
    namespace = await sync_e2e_seed_namespace(di, unique_id, suffix=suffix, company_id=company_id)
    await sync_e2e_activate_namespace_for_next_load(page, namespace, company_id=company_id)
    await wiki_e2e_set_locale_ru(page)
    await wiki_ui.open(page)
    await expect(page.locator("wiki-app")).to_be_visible(timeout=30_000)
    return namespace


async def wiki_api_create_page(
    origin: str,
    auth_token: str,
    *,
    namespace: str,
    title: str,
    parent_page_id: str | None = None,
    markdown: str = "",
) -> str:
    """Создаёт страницу через API — быстрее и надёжнее, чем через UI."""
    body: dict[str, object] = {"title": title}
    if parent_page_id is not None:
        body["parent_page_id"] = parent_page_id
    if markdown != "":
        body["markdown"] = markdown
    async with httpx2.AsyncClient(base_url=origin, timeout=30.0) as client:
        response = await client.post(
            "/wiki/api/v1/pages",
            json=body,
            headers={
                "Cookie": f"auth_token={auth_token}",
                "X-Platform-Namespace": namespace,
            },
        )
    _ = response.raise_for_status()
    payload = cast(dict[str, dict[str, str]], response.json())
    page_id = payload["page"]["wiki_page_id"]
    assert page_id != ""
    return page_id


def wiki_e2e_tree_row(page: Page, page_id: str):
    """Строка дерева в сайдбаре.

    Второе дерево той же страницы живёт в мобильном листе `wiki.tree`: он всегда
    в DOM, поэтому без привязки к сайдбару локатор находит два узла.
    """
    return page.locator(f'wiki-sidebar platform-tree [data-node-id="{page_id}"]')


def wiki_e2e_title_input(page: Page):
    return page.locator("wiki-page-view [data-wiki-title]")


async def wiki_e2e_open_page(page: Page, origin: str, page_id: str) -> None:
    _ = await page.goto(f"{origin}/wiki/p/{page_id}")
    await expect(wiki_e2e_title_input(page)).to_be_visible(timeout=30_000)
