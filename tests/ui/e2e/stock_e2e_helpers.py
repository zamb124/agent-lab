"""Хелперы документационных UI-сценариев сервиса Stock.

UI склада — первый срез: справочники и журналы читаются таблицами, создают
данные операции (tools/интеграции). Подготовку документов сценарий выполняет
тем же транспортом, что и SPA — ``__PLATFORM_BUS__`` + ``<command>_succeeded``.
"""

from __future__ import annotations

import uuid
from typing import Any

from playwright.async_api import Page, expect
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from tests.ui.harness import AppUI, ui_click_and_wait_bus_op


async def stock_e2e_op(
    page: Page,
    name: str,
    request_type: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout_ms: float = 30_000,
) -> Any:
    """Выполняет stock-операцию через ``__PLATFORM_BUS__``, возвращает результат.

    Dispatch ``request_type`` (``<name>/requested`` для async op,
    ``<name>/list_requested`` для коллекции) идёт тем же каналом, что и UI.
    Исход — событие фабрики: ``<name>/succeeded`` (payload ``{result, request}``)
    или ``<name>/list_loaded``; ``<name>/failed`` / ``<name>/list_failed`` — ошибка.
    """
    marker = f"__stockOp_{uuid.uuid4().hex}"
    await page.evaluate(
        """([m, name, requestType, payload]) => {
            const bus = window.__PLATFORM_BUS__;
            if (!bus || typeof bus.subscribeAny !== 'function') {
                throw new Error('__PLATFORM_BUS__ недоступен для stock op');
            }
            const done = [
                name + '/succeeded', name + '/failed',
                name + '/list_loaded', name + '/list_failed',
            ];
            window[m] = [];
            bus.subscribeAny((event) => {
                if (done.includes(event.type)) {
                    window[m].push({ type: event.type, payload: event.payload });
                }
            });
            bus.dispatch(requestType, payload);
        }""",
        [marker, name, request_type, payload],
    )
    try:
        handle = await page.wait_for_function(
            "(m) => (window[m] || []).length > 0 ? window[m][0] : false",
            arg=marker,
            timeout=timeout_ms,
        )
        event: dict[str, Any] = await handle.json_value()
    except PlaywrightTimeoutError as exc:
        raise AssertionError(f"Операция {request_type} не вернула succeeded/failed за {timeout_ms}мс") from exc
    if event["type"].endswith("/failed") or event["type"].endswith("/list_failed"):
        raise AssertionError(f"Операция {request_type} завершилась failed: {event['payload']}")
    result = event["payload"]
    if isinstance(result, dict) and "result" in result:
        return result["result"]
    return result


async def stock_e2e_open(page: Page, stock_ui: AppUI) -> None:
    """Открывает Stock SPA и ждёт shell + открытый WS (команды идут по Centrifugo)."""
    await stock_ui.open(page)
    await stock_ui.expect_shell(page)
    await page.wait_for_function(
        """() => {
            const bus = window.__PLATFORM_BUS__;
            if (!bus || typeof bus.getState !== 'function') return false;
            const state = bus.getState();
            return state?.network?.ws?.status === 'open';
        }""",
        timeout=30_000,
    )


async def stock_e2e_nav(page: Page, route_key: str, *, page_selector: str) -> None:
    """Переход по сайдбару nav-tree: клик по листу с ``data-route-key`` и ожидание страницы."""
    item = page.locator(f"stock-sidebar [data-route-key='{route_key}']")
    await expect(item).to_be_visible(timeout=10_000)
    await item.click()
    await expect(page.locator(page_selector)).to_be_visible(timeout=15_000)


async def stock_e2e_open_transfer(page: Page, transfer_id: str) -> None:
    """Открывает карточку перевода кликом по строке журнала."""
    row = page.locator(f"stock-transfers-page tr[data-id='{transfer_id}']")
    await expect(row).to_be_visible(timeout=15_000)
    await row.click()
    await expect(page.locator("stock-transfer-page h1")).to_be_visible(timeout=15_000)


async def stock_e2e_transfer_action(page: Page, button_index: int, op: str, state: str) -> None:
    """Действие карточки перевода: клик, исход op на bus, обновлённый state."""
    button = page.locator("stock-transfer-page .actions platform-button").nth(button_index)
    await expect(button).to_be_visible(timeout=10_000)
    await ui_click_and_wait_bus_op(page, button, op)
    await expect(page.locator("stock-transfer-page .state")).to_contain_text(state, timeout=15_000)
