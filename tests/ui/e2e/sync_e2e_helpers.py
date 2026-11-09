"""Общие локаторы для E2E Sync (сайдбар vs шапка чата)."""

from __future__ import annotations

import asyncio
import json
import re

import httpx2
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Locator, Page, TimeoutError as PlaywrightTimeoutError, expect

from core.di.platform import PlatformDi
from tests.ui.e2e.ui_e2e_pwa import ui_e2e_dismiss_pwa_install_banner
from tests.ui.e2e_worker import ui_e2e_company_id


def _namespace_name(unique_id: str, suffix: str) -> str:
    safe_suffix = suffix.strip("_")
    return f"ns_{unique_id}_{safe_suffix}" if safe_suffix else f"ns_{unique_id}"


async def sync_e2e_seed_namespace(
    di: PlatformDi,
    unique_id: str,
    *,
    suffix: str = "ui",
    company_id: str | None = None,
) -> str:
    """Создаёт платформенный namespace для текущего UI-сценария."""
    from tests.sync.api._helpers import seed_namespace_via_repo

    resolved_company_id = company_id if company_id is not None else ui_e2e_company_id()
    namespace = _namespace_name(unique_id, suffix)
    return await seed_namespace_via_repo(di, resolved_company_id, namespace)


async def sync_e2e_activate_namespace_for_next_load(
    page: Page,
    namespace: str,
    *,
    company_id: str | None = None,
) -> None:
    """Запоминает namespace в localStorage до открытия SPA, как делает CRM/Sync sidebar."""
    resolved_company_id = company_id if company_id is not None else ui_e2e_company_id()
    company_json = json.dumps(resolved_company_id)
    namespace_json = json.dumps(namespace)
    await page.add_init_script(
        f"""
        (() => {{
            const key = 'platform:crm:last_namespace_by_company';
            let map = {{}};
            try {{
                const raw = window.localStorage.getItem(key);
                if (raw) {{
                    const parsed = JSON.parse(raw);
                    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) map = parsed;
                }}
            }} catch {{}}
            map[{company_json}] = {namespace_json};
            window.localStorage.setItem(key, JSON.stringify(map));
        }})();
        """
    )


async def sync_e2e_expect_namespace(page: Page, namespace: str, *, timeout: float = 10_000) -> None:
    field = page.locator("platform-sidebar-namespace-select").first
    await expect(field.locator("platform-field-enum input.field-pill-enum-input")).to_have_value(
        namespace,
        timeout=timeout,
    )


async def sync_e2e_expect_ws_open(page: Page) -> None:
    await page.wait_for_function(
        """() => {
            const bus = window.__PLATFORM_BUS__;
            if (!bus || typeof bus.getState !== 'function') return false;
            const state = bus.getState();
            return state?.network?.ws?.status === 'open';
        }""",
        timeout=30_000,
    )


async def sync_e2e_expect_namespace_in_list(page: Page, namespace: str, *, timeout: float = 10_000) -> None:
    """Ждёт namespace в slice syncNamespaces или officeNamespaces (до UI-выбора)."""
    already = await page.evaluate(
        """(namespaceName) => {
            const bus = window.__PLATFORM_BUS__;
            if (!bus || typeof bus.getState !== 'function') return false;
            const state = bus.getState();
            for (const key of ['syncNamespaces', 'officeNamespaces']) {
                const slice = state[key];
                if (!slice || !Array.isArray(slice.items)) continue;
                if (slice.items.some((item) => item && item.name === namespaceName)) {
                    return true;
                }
            }
            return false;
        }""",
        namespace,
    )
    if not already:
        await page.evaluate(
            """() => {
                const bus = window.__PLATFORM_BUS__;
                if (!bus || typeof bus.dispatch !== 'function') {
                    throw new Error('__PLATFORM_BUS__ недоступен для reload namespaces');
                }
                bus.dispatch('sync/namespaces/list_requested', null);
                bus.dispatch('office/namespaces/list_requested', null);
            }"""
        )
    await page.wait_for_function(
        """(namespaceName) => {
            const bus = window.__PLATFORM_BUS__;
            if (!bus || typeof bus.getState !== 'function') return false;
            const state = bus.getState();
            for (const key of ['syncNamespaces', 'officeNamespaces']) {
                const slice = state[key];
                if (!slice || !Array.isArray(slice.items)) continue;
                if (slice.items.some((item) => item && item.name === namespaceName)) {
                    return true;
                }
            }
            return false;
        }""",
        arg=namespace,
        timeout=timeout,
    )


async def sync_e2e_select_namespace(page: Page, namespace: str) -> None:
    await sync_e2e_expect_namespace_in_list(page, namespace, timeout=30_000)
    for attempt in range(3):
        try:
            field = page.locator("platform-sidebar-namespace-select").first
            input_box = field.locator("platform-field-enum input.field-pill-enum-input")
            await expect(input_box).to_be_visible(timeout=5_000)
            if await input_box.input_value(timeout=2_000) == namespace:
                return
            await input_box.click(timeout=5_000)
            await input_box.fill(namespace, timeout=5_000)
            option = field.locator(f'li[role="option"][data-enum-value="{namespace}"]')
            await expect(option).to_be_visible(timeout=5_000)
            # Enter надёжнее click: избегает гонки blur/willUpdate при обновлении config.
            await input_box.press("Enter")
            await sync_e2e_expect_namespace(page, namespace, timeout=5_000)
            return
        except (PlaywrightError, AssertionError):
            if attempt == 2:
                raise
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(300)


async def sync_e2e_dismiss_pwa_install_banner(page: Page) -> None:
    """Убирает pwa-install-banner (в т.ч. в shadow DOM PlatformApp)."""
    await ui_e2e_dismiss_pwa_install_banner(page)


async def sync_e2e_open_sync_defaults(page: Page) -> Locator:
    """Открывает ``sync.namespace_settings`` для company workspace ``default``."""
    gear = page.locator("sync-chat-list .header-action-btn").filter(
        has=page.locator('platform-icon[name="settings"]')
    ).first
    await expect(gear).to_be_visible(timeout=15_000)
    await gear.click()
    modal = page.locator("sync-namespace-modal")
    await expect(modal).to_be_visible(timeout=15_000)
    return modal


async def sync_e2e_open_with_namespace(
    sync_ui,
    page: Page,
    unique_id: str,
    *,
    suffix: str = "ui",
    company_id: str | None = None,
) -> str:
    """Открывает Sync shell. Возвращает ``default`` — workspace для seed каналов.

    ``unique_id``/``suffix``/``company_id`` сохранены для совместимости вызовов;
    Sync UI больше не переключает namespace.
    """
    _ = unique_id, suffix, company_id
    await sync_ui.open(page)
    await sync_ui.expect_shell(page)
    await sync_e2e_dismiss_pwa_install_banner(page)
    await sync_e2e_expect_ws_open(page)
    await expect(page.locator("sync-chat-list")).to_be_visible(timeout=30_000)
    await expect(page.locator("sync-chat-list platform-sidebar-namespace-select")).to_have_count(0)
    return "default"


async def sync_e2e_click_platform_button(
    scope: Page | Locator,
    *labels: str,
    timeout: float = 30_000,
) -> None:
    """Кликает по platform-button по видимому тексту slotted label."""
    if not labels:
        raise ValueError("Нужен хотя бы один текст кнопки.")
    exact_labels = "|".join(re.escape(label) for label in labels)
    label_pattern = re.compile(rf"^\s*(?:{exact_labels})\s*$")
    host = scope.locator("platform-button").filter(has_text=label_pattern).first
    await expect(host).to_be_visible(timeout=timeout)
    shadow_button = host.locator("button").first
    await expect(shadow_button).to_be_enabled(timeout=timeout)
    await shadow_button.click(no_wait_after=True)


def sync_sidebar_channel_row(page: Page, channel_name: str) -> Locator:
    """Host-строка канала в сайдбаре."""
    return page.locator("sync-sidebar").locator("sync-channel-row").filter(
        has_text=channel_name
    ).first


def sync_sidebar_channel_nav(page: Page, channel_name: str) -> Locator:
    """Кликабельная область выбора канала в сайдбаре."""
    return sync_sidebar_channel_row(page, channel_name).locator(".row-body").first


def sync_sidebar_channel_settings_gear(page: Page, channel_name: str) -> Locator:
    """Кнопка настроек канала в строке сайдбара."""
    return sync_sidebar_channel_row(page, channel_name).locator("button.gear").first


async def sync_e2e_click_create_channel(page: Page) -> None:
    """Открывает модалку создания канала: primary на shell (`sync-channel-picker`) или «+» в секции чатов сайдбара."""
    picker_ru = page.locator("sync-channel-picker").get_by_role("button", name="Создать канал")
    picker_en = page.locator("sync-channel-picker").get_by_role("button", name="Create channel")
    from_picker = picker_ru.or_(picker_en)
    from_sidebar = page.locator("sync-chat-list .section-action-btn").first
    target = from_picker.or_(from_sidebar)
    await expect(target).to_be_visible(timeout=30_000)
    await target.click()


async def _sync_page_auth_token(page: Page) -> str:
    cookies = await page.context.cookies()
    for cookie in cookies:
        if cookie.get("name") == "auth_token":
            value = cookie.get("value")
            if isinstance(value, str) and value.strip() != "":
                return value
    raise AssertionError("auth_token cookie обязателен для sync API seed канала")


async def _sync_page_origin(page: Page) -> str:
    origin = await page.evaluate("() => window.location.origin")
    if not isinstance(origin, str) or origin.strip() == "":
        raise AssertionError("window.location.origin обязателен для sync API seed")
    return origin


async def _sync_active_namespace(page: Page) -> str:
    """Workspace для API seed каналов в Sync E2E — всегда company ``default``."""
    _ = page
    return "default"


async def sync_api_create_group_channel(
    origin: str,
    auth_token: str,
    namespace: str,
    channel_name: str,
) -> str:
    async with _sync_client(origin, auth_token) as client:
        response = await client.post(
            "/sync/api/v1/channels/",
            json={
                "namespace": namespace,
                "type": "group",
                "name": channel_name,
                "is_private": False,
            },
        )
        response.raise_for_status()
        payload = response.json()
    channel_id = payload.get("channel_id")
    if not isinstance(channel_id, str) or channel_id.strip() == "":
        raise AssertionError("POST /channels/ должен вернуть channel_id")
    return channel_id


async def _sync_e2e_reload_channels(page: Page) -> None:
    await page.evaluate(
        """() => {
            const bus = window.__PLATFORM_BUS__;
            if (!bus || typeof bus.dispatch !== 'function') {
                throw new Error('__PLATFORM_BUS__ недоступен для reload sync/channels');
            }
            bus.dispatch('sync/channels/list_requested', null);
        }"""
    )


async def sync_e2e_create_topic_channel_and_open(
    page: Page,
    unique_id: str,
    *,
    channel_prefix: str = "Канал",
) -> str:
    """Создаёт групповой канал (API seed в активный namespace) и открывает чат."""
    await sync_e2e_dismiss_pwa_install_banner(page)
    channel_name = f"{channel_prefix} {unique_id}"
    namespace = await _sync_active_namespace(page)
    origin = await _sync_page_origin(page)
    auth_token = await _sync_page_auth_token(page)
    channel_id = await sync_api_create_group_channel(
        origin, auth_token, namespace, channel_name
    )
    await _sync_e2e_reload_channels(page)
    await expect(sync_sidebar_channel_nav(page, channel_name)).to_be_visible(timeout=30_000)
    # Список каналов обновляется push'ами и повторными LIST_REQUESTED: строка
    # может перебиндиться между resolve локатора и кликом, и _onClick строки
    # откроет другой канал. Проверяем channelId открывшейся страницы и при
    # промахе кликаем заново.
    for _attempt in range(5):
        await sync_sidebar_channel_nav(page, channel_name).click()
        try:
            await page.wait_for_function(
                """(cid) => {
                    const find = (root) => {
                        const el = root.querySelector && root.querySelector('sync-channel-page');
                        if (el) return el;
                        for (const n of root.querySelectorAll ? root.querySelectorAll('*') : []) {
                            if (n.shadowRoot) { const hit = find(n.shadowRoot); if (hit) return hit; }
                        }
                        return null;
                    };
                    const page = find(document);
                    return page !== null && page.channelId === cid;
                }""",
                arg=channel_id,
                timeout=6_000,
            )
            break
        except PlaywrightTimeoutError:
            continue
    else:
        raise AssertionError(
            f"Клик по каналу {channel_name!r} не открыл sync-channel-page с channel_id={channel_id}."
        )
    return channel_name


async def sync_e2e_create_topic_channel_in_current_space(page: Page, unique_id: str, *, channel_prefix: str) -> str:
    """Второй и следующие каналы в том же UI (API seed в активный namespace)."""
    await sync_e2e_dismiss_pwa_install_banner(page)
    channel_name = f"{channel_prefix} {unique_id}"
    namespace = await _sync_active_namespace(page)
    origin = await _sync_page_origin(page)
    auth_token = await _sync_page_auth_token(page)
    await sync_api_create_group_channel(origin, auth_token, namespace, channel_name)
    await _sync_e2e_reload_channels(page)
    await expect(sync_sidebar_channel_nav(page, channel_name)).to_be_visible(timeout=30_000)
    return channel_name


def _sync_client(origin: str, auth_token: str) -> httpx2.AsyncClient:
    from tests.ui.e2e_worker import ui_e2e_scope_headers

    return httpx2.AsyncClient(
        base_url=origin,
        cookies={"auth_token": auth_token},
        headers=ui_e2e_scope_headers(),
        timeout=60.0,
    )


async def sync_api_channel_id_by_name(origin: str, auth_token: str, channel_name: str) -> str:
    async with _sync_client(origin, auth_token) as client:
        r = await client.get("/sync/api/v1/channels/")
        r.raise_for_status()
        payload = r.json()
    if not isinstance(payload, dict) or "items" not in payload:
        raise AssertionError("GET /channels/ должен вернуть OffsetPage с полем items.")
    for ch in payload["items"]:
        if not isinstance(ch, dict) or ch.get("name") != channel_name:
            continue
        channel_id = ch.get("channel_id") or ch.get("id")
        if isinstance(channel_id, str) and channel_id:
            return channel_id
    raise AssertionError(f"Канал с именем {channel_name!r} не найден в API.")


async def sync_api_add_channel_member(
    origin: str,
    auth_token: str,
    channel_id: str,
    user_id: str,
    role: str = "member",
) -> None:
    async with _sync_client(origin, auth_token) as client:
        r = await client.post(
            f"/sync/api/v1/channels/{channel_id}/members",
            json={"user_id": user_id, "role": role},
        )
        r.raise_for_status()


async def sync_api_post_plain_message(
    origin: str,
    auth_token: str,
    channel_id: str,
    text: str,
) -> None:
    async with _sync_client(origin, auth_token) as client:
        r = await client.post(
            f"/sync/api/v1/channels/{channel_id}/messages",
            json={
                "thread_id": None,
                "parent_message_id": None,
                "contents": [
                    {"type": "text/plain", "data": {"body": text}, "order": 0},
                ],
            },
        )
        r.raise_for_status()


async def sync_api_react_to_message(
    origin: str,
    auth_token: str,
    channel_id: str,
    message_id: str,
    emoji: str,
) -> None:
    async with _sync_client(origin, auth_token) as client:
        r = await client.post(
            f"/sync/api/v1/channels/{channel_id}/messages/{message_id}/react",
            json={
                "channel_id": channel_id,
                "message_id": message_id,
                "emoji": emoji,
            },
        )
        r.raise_for_status()


async def sync_api_find_message_id_with_text(
    origin: str,
    auth_token: str,
    channel_id: str,
    substring: str,
    *,
    attempts: int = 12,
    delay_s: float = 0.25,
) -> str:
    last_error: AssertionError | None = None
    for attempt in range(attempts):
        async with _sync_client(origin, auth_token) as client:
            r = await client.get(f"/sync/api/v1/channels/{channel_id}/messages")
            r.raise_for_status()
            payload = r.json()
        if not isinstance(payload, dict):
            raise AssertionError("GET messages должен вернуть объект пагинации.")
        messages = payload.get("items")
        if not isinstance(messages, list):
            raise AssertionError("GET messages должен вернуть массив в поле items.")
        for m in messages:
            if not isinstance(m, dict):
                continue
            mid = m.get("message_id") if isinstance(m.get("message_id"), str) else m.get("id")
            contents = m.get("contents")
            if not isinstance(mid, str) or not isinstance(contents, list):
                continue
            for block in contents:
                if not isinstance(block, dict):
                    continue
                data = block.get("data")
                if isinstance(data, dict) and substring in str(data.get("body", "")):
                    return mid
        last_error = AssertionError(
            f"Сообщение с текстом, содержащим {substring!r}, не найдено."
        )
        if attempt + 1 < attempts:
            await asyncio.sleep(delay_s)
    if last_error is None:
        raise AssertionError(f"Сообщение с текстом, содержащим {substring!r}, не найдено.")
    raise last_error


async def sync_e2e_expect_team_member_loaded(page: Page, user_id: str, *, timeout: float = 30_000) -> None:
    """Ждёт появления участника компании в state.team.members (для profile modal / mentions)."""
    user_id_json = json.dumps(user_id)
    await page.wait_for_function(
        f"""() => {{
            const bus = window.__PLATFORM_BUS__;
            if (!bus || typeof bus.getState !== 'function') return false;
            const team = bus.getState().team;
            if (!team || !Array.isArray(team.members)) return false;
            return team.members.some((m) => m && m.user_id === {user_id_json});
        }}""",
        timeout=timeout,
    )


async def sync_e2e_expect_company_member_loaded(page: Page, user_id: str, *, timeout: float = 15_000) -> None:
    """Ждёт участника только в state.syncCompanyMembers.items (listFetchAllPages)."""
    await page.evaluate(
        """() => {
            const bus = window.__PLATFORM_BUS__;
            if (!bus || typeof bus.dispatch !== 'function') {
                throw new Error('__PLATFORM_BUS__ недоступен для reload company_members');
            }
            bus.dispatch('sync/company_members/list_requested', null);
        }"""
    )
    await page.wait_for_function(
        """(userId) => {
            const bus = window.__PLATFORM_BUS__;
            if (!bus || typeof bus.getState !== 'function') return false;
            const slice = bus.getState().syncCompanyMembers;
            return !!(slice && Array.isArray(slice.items)
                && slice.items.some((m) => m && m.user_id === userId));
        }""",
        arg=user_id,
        timeout=timeout,
    )
