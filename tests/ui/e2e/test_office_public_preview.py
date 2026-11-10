"""E2E: анонимный просмотр по публичной ссылке Office."""

from __future__ import annotations

import os
import re

import pytest
from playwright.async_api import Page, expect

os.environ.setdefault("UI_E2E_USE_LVH_ME", "1")

from tests.ui.e2e.office_e2e_helpers import (
    office_api_create_catalog,
    office_api_enable_binding_public_link,
    office_api_upload_txt,
    office_e2e_goto_public_preview,
    office_e2e_set_locale_ru,
)
from tests.ui.e2e.sync_e2e_helpers import sync_e2e_seed_namespace
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

_DOC_BODY = b"public preview content for office e2e"


@pytest.mark.scenario(
    service="office",
    tag="public",
    doc_slug="public-link-preview",
    title="Office: просмотр документа по публичной ссылке",
    title_en="Office: view a document via public link",
    description=(
        "**Для чего:** эта инструкция покажет, как гость без аккаунта открывает "
        "документ по публичной ссылке.\n\n"
        "**Какие проблемы решает:** вы делитесь файлом с человеком вне компании "
        "и хотите знать, что он увидит и что произойдёт при неверной ссылке.\n\n"
        "**Результат:** документ открывается в браузере без входа, а нерабочая "
        "ссылка показывает понятную ошибку."
    ),
    description_en=(
        "**What for:** this guide shows how a guest without an account opens a "
        "document via a public link.\n\n"
        "**Problems it solves:** you share a file with someone outside the "
        "company and want to see what they will get and what a wrong link does.\n\n"
        "**Result:** the document opens in the browser without sign-in, and a "
        "broken link shows a clear error."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_office_public_link_preview(
    scenario: ScenarioRecorder,
    office_ui: AppUI,
    ui_page_anonymous: Page,
    unique_id: str,
    office_client_http,
    auth_headers_system,
    auth_token_system: str, frontend_di,
) -> None:
    doc_title = f"Public {unique_id}"

    namespace = await sync_e2e_seed_namespace(frontend_di, unique_id, suffix="public")
    catalog_id = await office_api_create_catalog(
        office_ui.origin,
        auth_token_system,
        unique_id,
        namespace=namespace,
        title_prefix="public",
    )
    file_id = await office_api_upload_txt(
        office_client_http,
        auth_headers_system,
        namespace=namespace,
        catalog_id=catalog_id,
        title=doc_title,
        content=_DOC_BODY,
    )
    token = await office_api_enable_binding_public_link(
        office_client_http,
        auth_headers_system,
        file_id,
        namespace=namespace,
    )

    await office_e2e_set_locale_ru(ui_page_anonymous)
    await office_e2e_goto_public_preview(office_ui, ui_page_anonymous, token)
    preview = ui_page_anonymous.locator("office-public-preview-page")
    await expect(preview).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте публичную ссылку на документ",
        ui_page_anonymous,
        screenshot_name="public-link-opened",
        label_en="Open the public document link",
        details=(
            "Вставьте полученную ссылку в адресную строку браузера. Входить в "
            "платформу не нужно — откроется страница предпросмотра."
        ),
        details_en=(
            "Paste the received link into the browser address bar. No sign-in is "
            "needed — the preview page opens."
        ),
    )

    await expect(preview).to_contain_text(doc_title, timeout=60_000)
    await scenario.step(
        "Проверьте название документа в шапке",
        ui_page_anonymous,
        screenshot_name="document-title-visible",
        label_en="Check the document title in the header",
        details=(
            "В верхней части страницы появится название файла. Это значит, что "
            "ссылка рабочая и документ доступен гостю."
        ),
        details_en=(
            "The file name appears at the top of the page. This means the link "
            "works and the document is available to the guest."
        ),
    )

    viewer = preview.locator("platform-document-viewer-host")
    await expect(viewer).to_be_visible(timeout=120_000)
    frame = preview.locator('iframe[name="frameEditor"]')
    await expect(frame).to_be_visible(timeout=120_000)
    await expect(
        preview.locator("platform-onlyoffice-host .editor-loading-overlay")
    ).to_have_count(0, timeout=120_000)
    oo_frame = preview.frame_locator('iframe[name="frameEditor"]')
    await oo_frame.get_by_role("button", name="OK").click(timeout=120_000)
    await expect(oo_frame.locator(".loadmask, .asc-loadmask")).to_have_count(0, timeout=120_000)
    await expect(
        oo_frame.get_by_text(re.compile(r"Page \d+ of \d+|Страница \d+ из \d+"))
    ).to_be_visible(timeout=120_000)
    await scenario.step(
        "Дождитесь содержимого документа",
        ui_page_anonymous,
        screenshot_name="document-content-visible",
        label_en="Wait for the document content",
        details=(
            "Просмотрщик подгружает текст файла — дождитесь, пока содержимое "
            "появится вместо заглушки. Документ можно читать прямо на странице."
        ),
        details_en=(
            "The viewer loads the file text — wait until the content replaces "
            "the placeholder. The document is readable right on the page."
        ),
    )

    await office_e2e_goto_public_preview(office_ui, ui_page_anonymous, "invalid-token-000")
    await expect(preview.get_by_text("Ссылка не найдена")).to_be_visible(timeout=30_000)
    await scenario.step(
        "Проверьте, что неверная ссылка не работает",
        ui_page_anonymous,
        screenshot_name="invalid-link-error",
        label_en="Check that a wrong link is rejected",
        details=(
            "**Демонстрация результата.** Если ссылку изменить или она устареет, "
            "страница покажет «Ссылка не найдена» — случайный человек не увидит "
            "чужой документ.\n\n"
            "**Итог.** Вы знаете, что гость видит по публичной ссылке: сам "
            "документ без входа и понятную ошибку при неверном адресе."
        ),
        details_en=(
            "**Result demonstration.** If the link is altered or expires, the "
            "page shows “Link not found” — a stranger cannot open the document.\n\n"
            "**Summary.** You know what a guest sees via a public link: the "
            "document itself without sign-in, and a clear error for a bad link."
        ),
    )

    _ = file_id
