"""Сервис оценки запасов — «книга стоимости» склада для бухгалтера.

Здесь отвечают на вопросы «сколько стоит остаток товара», «почему
сумма такая» и вносят ручные бухгалтерские поправки (переоценка,
сторно). Писать слои умеет только сам журнал: ``write_for_done_move``
в транзакции движения и ``write_adjustment`` для ручных записей.
Сервис — адаптер: читает журнал и формирует ручные записи через
``adjust_in_lane``.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from apps.stock.models import (
    StockProduct,
    StockQuant,
    StockTransfer,
    StockValueLayer,
    StockWarehouse,
    ValueEntryKind,
)
from apps.stock.models.api import (
    StockValuationLayersPage,
    StockValuationReportResponse,
    StockValuationReportRow,
)
from apps.stock.models.common import STOCK_DB
from apps.stock.models.valuation import quantize
from core.catalog.models import CatalogProduct
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.lanes import publish_lane_run
from core.request_scope import command_idempotency_key


class ProductValue:
    """Ответ «сколько стоит товар»: количество, сумма, средняя цена.

    ``quantity`` — остаток в штуках (из журнала по компании или по
    quant'ам склада); ``value`` — стоимость запаса в деньгах;
    ``avg_cost`` — средняя себестоимость единицы (value/quantity):
    «по сколько в среднем куплена штука, лежащая сейчас на складе».
    """

    def __init__(
        self,
        *,
        product_id: str,
        quantity: Decimal,
        value: Decimal,
        avg_cost: Decimal,
        warehouse_id: str | None,
    ) -> None:
        self.product_id: str = product_id
        self.quantity: Decimal = quantity
        self.value: Decimal = value
        self.avg_cost: Decimal = avg_cost
        self.warehouse_id: str | None = warehouse_id


async def _require_product(company_id: str, product_id: str) -> StockProduct:
    product = await StockProduct.by_id(company_id, product_id)
    if product is None:
        raise PlatformNotFoundError("Product not found", error_code="product_not_found")
    return product


class ValuationService:
    """Чтение журнала + `revalue`/`correction` (единственная точка ручных слоёв)."""

    async def list_layers(
        self,
        *,
        company_id: str,
        product_id: str | None,
        warehouse_id: str | None,
        transfer_id: str | None,
        entry_kinds: list[ValueEntryKind] | None,
        date_from: datetime | None,
        date_to: datetime | None,
        open_only: bool,
        search: str | None,
        limit: int,
        offset: int,
    ) -> StockValuationLayersPage:
        """Лента проводок журнала стоимости — «карточка счёта товара».

        Каждая строка — одна хозоперация с количеством, ценой и балансом
        «после»: история, по которой видно, откуда взялась текущая
        оценка (приходы по счетам, списания по себестоимости, ручные
        переоценки).

        ``search`` — умный поиск UI: текст совпадает с именем/SKU
        товара, номером накладной (``WH/IN/00001``), описанием или
        ``origin_document_id`` записи. В ответе — sidecar-карты имён
        товаров, накладных и складов для строк страницы.
        """
        search_text = search.strip() if search is not None else ""
        search_product_ids: list[str] | None = None
        search_transfer_ids: list[str] | None = None
        if search_text:
            search_product_ids = await CatalogProduct.list_ids_by_text_icontains(
                company_id, search_text
            )
            search_transfer_ids = await StockTransfer.list_ids_by_name_icontains(
                company_id, search_text
            )
        rows = await StockValueLayer.list_by_entry_no_asc(
            company_id,
            product_id=product_id,
            warehouse_id=warehouse_id,
            transfer_id=transfer_id,
            entry_kinds=entry_kinds,
            date_from=date_from,
            date_to=date_to,
            open_only=open_only,
            search_text=search_text if search_text else None,
            search_product_ids=search_product_ids,
            search_transfer_ids=search_transfer_ids,
            limit=limit,
            offset=offset,
        )
        total = await StockValueLayer.count_filtered(
            company_id,
            product_id=product_id,
            warehouse_id=warehouse_id,
            transfer_id=transfer_id,
            entry_kinds=entry_kinds,
            date_from=date_from,
            date_to=date_to,
            open_only=open_only,
            search_text=search_text if search_text else None,
            search_product_ids=search_product_ids,
            search_transfer_ids=search_transfer_ids,
        )
        product_ids = list({row.product_id for row in rows})
        transfer_ids = list(
            {row.transfer_id for row in rows if row.transfer_id is not None}
        )
        warehouse_ids = list(
            {row.warehouse_id for row in rows if row.warehouse_id is not None}
        )
        products = await CatalogProduct.found_in_company_by_ids(company_id, product_ids)
        transfers = await StockTransfer.found_in_company_by_ids(company_id, transfer_ids)
        warehouses = await StockWarehouse.found_in_company_by_ids(company_id, warehouse_ids)
        return StockValuationLayersPage(
            items=rows,
            total=total,
            limit=limit,
            offset=offset,
            product_names={pid: p.name for pid, p in products.items()},
            product_skus={
                pid: p.sku for pid, p in products.items() if p.sku is not None
            },
            transfer_names={tid: t.name for tid, t in transfers.items()},
            warehouse_names={wid: w.name for wid, w in warehouses.items()},
        )

    async def report_by_value_desc(
        self,
        *,
        company_id: str,
        warehouse_id: str | None,
        search: str | None,
        limit: int,
        offset: int,
    ) -> StockValuationReportResponse:
        """Отчёт «Стоимость запасов»: остаток каждого товара в деньгах.

        По компании — баланс из последнего слоя журнала товара (как
        ``product_value`` без склада). По складу — количество из
        quant'ов склада по средней себестоимости компании (как
        ``product_value`` со складом). ``search`` сужает товары по
        имени/SKU. Строки — только товары с ненулевым остатком,
        ``ORDER BY value DESC``.
        """
        search_text = search.strip() if search is not None else ""
        if warehouse_id is not None:
            warehouse = await StockWarehouse.by_id(company_id, warehouse_id)
            if warehouse is None:
                raise PlatformNotFoundError(
                    "Warehouse not found", error_code="warehouse_not_found"
                )
        latest = await StockValueLayer.latest_per_product_by_entry_no_desc(company_id)
        if search_text:
            allowed_ids = set(
                await CatalogProduct.list_ids_by_text_icontains(
                    company_id, search_text
                )
            )
            latest = [layer for layer in latest if layer.product_id in allowed_ids]
        products = await CatalogProduct.found_in_company_by_ids(
            company_id, [layer.product_id for layer in latest]
        )
        warehouse_qty: dict[str, Decimal] = {}
        if warehouse_id is not None:
            quants = await StockQuant.list_unordered_for_warehouse(
                company_id, warehouse_id
            )
            for quant in quants:
                warehouse_qty[quant.product_id] = (
                    warehouse_qty.get(quant.product_id, Decimal("0"))
                    + quant.quantity
                )
        rows: list[StockValuationReportRow] = []
        for layer in latest:
            product = products.get(layer.product_id)
            if product is None:
                continue
            if warehouse_id is not None:
                qty = warehouse_qty.get(layer.product_id, Decimal("0"))
            else:
                qty = layer.qty_after
            if qty <= Decimal("0"):
                continue
            avg = (
                quantize(layer.value_after / layer.qty_after)
                if layer.qty_after > Decimal("0")
                else Decimal("0")
            )
            value = layer.value_after if warehouse_id is None else quantize(avg * qty)
            rows.append(
                StockValuationReportRow(
                    product_id=layer.product_id,
                    name=product.name,
                    sku=product.sku,
                    quantity=qty,
                    avg_cost=avg,
                    value=value,
                )
            )
        rows.sort(key=lambda row: row.value, reverse=True)
        total_value = sum((row.value for row in rows), Decimal("0"))
        return StockValuationReportResponse(
            items=rows[offset : offset + limit],
            total_value=total_value,
            products_count=len(rows),
        )

    async def product_value(
        self,
        *,
        company_id: str,
        product_id: str,
        warehouse_id: str | None,
    ) -> ProductValue:
        """Оценка остатка одного товара — «сколько он стоит на складе».

        Без ``warehouse_id`` — по компании целиком: баланс из последней
        записи журнала (``qty_after``/``value_after``) — это и есть
        складская стоимость. С ``warehouse_id`` — количество считается
        по quant'ам склада (куда физически лежит), а цена берётся по
        средней себестоимости компании.
        """
        product = await StockProduct.by_id(company_id, product_id)
        if product is None:
            raise PlatformNotFoundError(
                "Product not found", error_code="product_not_found"
            )
        last = await StockValueLayer.last_for_product_by_entry_no_desc(company_id, product_id)
        total_value = last.value_after if last is not None else Decimal("0")
        total_qty = last.qty_after if last is not None else Decimal("0")
        if warehouse_id is not None:
            warehouse = await StockWarehouse.by_id(company_id, warehouse_id)
            if warehouse is None:
                raise PlatformNotFoundError(
                    "Warehouse not found", error_code="warehouse_not_found"
                )
            quants = await StockQuant.list_unordered_for_warehouse(company_id, warehouse_id)
            qty = sum(
                (q.quantity for q in quants if q.product_id == product_id),
                Decimal("0"),
            )
            avg = (
                quantize(total_value / total_qty)
                if total_qty > Decimal("0")
                else Decimal("0")
            )
            return ProductValue(
                product_id=product_id,
                quantity=qty,
                value=quantize(avg * qty),
                avg_cost=avg,
                warehouse_id=warehouse_id,
            )
        avg = (
            quantize(total_value / total_qty)
            if total_qty > Decimal("0")
            else Decimal("0")
        )
        return ProductValue(
            product_id=product_id,
            quantity=total_qty,
            value=total_value,
            avg_cost=avg,
            warehouse_id=None,
        )

    async def revalue(
        self,
        *,
        company_id: str,
        product_id: str,
        value_delta: Decimal | None,
        new_price: Decimal | None,
        description: str,
        idempotency_key: str | None = None,
        actor_user_id: str = "system",
        command_type: str = "stock/valuation/revalue_requested",
        causation_id: str | None = None,
    ) -> StockValueLayer:
        """Переоценка запаса — «переписать цену всего остатка товара».

        Два способа (ровно один обязателен):
          * ``value_delta`` — «добавь/убавь сумму запаса на N ₽»
            (уценка просрочки −3000 ₽);
          * ``new_price`` — «с этого момента единица стоит X ₽»:
            дельта вычисляется как ``new_price × остаток − текущая
            стоимость``.

        Пишется запись ``revaluation`` в журнал — количество не меняется
        (quantity_delta=0), только сумма. Нулевая дельта или пустой
        остаток — конфликт: переоценивать «ничего» бессмысленно.
        """
        if (value_delta is None) == (new_price is None):
            raise PlatformConflictError(
                "Pass exactly one of value_delta/new_price",
                error_code="revalue_input_invalid",
            )
        delta = value_delta
        if new_price is not None:
            last = await StockValueLayer.last_for_product_by_entry_no_desc(company_id, product_id)
            qty = last.qty_after if last is not None else Decimal("0")
            if qty <= Decimal("0"):
                raise PlatformConflictError(
                    "Cannot revalue by price with zero on-hand",
                    error_code="revalue_empty_stock",
                )
            current = last.value_after if last is not None else Decimal("0")
            delta = quantize(new_price * qty - current)
        if delta is None or delta == Decimal("0"):
            raise PlatformConflictError(
                "Revaluation delta is zero", error_code="revalue_delta_zero"
            )
        product = await _require_product(company_id, product_id)
        run = await StockValueLayer.adjust_in_lane(
            company_id=company_id,
            product_id=product_id,
            entry_kind=ValueEntryKind.REVALUATION,
            value_delta=delta,
            quantity_delta=Decimal("0"),
            description=description,
            origin_layer_id=None,
            valuation_method=product.valuation_method,
            idempotency_key=command_idempotency_key(idempotency_key),
            actor_user_id=actor_user_id,
            command_type=command_type,
            causation_id=causation_id,
        )
        await publish_lane_run(run, using=STOCK_DB)
        return run.result

    async def correction(
        self,
        *,
        company_id: str,
        origin_layer_id: str,
        quantity_delta: Decimal,
        value_delta: Decimal,
        description: str,
        idempotency_key: str | None = None,
        actor_user_id: str = "system",
        command_type: str = "stock/valuation/correction_requested",
        causation_id: str | None = None,
    ) -> StockValueLayer:
        """Сторно конкретной записи журнала — «исправляем ошибку».

        Указывает на ошибочную проводку (``origin_layer_id``) и пишет
        запись ``correction`` с дельтами количества/суммы — сторнировать
        можно и частично (исправили 2 из 10 шт по неверной цене).
        Исходная запись не трогается — история остаётся честной,
        исправление видно как отдельная запись со ссылкой.
        """
        origin = await StockValueLayer.by_id(company_id, origin_layer_id)
        if origin is None:
            raise PlatformNotFoundError(
                "Origin layer not found", error_code="layer_not_found"
            )
        product = await _require_product(company_id, origin.product_id)
        run = await StockValueLayer.adjust_in_lane(
            company_id=company_id,
            product_id=origin.product_id,
            entry_kind=ValueEntryKind.CORRECTION,
            value_delta=value_delta,
            quantity_delta=quantity_delta,
            description=description,
            origin_layer_id=origin_layer_id,
            valuation_method=product.valuation_method,
            idempotency_key=command_idempotency_key(idempotency_key),
            actor_user_id=actor_user_id,
            command_type=command_type,
            causation_id=causation_id,
        )
        await publish_lane_run(run, using=STOCK_DB)
        return run.result


