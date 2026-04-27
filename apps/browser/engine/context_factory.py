"""
Фабрика BrowserContext без глобального переиспользования.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from apps.browser.engine.types import ContextSignature
from apps.browser.stealth.playwright_stealth import apply_stealth_to_context


def _playwright_transport_gone(exc: BaseException) -> bool:
    """
    Playwright/CDP уже оборван (движок упал, закрыл сокет): close() не обязан повторно бросать.
    """
    try:
        from playwright._impl._errors import is_target_closed_error

        if isinstance(exc, Exception) and is_target_closed_error(exc):
            return True
    except Exception:
        pass
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


async def _safe_page_close(page: Any) -> None:
    try:
        await page.close()
    except Exception as exc:
        if _playwright_transport_gone(exc):
            return
        raise


async def _safe_context_close(context: Any) -> None:
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
    def _proxy_config(proxy_policy: str) -> Optional[dict[str, str]]:
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
        browser: Any,
        signature: ContextSignature,
        storage_state: Optional[dict[str, Any]],
    ) -> Any:
        async with self._lock:
            proxy = self._proxy_config(signature.proxy_policy)
            kwargs: dict[str, Any] = {}
            if signature.emulate_locale_timezone_via_cdp is False:
                # Некоторые CDP-движки (Lightpanda) не поддерживают создание отдельных
                # browser contexts (Target.createBrowserContext). В этом режиме используем
                # единственный уже существующий контекст.
                if storage_state is not None:
                    raise ValueError(
                        "storage_state не поддерживается, когда emulate_locale_timezone_via_cdp=False"
                    )
                contexts = getattr(browser, "contexts", None)
                if not isinstance(contexts, list) or len(contexts) == 0:
                    raise RuntimeError(
                        "Движок не поддерживает new_context и не предоставляет browser.contexts"
                    )
                context = contexts[0]
                try:
                    setattr(context, "_browser_runtime_shared_context", True)
                except Exception:
                    pass
                try:
                    setattr(context, "_browser_runtime_signature", signature)
                except Exception:
                    pass
                await apply_stealth_to_context(context, signature)
                return context
            if signature.emulate_locale_timezone_via_cdp:
                kwargs["locale"] = signature.locale
                kwargs["timezone_id"] = signature.timezone_id
            # Иначе не передаём locale/timezone: CDP (например Lightpanda) может не
            # поддерживать Emulation.setLocaleOverride / setTimezoneOverride.
            if proxy is not None:
                kwargs["proxy"] = proxy
            if signature.user_agent:
                kwargs["user_agent"] = signature.user_agent
            if storage_state is not None:
                kwargs["storage_state"] = storage_state
            context = await browser.new_context(**kwargs)
            try:
                setattr(context, "_browser_runtime_signature", signature)
            except Exception:
                pass
            await apply_stealth_to_context(context, signature)
            if signature.stealth_init_version:
                marker = json.dumps(signature.stealth_init_version)
                if signature.emulate_locale_timezone_via_cdp:
                    await context.add_init_script(
                        f"window.__browser_runtime_stealth = {marker};"
                    )
            return context

    async def new_page(self, context: Any) -> Any:
        async with self._lock:
            return await context.new_page()

    async def close_page(self, page: Any) -> None:
        await _safe_page_close(page)

    async def close_context(self, context: Any) -> None:
        if getattr(context, "_browser_runtime_shared_context", False) is True:
            return
        await _safe_context_close(context)
