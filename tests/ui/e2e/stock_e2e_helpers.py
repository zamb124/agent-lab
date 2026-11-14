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
    await expect(page.locator("stock-transfer-page page-header")).to_be_visible(timeout=15_000)


async def stock_e2e_seed_product_image(
    page: Page,
    product_id: str,
    *,
    color: str = "#5b8def",
) -> str:
    """Присваивает товару сгенерированную картинку (chunked Files API + overlay).

    Рисует цветной квадрат 96×96 в canvas страницы и грузит его тем же
    путём, что и SPA: init ``/uploads`` → PUT part → complete, затем
    ``stock/product_update`` с ``overlay.image_file_ids``. Возвращает file_id.
    """
    file_id = await page.evaluate(
        """async ({ productId, color }) => {
            const canvas = document.createElement('canvas');
            canvas.width = 96; canvas.height = 96;
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = color;
            ctx.fillRect(0, 0, 96, 96);
            ctx.fillStyle = 'rgba(255,255,255,0.9)';
            ctx.beginPath();
            ctx.arc(48, 40, 22, 0, Math.PI * 2);
            ctx.fill();
            ctx.fillStyle = color;
            ctx.font = 'bold 20px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('SKU', 48, 47);
            ctx.fillStyle = 'rgba(0,0,0,0.55)';
            ctx.font = '12px sans-serif';
            ctx.fillText(productId.slice(-6), 48, 82);
            const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'));
            if (blob === null) throw new Error('canvas.toBlob вернул null');
            const buf = await blob.arrayBuffer();
            const spec = {
                source_kind: 'product',
                source_ref: { product_id: productId },
                retention: { kind: 'product' },
                post_create: { is_public: false },
            };
            const init = await fetch('/stock/api/v1/files/uploads', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    spec,
                    original_name: `product-${productId}.png`,
                    content_type: 'image/png',
                    file_size: buf.byteLength,
                }),
            });
            if (!init.ok) throw new Error(`upload init: ${init.status} ${await init.text()}`);
            const { upload_id, file_id } = await init.json();
            const put = await fetch(`/stock/api/v1/files/uploads/${upload_id}/parts/1`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/octet-stream' },
                body: buf,
            });
            if (!put.ok) throw new Error(`upload part: ${put.status} ${await put.text()}`);
            const done = await fetch(`/stock/api/v1/files/uploads/${upload_id}/complete`, {
                method: 'POST',
            });
            if (!done.ok) throw new Error(`upload complete: ${done.status} ${await done.text()}`);
            return file_id;
        }""",
        {"productId": product_id, "color": color},
    )
    if not isinstance(file_id, str) or file_id == "":
        raise AssertionError(f"seed product image: file_id не получен ({file_id!r})")
    await stock_e2e_op(
        page,
        "stock/product_update",
        "stock/products/update_requested",
        {"product_id": product_id, "overlay": {"image_file_ids": [file_id]}},
    )
    return file_id


async def stock_e2e_transfer_action(page: Page, button_index: int, op: str, state: str) -> None:
    """Действие карточки перевода: клик, исход op на bus, обновлённый state."""
    button = page.locator("stock-transfer-page page-header platform-button").nth(button_index)
    await expect(button).to_be_visible(timeout=10_000)
    await ui_click_and_wait_bus_op(page, button, op)
    await expect(page.locator("stock-transfer-page page-header")).to_contain_text(state, timeout=15_000)
