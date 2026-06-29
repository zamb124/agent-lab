"""Общие локаторы и API-seed для E2E Office (/documents)."""

from __future__ import annotations

import re
from pathlib import Path

import httpx
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Locator, Page, expect

from tests.office.access_helpers import (
    create_private_catalog,
    create_public_catalog,
    enable_binding_link,
    enable_catalog_link,
    upload_txt_binding,
)
from tests.ui.e2e.sync_e2e_helpers import (
    sync_e2e_activate_namespace_for_next_load,
    sync_e2e_click_platform_button,
    sync_e2e_expect_namespace,
    sync_e2e_expect_ws_open,
    sync_e2e_seed_namespace,
    sync_e2e_select_namespace,
)

_MIN_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
)


def office_e2e_namespace_name(unique_id: str, *, suffix: str = "ui") -> str:
    safe_suffix = suffix.strip("_")
    return f"ns_{unique_id}_{safe_suffix}" if safe_suffix else f"ns_{unique_id}"


async def office_e2e_set_locale_ru(page: Page) -> None:
    await page.add_init_script(
        """
        (() => {
            window.localStorage.setItem('platform_locale', 'ru');
            document.cookie = 'language=ru; path=/; SameSite=Lax';
            document.documentElement.lang = 'ru';
        })();
        """
    )


def office_e2e_explorer(page: Page) -> Locator:
    return page.locator("office-documents-explorer-page").first


def office_e2e_toolbar(page: Page) -> Locator:
    return office_e2e_explorer(page).locator("office-file-toolbar").first


def office_e2e_tree(page: Page) -> Locator:
    return page.locator("office-explorer-tree").first


def office_e2e_nav_rail(page: Page) -> Locator:
    return page.locator("office-explorer-nav-rail").first


def office_e2e_catalog_row(page: Page, title: str) -> Locator:
    return office_e2e_tree(page).locator("button.item").filter(has_text=title).first


async def office_e2e_open(office_ui, page: Page) -> None:
    await office_ui.open(page)
    await office_ui.expect_shell(page)
    await office_e2e_expect_explorer(page)


async def office_e2e_expect_explorer(page: Page, *, timeout: float = 30_000) -> None:
    await expect(office_e2e_explorer(page)).to_be_visible(timeout=timeout)


async def office_e2e_open_with_namespace(
    office_ui,
    page: Page,
    unique_id: str,
    *,
    suffix: str = "ui",
    company_id: str = "system",
) -> str:
    namespace = await sync_e2e_seed_namespace(unique_id, suffix=suffix, company_id=company_id)
    await sync_e2e_activate_namespace_for_next_load(page, namespace, company_id=company_id)
    await office_e2e_set_locale_ru(page)
    await office_e2e_open(office_ui, page)
    await sync_e2e_expect_ws_open(page)
    try:
        await sync_e2e_expect_namespace(page, namespace, timeout=5_000)
    except PlaywrightError:
        await sync_e2e_select_namespace(page, namespace)
    return namespace


async def office_e2e_click_modal_button(
    modal: Locator,
    *labels: str,
    timeout: float = 30_000,
) -> None:
    if not labels:
        raise ValueError("labels required")
    pattern = re.compile("|".join(re.escape(label) for label in labels))
    platform_btn = modal.locator("platform-button").filter(has_text=pattern)
    if await platform_btn.count() > 0:
        await sync_e2e_click_platform_button(modal, *labels, timeout=timeout)
        return
    btn = modal.locator("button.btn-primary, button.btn-danger, button.btn-secondary, button.btn").filter(
        has_text=pattern
    ).first
    await expect(btn).to_be_visible(timeout=timeout)
    await btn.click()


async def office_e2e_create_namespace_ui(page: Page, namespace_name: str) -> None:
    ns_select = page.locator("platform-sidebar-namespace-select").first
    add_btn = ns_select.locator("button.btn-add")
    await expect(add_btn).to_be_visible(timeout=30_000)
    await add_btn.click()
    modal = page.locator("office-namespace-create-modal")
    await expect(modal).to_be_visible(timeout=30_000)
    template = modal.locator("button.template-card").first
    await expect(template).to_be_visible(timeout=60_000)
    await template.click()
    name_input = modal.locator("input.field-pill-input").first
    await name_input.fill(namespace_name)
    await office_e2e_click_modal_button(modal, "Создать пространство", "Create workspace")
    await expect(modal).to_be_hidden(timeout=45_000)
    await sync_e2e_expect_namespace(page, namespace_name)


async def office_e2e_create_catalog_ui(
    page: Page,
    title: str,
    *,
    from_tree: bool = True,
) -> None:
    if from_tree:
        create_btn = office_e2e_tree(page).locator("button.head-btn").first
        await expect(create_btn).to_be_visible(timeout=30_000)
        await create_btn.click()
    else:
        await office_e2e_explorer(page).get_by_role("button", name="Новый каталог").click()
    modal = page.locator("office-catalog-create-modal")
    await expect(modal).to_be_visible(timeout=30_000)
    await modal.locator("input.field-pill-input").first.fill(title)
    await office_e2e_click_modal_button(modal, "Создать", "Create")
    await expect(modal).to_be_hidden(timeout=45_000)
    await expect(office_e2e_catalog_row(page, title)).to_be_visible(timeout=45_000)


async def office_e2e_select_catalog(page: Page, title: str) -> None:
    row = office_e2e_catalog_row(page, title)
    await expect(row).to_be_visible(timeout=30_000)
    await row.click()


async def office_e2e_open_create_empty_modal(page: Page) -> Locator:
    toolbar = office_e2e_toolbar(page)
    await toolbar.get_by_role("button", name="Новый документ").click()
    modal = page.locator("office-document-create-empty-modal")
    await expect(modal).to_be_visible(timeout=30_000)
    return modal


async def office_e2e_create_empty_document(
    page: Page,
    title: str,
    *,
    type_label: str = "Текст",
) -> None:
    modal = await office_e2e_open_create_empty_modal(page)
    await modal.locator("input.field-pill-input").first.fill(title)
    type_card = modal.locator(".type-card").filter(has_text=type_label).first
    await expect(type_card).to_be_visible(timeout=10_000)
    await type_card.click()
    await office_e2e_click_modal_button(modal, "Создать", "Create")
    await expect(modal).to_be_hidden(timeout=60_000)


async def office_e2e_open_upload_modal(page: Page) -> Locator:
    toolbar = office_e2e_toolbar(page)
    await toolbar.get_by_role("button", name="Загрузить файл").click()
    modal = page.locator("office-document-upload-modal")
    await expect(modal).to_be_visible(timeout=30_000)
    return modal


async def office_e2e_upload_file_ui(page: Page, file_path: Path) -> None:
    modal = await office_e2e_open_upload_modal(page)
    file_input = modal.locator('input[type="file"]')
    await file_input.set_input_files(str(file_path))
    await office_e2e_click_modal_button(modal, "Загрузить", "Upload")
    await expect(modal).to_be_hidden(timeout=120_000)


async def office_e2e_open_document_by_title(page: Page, title: str) -> None:
    row = page.locator("platform-file-row").filter(has_text=title).first
    card = page.locator("platform-file-card").filter(has_text=title).first
    target = row.or_(card)
    await expect(target).to_be_visible(timeout=45_000)
    await target.click()
    details = office_e2e_explorer(page).locator("office-file-details-panel")
    open_btn = details.get_by_role("button", name=re.compile(r"^Открыть$|^Open$"))
    if await open_btn.count() > 0:
        await open_btn.click()
    else:
        await target.dblclick()
    await expect(page.locator("office-document-editor-page")).to_be_visible(timeout=60_000)


async def office_e2e_select_nav_view(page: Page, *labels: str) -> None:
    pattern = re.compile("|".join(re.escape(label) for label in labels))
    item = office_e2e_nav_rail(page).locator("button.item").filter(has_text=pattern).first
    await expect(item).to_be_visible(timeout=30_000)
    await item.click()


async def office_e2e_set_view_mode(page: Page, mode: str) -> None:
    if mode not in {"list", "grid"}:
        raise ValueError("mode must be list or grid")
    toolbar = office_e2e_toolbar(page)
    btn = toolbar.locator("button.view-btn").nth(0 if mode == "list" else 1)
    await expect(btn).to_be_visible(timeout=10_000)
    await btn.click()


async def office_e2e_search_documents(page: Page, query: str) -> None:
    search = office_e2e_toolbar(page).locator("platform-field input.field-pill-input").first
    await expect(search).to_be_visible(timeout=10_000)
    await search.fill(query)
    await page.wait_for_timeout(400)


async def office_e2e_refresh_documents(page: Page) -> None:
    toolbar = office_e2e_toolbar(page)
    overflow = toolbar.locator("button.btn-icon-only").first
    await expect(overflow).to_be_visible(timeout=10_000)
    await overflow.click()
    refresh_item = toolbar.locator("button.overflow-item").filter(
        has_text=re.compile(r"Обновить|Refresh")
    ).first
    await expect(refresh_item).to_be_visible(timeout=10_000)
    await refresh_item.click()


async def office_e2e_star_selected_document(page: Page) -> None:
    details = office_e2e_explorer(page).locator("office-file-details-panel")
    star_btn = details.get_by_role("button", name=re.compile(r"Избранное|В избранное|star", re.I))
    if await star_btn.count() == 0:
        star_btn = details.locator("button").filter(has=page.locator("platform-icon[name='star']")).first
    await expect(star_btn).to_be_visible(timeout=15_000)
    await star_btn.click()


async def office_e2e_open_file_actions_menu(page: Page, title: str) -> None:
    row = page.locator("platform-file-row").filter(has_text=title).first
    card = page.locator("platform-file-card").filter(has_text=title).first
    target = row.or_(card)
    await expect(target).to_be_visible(timeout=15_000)
    menu_host = target.locator("office-file-actions-menu").first
    trigger = menu_host.locator("button.trigger").first
    await expect(trigger).to_be_visible(timeout=15_000)
    await trigger.click()


async def office_e2e_click_file_action(page: Page, title: str, *action_labels: str) -> None:
    await office_e2e_open_file_actions_menu(page, title)
    pattern = re.compile("|".join(re.escape(label) for label in action_labels))
    row = page.locator("platform-file-row").filter(has_text=title).first
    card = page.locator("platform-file-card").filter(has_text=title).first
    target = row.or_(card)
    item = target.locator("office-file-actions-menu .item").filter(has_text=pattern).first
    await expect(item).to_be_visible(timeout=10_000)
    await item.click()


async def office_e2e_rename_document(page: Page, title: str, new_title: str) -> None:
    row = page.locator("platform-file-row").filter(has_text=title).first
    await expect(row).to_be_visible(timeout=15_000)
    await row.click()
    details = office_e2e_explorer(page).locator("office-file-details-panel")
    rename_btn = details.get_by_role("button", name=re.compile(r"^Переименовать$|^Rename$"))
    if await rename_btn.count() > 0:
        await rename_btn.click()
    else:
        await office_e2e_click_file_action(page, title, "Переименовать", "Rename")
    modal = page.locator("office-document-rename-modal")
    await expect(modal).to_be_visible(timeout=30_000)
    await modal.locator("input.field-pill-input").first.fill(new_title)
    await office_e2e_click_modal_button(modal, "Сохранить", "Save")
    await expect(modal).to_be_hidden(timeout=45_000)


async def office_e2e_delete_document(page: Page, title: str) -> None:
    row = page.locator("platform-file-row").filter(has_text=title).first
    await expect(row).to_be_visible(timeout=15_000)
    await row.click()
    details = office_e2e_explorer(page).locator("office-file-details-panel")
    delete_btn = details.get_by_role("button", name=re.compile(r"^Удалить$|^Delete$"))
    if await delete_btn.count() > 0:
        await delete_btn.click()
    else:
        await office_e2e_click_file_action(page, title, "Удалить", "Delete")
    confirm = page.locator("platform-confirm-modal")
    await expect(confirm).to_be_visible(timeout=15_000)
    await office_e2e_click_modal_button(confirm, "Удалить", "Delete")
    await expect(confirm).to_be_hidden(timeout=30_000)


async def office_e2e_open_catalog_context_menu(page: Page, title: str) -> None:
    row = office_e2e_tree(page).locator(".tree-row").filter(has_text=title).first
    menu_btn = row.locator("button.mini-btn").filter(
        has=page.locator("platform-icon[name='more-vertical']")
    ).first
    await expect(menu_btn).to_be_visible(timeout=15_000)
    await menu_btn.click()


async def office_e2e_catalog_context_action(page: Page, title: str, *labels: str) -> None:
    await office_e2e_open_catalog_context_menu(page, title)
    pattern = re.compile("|".join(re.escape(label) for label in labels))
    item = page.locator("office-catalog-context-menu .ctx-item").filter(has_text=pattern).first
    await expect(item).to_be_visible(timeout=10_000)
    await item.click()


async def office_e2e_create_subcatalog_ui(page: Page, parent_title: str, child_title: str) -> None:
    row = office_e2e_tree(page).locator(".tree-row").filter(has_text=parent_title).first
    plus_btn = row.locator("button.mini-btn").filter(
        has=page.locator("platform-icon[name='plus']")
    ).first
    await expect(plus_btn).to_be_visible(timeout=15_000)
    await plus_btn.click()
    modal = page.locator("office-catalog-create-modal")
    await expect(modal).to_be_visible(timeout=30_000)
    await modal.locator("input.field-pill-input").first.fill(child_title)
    await office_e2e_click_modal_button(modal, "Создать", "Create")
    await expect(modal).to_be_hidden(timeout=45_000)
    await expect(office_e2e_catalog_row(page, child_title)).to_be_visible(timeout=45_000)


async def office_e2e_open_access_modal_catalog(page: Page, catalog_title: str) -> Locator:
    await office_e2e_catalog_context_action(page, catalog_title, "Доступ", "Access")
    modal = page.locator("office-access-modal")
    await expect(modal).to_be_visible(timeout=30_000)
    return modal


def office_e2e_namespace_headers(headers: dict[str, str], namespace: str) -> dict[str, str]:
    if not namespace:
        raise ValueError("namespace is required")
    return {**headers, "X-Platform-Namespace": namespace}


def _office_client(origin: str, auth_token: str, *, namespace: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=origin,
        cookies={"auth_token": auth_token},
        headers={"X-Platform-Namespace": namespace},
        timeout=60.0,
    )


async def office_api_create_catalog(
    origin: str,
    auth_token: str,
    unique_id: str,
    *,
    namespace: str,
    title_prefix: str = "catalog",
    is_public: bool = True,
    parent_catalog_id: str | None = None,
) -> str:
    async with _office_client(origin, auth_token, namespace=namespace) as client:
        payload: dict[str, object] = {
            "title": f"{title_prefix}-{unique_id}",
            "is_public": is_public,
        }
        if parent_catalog_id:
            payload["parent_catalog_id"] = parent_catalog_id
        response = await client.post("/documents/api/v1/catalogs", json=payload)
        if response.status_code != 200:
            raise AssertionError(f"create catalog failed: {response.status_code} {response.text}")
        body = response.json()
        catalog_id = body.get("catalog_id")
        if not isinstance(catalog_id, str) or catalog_id == "":
            raise AssertionError("catalog_id required in create catalog response")
        return catalog_id


async def office_api_create_empty_document(
    origin: str,
    auth_token: str,
    *,
    namespace: str,
    catalog_id: str,
    title: str,
    document_type: str = "word",
) -> str:
    async with _office_client(origin, auth_token, namespace=namespace) as client:
        response = await client.post(
            "/documents/api/v1/documents/empty",
            json={
                "catalog_id": catalog_id,
                "title": title,
                "document_type": document_type,
            },
        )
        if response.status_code != 200:
            raise AssertionError(f"create empty doc failed: {response.status_code} {response.text}")
        body = response.json()
        binding_id = body.get("binding_id")
        if not isinstance(binding_id, str) or binding_id == "":
            raise AssertionError("binding_id required in empty document response")
        return binding_id


async def office_api_upload_txt(
    office_client_http,
    auth_headers: dict[str, str],
    *,
    namespace: str,
    catalog_id: str,
    title: str,
    content: bytes = b"office e2e content",
) -> str:
    return await upload_txt_binding(
        office_client_http,
        office_e2e_namespace_headers(auth_headers, namespace),
        catalog_id=catalog_id,
        title=title,
        content=content,
    )


async def office_api_setup_private_catalog(
    office_client_http,
    auth_headers: dict[str, str],
    unique_id: str,
    *,
    namespace: str,
    title_prefix: str = "access-private",
) -> str:
    return await create_private_catalog(
        office_client_http,
        office_e2e_namespace_headers(auth_headers, namespace),
        unique_id,
        title_prefix=title_prefix,
    )


async def office_api_setup_public_catalog(
    office_client_http,
    auth_headers: dict[str, str],
    unique_id: str,
    *,
    namespace: str,
) -> str:
    return await create_public_catalog(
        office_client_http,
        office_e2e_namespace_headers(auth_headers, namespace),
        unique_id,
    )


async def office_api_enable_catalog_public_link(
    office_client_http,
    auth_headers: dict[str, str],
    catalog_id: str,
    *,
    namespace: str,
) -> str:
    headers = office_e2e_namespace_headers(auth_headers, namespace)
    token, _body = await enable_catalog_link(office_client_http, headers, catalog_id)
    return token


async def office_api_enable_binding_public_link(
    office_client_http,
    auth_headers: dict[str, str],
    binding_id: str,
    *,
    namespace: str,
) -> str:
    headers = office_e2e_namespace_headers(auth_headers, namespace)
    token, _body = await enable_binding_link(office_client_http, headers, binding_id)
    return token


async def office_api_enable_rag_index(
    office_client_http,
    auth_headers: dict[str, str],
    catalog_id: str,
    *,
    namespace: str,
) -> None:
    response = await office_client_http.post(
        f"/documents/api/v1/catalogs/{catalog_id}/rag-index/enable",
        headers=office_e2e_namespace_headers(auth_headers, namespace),
    )
    if response.status_code != 200:
        raise AssertionError(f"enable rag failed: {response.status_code} {response.text}")


async def office_api_delete_document(
    office_client_http,
    auth_headers: dict[str, str],
    binding_id: str,
    *,
    namespace: str,
) -> None:
    response = await office_client_http.delete(
        f"/documents/api/v1/documents/{binding_id}",
        headers=office_e2e_namespace_headers(auth_headers, namespace),
    )
    if response.status_code not in {200, 204}:
        raise AssertionError(f"delete document failed: {response.status_code} {response.text}")


def office_e2e_min_png_path(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.write_bytes(_MIN_PNG)
    return path


async def office_e2e_expect_editor_loaded(page: Page) -> None:
    editor = page.locator("office-document-editor-page")
    await expect(editor).to_be_visible(timeout=60_000)
    host = editor.locator("platform-document-viewer-host, platform-onlyoffice-host")
    await expect(host.first).to_be_visible(timeout=120_000)


async def office_e2e_goto_public_preview(office_ui, page: Page, token: str) -> None:
    url = f"{office_ui.origin}/documents/p/{token}"
    await page.goto(url, wait_until="domcontentloaded")
    await expect(page.locator("office-app")).to_be_visible(timeout=30_000)
    await expect(page.locator("office-public-preview-page")).to_be_visible(timeout=60_000)
