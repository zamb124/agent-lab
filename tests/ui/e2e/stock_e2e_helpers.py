"""Хелперы документационных UI-сценариев сервиса Stock.

UI склада — первый срез: справочники и журналы читаются таблицами, создают
данные операции (tools/интеграции). Подготовку документов сценарий выполняет
тем же транспортом, что и SPA — ``__PLATFORM_BUS__`` + ``<command>_succeeded``.
"""

from __future__ import annotations

import base64
import uuid
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page, ViewportSize, expect
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
    """Операция через ``__PLATFORM_BUS__`` с одним повтором на timeout:
    списки/чтения идемпотентны, а под параллельным прогоном shared-стек
    отвечает медленнее таймаута WS-команды — оператор на терминале
    физически сделал бы то же самое (потянул ещё раз)."""
    try:
        return await _stock_e2e_op_once(page, name, request_type, payload, timeout_ms=timeout_ms)
    except AssertionError as exc:
        if "'timeout'" not in str(exc):
            raise
        return await _stock_e2e_op_once(page, name, request_type, payload, timeout_ms=timeout_ms)


async def _stock_e2e_op_once(
    page: Page,
    name: str,
    request_type: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout_ms: float,
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


async def stock_e2e_pick_warehouse(page_el: Any, warehouse_name: str) -> None:
    """Выбор склада в toolbar-combobox settings-страницы."""
    combo = page_el.locator(".toolbar platform-searchable-combobox")
    input_el = combo.locator("input")
    await input_el.click()
    await input_el.fill("")
    option = combo.locator("li.item").filter(has_text=warehouse_name)
    await expect(option.first).to_be_visible(timeout=15_000)
    await option.first.click()


async def stock_e2e_open_transfer(page: Page, transfer_id: str) -> None:
    """Открывает карточку перевода кликом по строке журнала."""
    row = page.locator(f"stock-transfers-page tr[data-id='{transfer_id}']")
    await expect(row).to_be_visible(timeout=15_000)
    await row.click()
    await expect(page.locator("stock-transfer-page page-header")).to_be_visible(timeout=15_000)


async def stock_e2e_transfer_action(page: Page, button_index: int, op: str, state: str) -> None:
    """Действие карточки перевода: клик, исход op на bus, обновлённый state."""
    button = page.locator("stock-transfer-page page-header platform-button").nth(button_index)
    await expect(button).to_be_visible(timeout=10_000)
    await ui_click_and_wait_bus_op(page, button, op)
    await expect(page.locator("stock-transfer-page page-header")).to_contain_text(state, timeout=15_000)


# --- ТСД `/stock/tsd`: канал сканера, шаги машины, коммит -------------------

# ТСД — портретный экран терминала: сценарий снимается в формате
# реального устройства оператора.
TSD_VIEWPORT = ViewportSize(width=430, height=900)


async def tsd_scan(page: Page, code: str) -> None:
    """Скан через нативный канал: тот же вход, что DataWedge/intent
    Capacitor-оболочки и hardware-кейборд-сканер после эвристики."""
    await page.evaluate(
        "(code) => window.dispatchEvent("
        "new CustomEvent('stock/tsd:native_scan', { detail: { code } }))",
        code,
    )


async def tsd_wait_step(page: Page, step: str) -> None:
    """Ожидание шага скан-машины: оператор физически ждёт подсказку
    экрана перед следующим сканом — следующий шаг возможен только
    после ответа scan_step на предыдущий."""
    await page.wait_for_function(
        """(step) => {
            const s = window.__PLATFORM_BUS__.getState();
            return s.stockTsdSession?.context?.step === step;
        }""",
        arg=step,
        # Бюджет scan_step — 15s op + рендер: под параллельным
        # прогоном 15s ожидания — ниже реальной латентности шага.
        timeout=30_000,
    )


async def tsd_wait_ws_open(page: Page) -> None:
    """Realtime-канал платформы поднят: ресурсы/опы по WS уже ходят."""
    await page.wait_for_function(
        """() => {
            const bus = window.__PLATFORM_BUS__;
            if (!bus || typeof bus.getState !== 'function') return false;
            return bus.getState()?.network?.ws?.status === 'open';
        }""",
        timeout=30_000,
    )


async def tsd_open(page: Page, stock_ui: AppUI) -> None:
    # Под -n4 фронтенд-сервис на пике может не принять соединение —
    # физически терминал переподключается сам, повторяем навигацию.
    for _ in range(2):
        try:
            await page.goto(
                f"{stock_ui.origin}/stock/tsd", wait_until="domcontentloaded"
            )
            break
        except PlaywrightError:
            await page.wait_for_timeout(1_000)
    else:
        await page.goto(
            f"{stock_ui.origin}/stock/tsd", wait_until="domcontentloaded"
        )
    await expect(page.locator("stock-tsd-app")).to_be_visible(timeout=30_000)
    await expect(page.locator("stock-tsd-home-page")).to_be_visible(
        timeout=30_000
    )
    await tsd_wait_ws_open(page)
    # Баннер «Install … offline» перекрывает нижние контролы — гасим «Позже»,
    # если он всплыл; dismiss персистится в storage.
    later = page.locator("pwa-install-banner .btn-secondary")
    try:
        await later.click(timeout=3_000)
    except PlaywrightTimeoutError:
        pass


async def tsd_qty(page: Page, digits: str) -> None:
    """Набор количества на экранной клавиатуре + подтверждение."""
    for ch in digits:
        key = page.locator("stock-tsd-run .numpad button", has_text=ch).first
        await expect(key).to_be_visible(timeout=10_000)
        await key.click()
    ok = page.locator("stock-tsd-run .numpad button.ok")
    await expect(ok).to_be_enabled(timeout=10_000)
    await ok.click()


async def tsd_commit_click(page: Page) -> None:
    """Slide-to-commit: тянем бегунок до правого края трека, как оператор пальцем."""
    track = page.locator("stock-tsd-run .commit-btn")
    await expect(track).to_be_visible(timeout=10_000)
    await track.scroll_into_view_if_needed()
    track_box = await track.bounding_box()
    thumb_box = await track.locator(".commit-thumb").bounding_box()
    assert track_box is not None and thumb_box is not None
    start_x = thumb_box["x"] + thumb_box["width"] / 2
    start_y = thumb_box["y"] + thumb_box["height"] / 2
    await page.mouse.move(start_x, start_y)
    await page.mouse.down()
    await page.mouse.move(track_box["x"] + track_box["width"] - 4, start_y, steps=12)
    await page.mouse.up()


async def tsd_commit(page: Page) -> None:
    await tsd_commit_click(page)
    # Успешный коммит закрывает сессию — run-экран уходит, возвращается рабочий стол.
    await expect(page.locator("stock-tsd-run")).to_have_count(0, timeout=30_000)


# --- REST-зеркала stock op'ов: подготовка данных сценария -------------------


async def stock_rest(
    page: Page, method: str, path: str, payload: dict[str, Any] | None = None
) -> Any:
    """REST-зеркало stock op'ов для подготовки данных: у ТСД нет
    фабрик справочников, контракт тот же — `POST /stock/api/v1/...`."""
    parts = urlsplit(page.url)
    resp = await page.request.fetch(
        f"{parts.scheme}://{parts.netloc}/stock/api/v1{path}",
        method=method,
        data=payload,
    )
    assert resp.ok, f"{method} {path} → {resp.status}: {await resp.text()}"
    return await resp.json()


async def tsd_seed_product_image(
    page: Page, product_id: str, *, color: str, label: str
) -> str:
    """Присваивает товару картинку: рисует PNG в canvas страницы и грузит
    chunked Files API (`/stock/api/v1/files/uploads`), затем привязывает
    file_id через overlay карточки. Так карточки на скриншотах — с фото."""
    data_url: str = await page.evaluate(
        """({ color, label }) => {
            const canvas = document.createElement('canvas');
            canvas.width = 96; canvas.height = 96;
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = color;
            ctx.fillRect(0, 0, 96, 96);
            ctx.fillStyle = 'rgba(255,255,255,0.92)';
            ctx.beginPath(); ctx.arc(48, 42, 24, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = color;
            ctx.font = 'bold 18px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(label, 48, 49);
            ctx.fillStyle = 'rgba(0,0,0,0.5)';
            ctx.font = '11px sans-serif';
            ctx.fillText('ФОТО', 48, 84);
            return canvas.toDataURL('image/png');
        }""",
        {"color": color, "label": label},
    )
    content = base64.b64decode(data_url.split(",", 1)[1])
    parts = urlsplit(page.url)
    base = f"{parts.scheme}://{parts.netloc}/stock/api/v1/files/uploads"
    init = await page.request.post(
        base,
        data={
            "spec": {
                "source_kind": "product",
                "source_ref": {"product_id": product_id},
                "retention": {"kind": "product"},
                "post_create": {"is_public": False},
            },
            "original_name": f"product-{product_id}.png",
            "content_type": "image/png",
            "file_size": len(content),
        },
    )
    assert init.ok, f"upload init → {init.status}: {await init.text()}"
    upload = await init.json()
    put = await page.request.fetch(
        f"{base}/{upload['upload_id']}/parts/1",
        method="PUT",
        data=content,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert put.ok, f"upload part → {put.status}: {await put.text()}"
    done = await page.request.post(f"{base}/{upload['upload_id']}/complete")
    assert done.ok, f"upload complete → {done.status}: {await done.text()}"
    file_id = upload["file_id"]
    await stock_rest(
        page, "PATCH", f"/products/{product_id}",
        {"product_id": product_id, "overlay": {"image_file_ids": [file_id]}},
    )
    return str(file_id)


async def stock_quant_row(
    page: Page, warehouse_id: str, product_id: str, location_id: str
) -> dict[str, Any]:
    quants: dict[str, Any] = await stock_e2e_op(
        page,
        "stock/quants",
        "stock/quants/list_requested",
        {"warehouse_id": warehouse_id, "product_id": product_id},
    )
    rows = [q for q in quants["items"] if q["location_id"] == location_id]
    assert len(rows) == 1, f"ожидался quant {product_id}@{location_id}: {quants}"
    return rows[0]


async def stock_quant_qty(
    page: Page, warehouse_id: str, product_id: str, location_id: str
) -> Decimal:
    return Decimal(
        str((await stock_quant_row(page, warehouse_id, product_id, location_id))["quantity"])
    )


async def tsd_seed_warehouse(
    page: Page, unique_id: str
) -> dict[str, Any]:
    """Типовая топология ТСД-сценария: склад, зона-view, две ячейки
    с баркодами и два товара с баркодами. Данные создаются через
    REST-зеркала op'ов — тот же контракт, что и у SPA."""
    warehouse = await stock_rest(
        page, "POST", "/warehouses",
        {"code": f"0-{unique_id[:8].upper()}", "name": f"Склад {unique_id[:4]}"},
    )
    zone = await stock_rest(
        page, "POST", "/locations",
        {
            "warehouse_id": warehouse["warehouse_id"],
            "name": f"Зона {unique_id[:4]}",
            "usage": "view",
        },
    )
    bin_a = await stock_rest(
        page, "POST", "/locations",
        {
            "warehouse_id": warehouse["warehouse_id"],
            "parent_id": zone["location_id"],
            "name": f"Ячейка А{unique_id[:3]}",
            "usage": "bin",
            "barcode": f"BIN-A-{unique_id[:6]}",
        },
    )
    bin_b = await stock_rest(
        page, "POST", "/locations",
        {
            "warehouse_id": warehouse["warehouse_id"],
            "parent_id": zone["location_id"],
            "name": f"Ячейка Б{unique_id[:3]}",
            "usage": "bin",
            "barcode": f"BIN-B-{unique_id[:6]}",
        },
    )
    uoms = await stock_rest(page, "GET", "/uoms")
    uom_id = next(u["uom_id"] for u in uoms["items"] if u["name"] == "Units")
    product_1 = await stock_rest(
        page, "POST", "/products",
        {
            "name": f"Кофе зерновой {unique_id[:4]}",
            "sku": f"BEAN-{unique_id[:6]}",
            "uom_id": uom_id,
            "valuation_method": "fifo",
            "standard_price": "0",
            "tracking": "none",
            "is_storable": True,
            "barcodes": [f"BC-1-{unique_id[:6]}"],
        },
    )
    product_2 = await stock_rest(
        page, "POST", "/products",
        {
            "name": f"Чай листовой {unique_id[:4]}",
            "sku": f"TEA-{unique_id[:6]}",
            "uom_id": uom_id,
            "valuation_method": "fifo",
            "standard_price": "0",
            "tracking": "none",
            "is_storable": True,
            "barcodes": [f"BC-2-{unique_id[:6]}"],
        },
    )
    await tsd_seed_product_image(
        page, str(product_1["product_id"]), color="#b4690e", label="КОФЕ"
    )
    await tsd_seed_product_image(
        page, str(product_2["product_id"]), color="#2e7d46", label="ЧАЙ"
    )
    # Сущности созданы REST-зеркалом мимо витрины ресурса: push-события
    # для каталога нет, autoload склада уже отстрелял — перезагружаем
    # страницу, чтобы список складов подтянул созданный.
    await page.reload(wait_until="domcontentloaded")
    await expect(page.locator("stock-tsd-home-page")).to_be_visible(
        timeout=30_000
    )
    await tsd_wait_ws_open(page)
    return {
        "warehouse": warehouse,
        "zone": zone,
        "bin_a": bin_a,
        "bin_b": bin_b,
        "product_1": product_1,
        "product_2": product_2,
        "uom_id": uom_id,
    }


async def tsd_seed_stock(
    page: Page,
    warehouse_id: str,
    lines: list[dict[str, Any]],
) -> None:
    """Положить товар на локацию тем же adhoc-commit, что ходит с ТСД:
    многострочный receive-контекст → один входящий документ."""
    await stock_rest(
        page, "POST", "/scan/adhoc-commit",
        {
            "warehouse_id": warehouse_id,
            "operation_code": "incoming",
            "context": {
                "flow": "receive",
                "step": "review",
                "lines": [
                    {
                        "location_id": None,
                        "location_dest_id": line["location_dest_id"],
                        "product_id": line["product_id"],
                        "quantity": str(line["quantity"]),
                    }
                    for line in lines
                ],
            },
        },
    )


async def tsd_pick_warehouse(page: Page, unique_id: str) -> None:
    """Выбор склада текущего прогона: компания воркера общая, склады
    копятся между прогонами — кликаем карточку по имени, а не первую.
    Список складов грузится один раз при монтировании — перезагружаем
    страницу после сидирования, иначе свежий склад гонится с autoload."""
    await page.reload(wait_until="domcontentloaded")
    await expect(page.locator("stock-tsd-home-page")).to_be_visible(
        timeout=30_000
    )
    await tsd_wait_ws_open(page)
    card = page.locator(
        "stock-tsd-home-page .warehouse-card",
        # Имя `Склад {uid[:4]}` коллидирует между прогонами в общей
        # компании воркера — код `0-{uid[:8]}` уникален на прогон.
        has_text=f"0-{unique_id[:8].upper()}",
    )
    # Autoload списка мог стартовать до поднятия WS: при отказе страница
    # показывает ошибку с «Повторить» — физически оператор жмёт её.
    retry = page.locator("platform-empty-state platform-button")
    try:
        await expect(card).to_be_visible(timeout=15_000)
    except AssertionError:
        await expect(retry).to_be_visible(timeout=5_000)
        await retry.click()
        await expect(card).to_be_visible(timeout=30_000)
    await card.click()


async def tsd_seed_document(
    page: Page,
    warehouse_id: str,
    unique_id: str,
    moves: list[dict[str, Any]],
    *,
    code: str = "outgoing",
    scan_flow: str | None = None,
) -> dict[str, Any]:
    """Накладная с баркодом под ТСД-исполнение: тип операции по коду,
    при необходимости — явный поток плеча (pack/ship)."""
    op_types = await stock_rest(
        page, "GET", f"/operation-types?warehouse_id={warehouse_id}"
    )
    op_type = next(ot for ot in op_types["items"] if ot["code"] == code)
    if scan_flow is not None:
        op_type = await stock_rest(
            page, "PATCH", f"/operation-types/{op_type['operation_type_id']}",
            {"operation_type_id": op_type["operation_type_id"], "scan_flow": scan_flow},
        )
    transfer = await stock_rest(
        page, "POST", "/transfers",
        {
            "warehouse_id": warehouse_id,
            "operation_type_id": op_type["operation_type_id"],
            "barcode": f"DOC-{unique_id[:6]}",
            "moves": moves,
        },
    )
    await stock_rest(page, "POST", f"/transfers/{transfer['transfer_id']}/confirm")
    await stock_rest(page, "POST", f"/transfers/{transfer['transfer_id']}/assign")
    return transfer
