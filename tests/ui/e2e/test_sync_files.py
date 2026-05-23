"""E2E: вложение изображения в сообщение."""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.sync_e2e_helpers import (
    sync_e2e_create_topic_channel_and_open,
    sync_e2e_open_with_namespace,
)
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
    caption = f"Фото {unique_id}"

    png_path = tmp_path / "e2e.png"
    png_path.write_bytes(_MIN_PNG)

    await sync_e2e_open_with_namespace(sync_ui, ui_page_system, unique_id, suffix="file")
    await sync_e2e_create_topic_channel_and_open(
        ui_page_system,
        unique_id,
        channel_prefix="Канал файлов",
    )
    await scenario.step("Канал открыт", ui_page_system)

    composer = ui_page_system.locator("sync-message-composer")
    file_input = composer.locator("input#photopick")
    await expect(file_input).to_be_attached()
    await file_input.set_input_files(str(png_path))
    await expect(composer.locator(".att").filter(has_text="e2e.png")).to_be_visible(timeout=30_000)
    await composer.locator('textarea[data-canon="composer"]').fill(caption)
    await composer.locator('button.send').click()

    await expect(ui_page_system.locator("sync-message-bubble").get_by_text(caption, exact=True)).to_be_visible(
        timeout=60_000
    )
    await expect(ui_page_system.locator("sync-message-bubble").locator(".image-wrap img")).to_be_visible(
        timeout=15_000
    )
    await scenario.step("Сообщение с превью изображения в ленте", ui_page_system)
