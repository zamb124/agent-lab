"""E2E: звонок в канале и страница входа по ссылке."""

from __future__ import annotations

import re

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.sync_e2e_helpers import (
    sync_e2e_create_topic_channel_and_open,
    sync_e2e_open_with_namespace,
    sync_sidebar_channel_nav,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


async def _click_channel_call_button(page: Page) -> None:
    call_button = page.locator("sync-chat-header button.icon-btn.accent").first
    await expect(call_button).to_be_visible(timeout=30_000)
    await call_button.click()


async def _install_call_trace(page: Page) -> None:
    page.on(
        "console",
        lambda msg: print(f"\n=== PAGE-CONSOLE[{msg.type}]: {msg.text[:300]}")
        if msg.type in ("error", "warning") or "livekit" in msg.text.lower()
        else None,
    )
    await page.evaluate(
        """() => {
            window.__callTrace = [];
            const t0 = Date.now();
            window.__PLATFORM_BUS__.subscribeAny((ev) => {
                const ty = ev && ev.type ? ev.type : '?';
                if (ty.includes('call') || ty.includes('modal')) {
                    window.__callTrace.push({
                        t: Date.now() - t0,
                        type: ty,
                        payload: JSON.stringify(ev.payload === undefined ? null : ev.payload).slice(0, 400),
                    });
                }
            });
        }"""
    )


async def _dump_call_trace(page: Page) -> None:
    trace = await page.evaluate("() => window.__callTrace || 'NO-TRACE'")
    print(f"\n=== CALL-TRACE: {trace}")


async def _ensure_overlay_chat_open(overlay) -> None:
    chat_input = overlay.locator("textarea.chat-input")
    if await chat_input.is_visible(timeout=1_000):
        return
    toggle = overlay.locator(
        'button.ctrl[title="Показать чат"], button.ctrl[title="Show chat"]'
    ).first
    await expect(toggle).to_be_visible(timeout=30_000)
    page = toggle.page
    info = await toggle.evaluate(
        """(btn) => {
            const r = btn.getBoundingClientRect();
            const cx = r.x + r.width / 2, cy = r.y + r.height / 2;
            let modal = btn;
            while (modal && modal.tagName !== 'SYNC-CALL-OVERLAY-MODAL') {
                modal = modal.parentElement || (modal.getRootNode && modal.getRootNode().host) || null;
            }
            const attrs = {};
            if (modal) for (const a of modal.attributes) attrs[a.name] = a.value;
            const mcs = modal ? getComputedStyle(modal) : null;
            const mr = modal ? modal.getBoundingClientRect() : {x:0,y:0,width:0,height:0};
            const bcs = getComputedStyle(document.body);
            const midStack = document.elementsFromPoint(innerWidth/2, innerHeight/2).map(e => e.tagName);
            return {
                box: {x: r.x, y: r.y, w: r.width, h: r.height},
                center: {x: cx, y: cy},
                stack: document.elementsFromPoint(cx, cy).map(e => {
                    const cs = getComputedStyle(e);
                    return e.tagName + '|pe=' + cs.pointerEvents + '|z=' + cs.zIndex;
                }),
                midStack,
                modalAttrs: attrs,
                modalPe: mcs ? mcs.pointerEvents : 'NO-MODAL',
                modalVis: mcs ? mcs.visibility : 'NO-MODAL',
                modalDisp: mcs ? mcs.display : 'NO-MODAL',
                modalClip: mcs ? mcs.clipPath : 'NO-MODAL',
                modalCv: mcs ? mcs.contentVisibility : 'NO-MODAL',
                bodyPe: bcs.pointerEvents,
                bodyVis: bcs.visibility,
                docHidden: document.hidden,
                modalRect: {x: Math.round(mr.x), y: Math.round(mr.y), w: Math.round(mr.width), h: Math.round(mr.height)},
                modalParent: modal && modal.parentElement ? modal.parentElement.tagName : null,
                modalCount: document.querySelectorAll('sync-call-overlay-modal').length,
            };
        }"""
    )
    print(f"\n=== TOGGLE-PROBE: {info}")
    try:
        await toggle.click(timeout=12_000)
    except Exception:
        info2 = await page.evaluate(
            """() => Array.from(document.querySelectorAll('sync-call-overlay-modal')).map(m => {
                const r = m.getBoundingClientRect();
                const cs = getComputedStyle(m);
                return {open: m.hasAttribute('open'), closing: m.hasAttribute('closing'), min: m.hasAttribute('data-minimized'), pe: cs.pointerEvents, disp: cs.display, vis: cs.visibility, rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)}};
            })"""
        )
        print(f"=== TOGGLE-PROBE post-fail modals: {info2}")
        raise
    await expect(chat_input).to_be_visible(timeout=30_000)


@pytest.mark.scenario(
    service="sync",
    tag="calls",
    doc_slug="channel-call-overlay",
    title="Sync: старт звонка из шапки канала",
    description=(
        "В topic-канале пользователь нажимает «Звонок в этом канале»; после ответа сервера "
        "отображается оверлей звонка (атрибут data-call-active на sync-app)."
    ),
    title_en="Sync: start a call from the channel header",
    description_en=(
        "In a topic channel the user clicks «Call in this channel»; after the server responds "
        "the call overlay appears (data-call-active on sync-app)."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_user_starts_channel_call_overlay(
    scenario: ScenarioRecorder,
    sync_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    await sync_e2e_open_with_namespace(sync_ui, ui_page_system, unique_id, suffix="call")
    await sync_e2e_create_topic_channel_and_open(
        ui_page_system,
        unique_id,
        channel_prefix="Канал звонка",
    )
    await scenario.step(
        "Открыт topic-канал",
        ui_page_system,
        label_en="Topic channel opened",
    )

    await _click_channel_call_button(ui_page_system)
    await expect(ui_page_system.locator("sync-app")).to_have_attribute("data-call-active", "", timeout=90_000)
    await expect(ui_page_system.locator("sync-call-overlay-modal")).to_be_visible(timeout=15_000)
    await scenario.step(
        "Отображается оверлей звонка",
        ui_page_system,
        label_en="Call overlay is displayed",
    )


@pytest.mark.scenario(
    service="sync",
    tag="calls",
    doc_slug="join-invalid-token",
    title="Sync: страница входа по недействительной ссылке",
    description="Публичная страница /sync/join/{token} показывает сообщение об ошибке для несуществующего токена.",
    title_en="Sync: join page for an invalid link",
    description_en=(
        "The public /sync/join/{token} page shows an error message for a nonexistent token."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(60)
async def test_call_join_page_shows_error_for_invalid_token(
    scenario: ScenarioRecorder,
    sync_ui: AppUI,
    page: Page,
) -> None:
    await page.goto(f"{sync_ui.origin}/sync/join/invalid-token-e2e", wait_until="domcontentloaded")
    await scenario.step(
        "Открыта страница входа по ссылке звонка",
        page,
        label_en="Call join page opened from link",
    )
    await expect(page.locator("sync-call-join-page .error-text")).to_contain_text(
        re.compile(
            r"Ссылка не найдена или истекла|Не удалось загрузить информацию о звонке|"
            r"Link not found or expired|Could not load call information"
        ),
        timeout=30_000,
    )
    await scenario.step(
        "Сообщение об ошибке для неверной ссылки",
        page,
        label_en="Error message for invalid join link",
    )


@pytest.mark.scenario(
    service="sync",
    tag="calls",
    doc_slug="call-overlay-chat-sync",
    title="Sync: чат в оверлее звонка синхронизирован с каналом",
    description=(
        "Сообщение из основного чата видно в call-overlay, а сообщение из call-overlay после завершения звонка "
        "отображается в ленте канала."
    ),
    title_en="Sync: call overlay chat stays in sync with the channel",
    description_en=(
        "A message from the main chat appears in the call overlay, and a message from the call overlay "
        "appears in the channel feed after the call ends."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_call_overlay_channel_chat_syncs_with_main_chat(
    scenario: ScenarioRecorder,
    sync_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    main_text = f"Сообщение до звонка {unique_id}"
    overlay_text = f"Сообщение из оверлея {unique_id}"

    await sync_e2e_open_with_namespace(sync_ui, ui_page_system, unique_id, suffix="overlay")
    await sync_e2e_create_topic_channel_and_open(
        ui_page_system,
        unique_id,
        channel_prefix="Канал чата звонка",
    )
    composer = ui_page_system.locator("sync-message-composer")
    await expect(composer).to_be_visible()
    await composer.locator('textarea[data-canon="composer"]').fill(main_text)
    await composer.locator('button.send').click()
    await expect(ui_page_system.locator("sync-message-bubble").get_by_text(main_text, exact=True)).to_be_visible(
        timeout=30_000
    )
    await scenario.step(
        "Сообщение из основного чата отправлено",
        ui_page_system,
        label_en="Message sent from the main chat",
    )

    await _click_channel_call_button(ui_page_system)
    overlay = ui_page_system.locator("sync-call-overlay-modal")
    await expect(overlay).to_be_visible(timeout=30_000)
    await _ensure_overlay_chat_open(overlay)
    await expect(overlay.locator(".chat-text").get_by_text(main_text, exact=True)).to_be_visible(timeout=30_000)

    await overlay.locator("textarea.chat-input").fill(overlay_text)
    await overlay.locator("button.chat-send").click()
    await expect(overlay.locator(".chat-text").get_by_text(overlay_text, exact=True)).to_be_visible(
        timeout=30_000
    )
    await scenario.step(
        "Чат в оверлее принимает и отправляет сообщения",
        ui_page_system,
        label_en="Call overlay chat accepts and sends messages",
    )

    await overlay.locator("button.ctrl.hangup").click()
    await expect(ui_page_system.locator("sync-app")).not_to_have_attribute("data-call-active", "", timeout=30_000)
    await expect(ui_page_system.locator("sync-message-bubble").get_by_text(overlay_text, exact=True)).to_be_visible(
        timeout=30_000
    )
    await scenario.step(
        "Сообщение из оверлея видно в основном чате канала",
        ui_page_system,
        label_en="Message from the overlay is visible in the main channel chat",
    )


@pytest.mark.scenario(
    service="sync",
    tag="calls",
    doc_slug="adhoc-call-visible-channel",
    title="Sync: ad-hoc звонок использует обычный видимый канал",
    description=(
        "Кнопка «Создать Sync» создаёт канал встречи с читаемым именем (дата и время), чат в оверлее работает, "
        "а после переключения каналов сообщения встречи сохраняются в этом канале."
    ),
    title_en="Sync: ad-hoc call uses a normal visible channel",
    description_en=(
        "The «Create Sync» button creates a meeting channel with a readable name (date and time), "
        "chat works in the overlay, and after switching channels the meeting messages remain in that channel."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_adhoc_call_channel_is_visible_and_survives_channel_switch(
    scenario: ScenarioRecorder,
    sync_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    base_channel_name = f"Основной канал {unique_id}"
    adhoc_text = f"Adhoc сообщение {unique_id}"

    await sync_e2e_open_with_namespace(sync_ui, ui_page_system, unique_id, suffix="adhoc")
    await sync_e2e_create_topic_channel_and_open(
        ui_page_system,
        unique_id,
        channel_prefix="Основной канал",
    )

    await _install_call_trace(ui_page_system)
    await ui_page_system.locator(
        "sync-chat-list .header-action-btn"
    ).filter(
        has=ui_page_system.locator("platform-icon[name='phone-plus']")
    ).first.click()
    overlay = ui_page_system.locator("sync-call-overlay-modal")
    try:
        await expect(overlay).to_be_visible(timeout=30_000)
        await _ensure_overlay_chat_open(overlay)

        await overlay.locator("textarea.chat-input").fill(adhoc_text)
        await overlay.locator("button.chat-send").click()
        await expect(overlay.locator(".chat-text").get_by_text(adhoc_text, exact=True)).to_be_visible(
            timeout=30_000
        )
    except Exception:
        await _dump_call_trace(ui_page_system)
        raise

    header_title = (
        await ui_page_system.locator("sync-channel-page sync-chat-header .title").first.inner_text()
    ).strip()
    assert not header_title.startswith("meet_")
    assert any(ch.isdigit() for ch in header_title)
    await scenario.step(
        "Ad-hoc встреча создала видимый канал с именем по дате/времени",
        ui_page_system,
        label_en="Ad-hoc meeting created a visible channel named by date and time",
    )

    await overlay.locator("button.ctrl.hangup").click()
    await expect(ui_page_system.locator("sync-app")).not_to_have_attribute("data-call-active", "", timeout=30_000)

    await sync_sidebar_channel_nav(ui_page_system, base_channel_name).click()
    await expect(ui_page_system.locator("sync-channel-page")).to_be_visible()
    await sync_sidebar_channel_nav(ui_page_system, header_title).click()
    await expect(ui_page_system.locator("sync-message-bubble").get_by_text(adhoc_text, exact=True)).to_be_visible(
        timeout=30_000
    )
    await scenario.step(
        "После переключения каналов сообщения ad-hoc канала сохранены",
        ui_page_system,
        label_en="After switching channels, ad-hoc channel messages are preserved",
    )
