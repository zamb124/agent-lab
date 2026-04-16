"""E2E: вложение изображения в сообщение."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.sync_e2e_helpers import sync_sidebar_channel_nav
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

# Минимальный валидный PNG 1x1 (серый пиксель).
_MIN_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.mark.scenario(
    service="sync",
    tag="files",
    doc_slug="message-with-image",
    title="Sync: отправка сообщения с изображением",
    description=(
        "Пользователь прикрепляет изображение к сообщению; после отправки в ленту попадает блок с картинкой."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_user_sends_message_with_image_attachment(
    scenario: ScenarioRecorder,
    sync_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
    tmp_path,
) -> None:
    space_name = f"E2E file space {unique_id}"
    channel_name = f"Канал файлов {unique_id}"
    caption = f"Фото {unique_id}"

    png_path = tmp_path / "e2e.png"
    png_path.write_bytes(_MIN_PNG)

    await sync_ui.open(ui_page_system)
    await sync_ui.expect_shell(ui_page_system)

    await ui_page_system.get_by_role("button", name="Создать пространство").click()
    sm = ui_page_system.locator("space-settings-modal")
    await expect(sm).to_be_visible()
    ins = sm.locator('input.input:not([type="file"])')
    await ins.nth(0).fill(space_name)
    await sm.get_by_role("button", name="Создать", exact=True).click()
    await expect(ui_page_system.get_by_role("button", name=space_name)).to_be_visible(
        timeout=30_000
    )

    await ui_page_system.get_by_role("button", name="Создать канал").click()
    ch_modal = ui_page_system.locator("channel-settings-modal")
    await expect(ch_modal).to_be_visible()
    await ch_modal.get_by_placeholder("Название канала").fill(channel_name)
    await ch_modal.get_by_role("button", name="Создать", exact=True).click()
    await expect(sync_sidebar_channel_nav(ui_page_system, channel_name)).to_be_visible(
        timeout=30_000
    )

    await sync_sidebar_channel_nav(ui_page_system, channel_name).click()
    await expect(ui_page_system.locator("chat-view")).to_be_visible()
    await scenario.step("Канал открыт", ui_page_system)

    composer = ui_page_system.locator("message-composer")
    await composer.locator('[title="Прикрепить файл"]').click()
    file_input = composer.locator('input[type="file"][accept*="image"]')
    await expect(file_input).to_be_attached()
    await file_input.set_input_files(str(png_path))
    await composer.locator("textarea[placeholder='Сообщение...']").fill(caption)
    await composer.locator('button.send[title="Отправить"]').click()

    await expect(ui_page_system.locator("message-bubble").get_by_text(caption, exact=True)).to_be_visible(
        timeout=60_000
    )
    await expect(ui_page_system.locator("message-bubble").locator("img.file-image")).to_be_visible(
        timeout=15_000
    )
    await scenario.step("Сообщение с превью изображения в ленте", ui_page_system)
