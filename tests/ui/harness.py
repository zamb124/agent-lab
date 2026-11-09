"""Обёртка Playwright (async) над реестром SERVICE_UI_REGISTRY: открытие SPA и проверка shell."""

from __future__ import annotations

import os
import uuid
from typing import Literal

from playwright.async_api import Locator, Page, expect
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from tests.ui.apps import ServiceUiSpec
from tests.ui.e2e_worker import resolve_ui_e2e_host_subdomain


def ui_e2e_use_lvh_me() -> bool:
    raw = os.environ.get("UI_E2E_USE_LVH_ME", "")
    return raw.lower() in {"1", "true", "yes"}


class AppUI:
    """Доступ к одному сервису по фиксированному ServiceUiSpec."""

    def __init__(self, spec: ServiceUiSpec) -> None:
        self._spec = spec

    @property
    def spec(self) -> ServiceUiSpec:
        return self._spec

    def _host(self) -> str:
        subdomain = resolve_ui_e2e_host_subdomain(self._spec.subdomain_prefix)
        if ui_e2e_use_lvh_me():
            return f"{subdomain}.lvh.me"
        if subdomain != "system" or self._spec.subdomain_prefix:
            return f"{subdomain}.localhost"
        return "localhost"

    @property
    def origin(self) -> str:
        return f"http://{self._host()}:{self._spec.port}"

    @property
    def apex_origin(self) -> str:
        """Origin платформы без company subdomain: публичный landing и system-виджеты."""
        host = "lvh.me" if ui_e2e_use_lvh_me() else "localhost"
        return f"http://{host}:{self._spec.port}"

    def spa_url(self) -> str:
        path = self._spec.spa_path
        if not path.startswith("/"):
            raise ValueError(f"spa_path must start with /: {path!r}")
        return f"{self.origin}{path}"

    async def open(self, page: Page, *, wait_until: Literal["commit", "domcontentloaded", "load", "networkidle"] = "domcontentloaded") -> None:
        await page.goto(self.spa_url(), wait_until=wait_until)

    async def expect_shell(self, page: Page, *, timeout_ms: int = 30_000) -> None:
        await expect(page.locator(self._spec.shell_selector)).to_be_visible(timeout=timeout_ms)
        if self._spec.title is not None:
            await expect(page).to_have_title(self._spec.title, timeout=timeout_ms)


async def ui_click_and_wait_bus_op(
    page: Page,
    button: Locator,
    op_name: str,
    *,
    timeout_ms: int = 30_000,
) -> None:
    """Клик по кнопке ws-transport op + ожидание ``<op>/succeeded`` на bus.

    Команды ``transport: 'ws'`` идут через Centrifugo RPC — HTTP-зеркала для
    expect_response нет. Исход проверяем по событию на ``__PLATFORM_BUS__``.
    """
    marker = f"__uiBusOp_{uuid.uuid4().hex}"
    await page.evaluate(
        """(m) => {
            const bus = window.__PLATFORM_BUS__;
            if (!bus || typeof bus.subscribeAny !== 'function') {
                throw new Error('__PLATFORM_BUS__ недоступен для ожидания исхода op');
            }
            window[m] = [];
            bus.subscribeAny((event) => { window[m].push(event.type); });
        }""",
        marker,
    )
    await button.click()
    succeeded = f"{op_name}/succeeded"
    failed = f"{op_name}/failed"
    result: str | None = None
    try:
        handle = await page.wait_for_function(
            """([m, ok, bad]) => {
                const types = window[m] || [];
                if (types.includes(bad)) return 'failed';
                return types.includes(ok) ? 'ok' : false;
            }""",
            arg=[marker, succeeded, failed],
            timeout=timeout_ms,
        )
        result = await handle.json_value()
    except PlaywrightTimeoutError as exc:
        seen = await page.evaluate(f"window[{marker!r}] || []")
        raise AssertionError(
            f"Клик не привёл к {succeeded}: событий на bus нет — {seen}"
        ) from exc
    if result == 'failed':
        seen = await page.evaluate(f"window[{marker!r}] || []")
        raise AssertionError(f"Операция завершилась {failed}: события bus — {seen}")


async def ui_set_platform_field(field: Locator, value: str) -> None:
    """Заполняет ``platform-field``: реальный ввод + ``change``-событие компонента.

    ``platform-field`` может держать скрытые служебные input при смене
    renderer'ов — работаем только с видимым контролом, а затем дублируем
    ``.value`` и ``change``, чтобы состояние компонента гарантированно
    обновилось (поведение идентично ``flows_set_platform_field``).
    """
    await expect(field).to_be_visible(timeout=5_000)
    editable = field.locator("input:visible, textarea:visible").first
    if await editable.count() > 0:
        await editable.fill(value)
    await field.evaluate(
        """
        (el, value) => {
            el.value = value;
            if (typeof el.requestUpdate === 'function') el.requestUpdate();
            el.dispatchEvent(new CustomEvent('change', {
                detail: { value },
                bubbles: true,
                composed: true,
            }));
        }
        """,
        value,
    )
    if await editable.count() > 0:
        await expect(editable).to_have_value(value, timeout=5_000)
