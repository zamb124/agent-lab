"""
Фабрика BrowserContext без глобального переиспользования.
"""

from __future__ import annotations

import asyncio

from playwright._impl._errors import is_target_closed_error
from playwright.async_api import ProxySettings

from apps.browser.engine.types import (
    BrowserContextHandle,
    BrowserHandle,
    BrowserPage,
    BrowserStorageState,
    ContextSignature,
)
from apps.browser.stealth.playwright_stealth import apply_stealth_to_context


def _playwright_transport_gone(exc: BaseException) -> bool:
    """
    Playwright/CDP уже оборван (движок упал, закрыл сокет): close() не обязан повторно бросать.
    """
    if isinstance(exc, Exception) and is_target_closed_error(exc):
        return True
    msg = str(exc).lower()
    return any(
        part in msg
        for part in (
            "connection closed",
            "closed while reading",
            "target closed",
            "browser has been closed",
            "websocket",
        )
    )


async def _safe_page_close(page: BrowserPage) -> None:
    try:
        await page.close()
    except Exception as exc:
        if _playwright_transport_gone(exc):
            return
        raise


async def _safe_context_close(context: BrowserContextHandle) -> None:
    try:
        await context.close()
    except Exception as exc:
        if _playwright_transport_gone(exc):
            return
        raise


class ContextFactory:
    """
    Фабрика BrowserContext, ориентированная на строгую изоляцию.

    Мотивация:
    - Создание BrowserContext дорогое, а большинство задач повторяют одинаковый
      профиль (proxy/ua/locale/storage policy).
    - Runtime использует модель "одна бизнес-сессия = один BrowserContext":
      переиспользование контекста между сессиями отключено.

    Связи:
    - Используется `PageLeaseManager` для создания контекстов и вкладок (page).
    - Опирается на `ContextSignature` как каноничный ключ изоляции контекста.

    Важно про границу ответственности:
    - Этот класс не хранит кэш и не знает про `session_id`.
    - Политика "какой контекст принадлежит какой сессии" находится в `PageLeaseManager`.

    Состояние:
    - `_lock`: защита от гонок при конкурентном создании/закрытии контекстов.

    Инварианты:
    - `new_context()` создаёт новый BrowserContext.
    - Закрытие (`close_page/close_context`) не должно падать на "transport gone".

    Переиспользование:
    - Стоит: когда нужна строгая изоляция выполнения.
    - Возможно: реюз контекстов можно вернуть позже как отдельный слой оптимизации.
    """
    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    @staticmethod
    def _proxy_config(proxy_policy: str) -> ProxySettings | None:
        if not proxy_policy:
            return None
        if (
            proxy_policy.startswith("http://")
            or proxy_policy.startswith("https://")
            or proxy_policy.startswith("socks5://")
        ):
            return {"server": proxy_policy}
        return None

    async def new_context(
        self,
        browser: BrowserHandle,
        endpoint_key: str,
        signature: ContextSignature,
        storage_state: BrowserStorageState | None,
    ) -> BrowserContextHandle:
        async with self._lock:
            proxy = self._proxy_config(signature.proxy_policy)
            context = await browser.new_context(
                locale=signature.locale,
                timezone_id=signature.timezone_id,
                proxy=proxy,
                user_agent=signature.user_agent,
                storage_state=storage_state,
            )
            try:
                setattr(context, "_browser_runtime_shared_context", True)
            except Exception:
                pass
            try:
                setattr(context, "_browser_runtime_signature", signature)
            except Exception:
                pass
            try:
                setattr(context, "_browser_runtime_endpoint_key", endpoint_key)
            except Exception:
                pass
            await apply_stealth_to_context(context, signature)
            return context

    async def new_page(self, context: BrowserContextHandle) -> BrowserPage:
        async with self._lock:
            page = await context.new_page()

            return page

    async def close_page(self, page: BrowserPage) -> None:
        await _safe_page_close(page)

    async def close_context(self, context: BrowserContextHandle) -> None:
        await _safe_context_close(context)
