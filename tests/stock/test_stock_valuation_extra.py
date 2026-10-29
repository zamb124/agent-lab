"""Оценка запаса — деньги на границе склада.

Бизнес-правила под тестом (математика журнала ``stock_value_layers``):

* ``unvalued``-товар двигается по quant'ам, но журнал пуст —
  мы его храним, но в деньгах не считаем;
* консигнация (``owner_entity_id``): полка наша, товар чужой —
  quant под владельцем есть, записи журнала нет;
* внутреннее перемещение bin→bin денег не трогает — стоимость
  привязана к товару, а не к полке;
* FIFO: расход ест приходные слои от старых к новым, развязка
  пишется в ``stock_value_layer_consumptions``;
* AVERAGE: цена отгрузки — скользящая средняя (Σvalue/Σqty на
  момент документа);
* STANDARD: приход по цене документа, расход по карточной цене;
* переоценка меняет только сумму (qty_after не двигается),
  сторно ссылается на исправляемую запись;
* running balance ``qty_after``/``value_after`` — бесшовный:
  каждая запись = прошлый баланс + своя дельта, номера entry_no
  без дыр;
* физический остаток (Σ quant'ов) обязан сходиться с
  бухгалтерским ``qty_after`` последней записи — иначе деньги
  и полки разъехались.
"""

from decimal import Decimal

import pytest

from apps.stock.models.common import StockMoveSpec
from apps.stock.models.enums import (
    StockLayoutPreset,
    StockLocationUsage,
    StockOperationCode,
    StockRemovalStrategy,
    StockTracking,
    ValuationMethod,
    ValuationPriceSource,
    ValueEntryKind,
)
from apps.stock.models.quant import StockQuant
from apps.stock.models.value_layer import StockValueLayer
from apps.stock.models.value_layer_consumption import (
    StockValueLayerConsumption,
)
from core.errors.boundary import PlatformNotFoundError

from .test_stock_domain import (
    StockEnv,
    _delivery,
    _layers,
    _make_env,
    _receipt,
    _stock_quant,
)


async def _env(
    stock_di, unique_id: str, valuation=ValuationMethod.FIFO
) -> StockEnv:
    return await _make_env(
        stock_di, f"co-{unique_id}", unique_id, valuation
    )


async def _product(
    env: StockEnv,
    suffix: str,
    *,
    valuation: ValuationMethod,
    standard_price: Decimal = Decimal("0"),
    tracking: StockTracking = StockTracking.NONE,
):
    return await env.di.catalog_service.create_product(
        company_id=env.company_id,
        name=f"P{suffix}",
        sku=f"SKU-{suffix}",
        uom_id=env.uom_id,
        valuation_method=valuation,
        standard_price=standard_price,
        tracking=tracking,
        is_storable=True,
        category="general",
        barcode=None,
    )


async def _receipt_for(
    env: StockEnv,
    product_id: str,
    qty: Decimal,
    unit_price: Decimal | None,
    *,
    owner_entity_id: str | None = None,
) -> str:
    """Приход поставщика на основной запас склада; возвращает transfer_id."""
    op = env.op_types[StockOperationCode.INCOMING]
    transfer = await env.di.move_engine.create_transfer(
        company_id=env.company_id,
        warehouse_id=env.warehouse.warehouse_id,
        operation_type_id=op.operation_type_id,
        partner_entity_id=None,
        owner_entity_id=owner_entity_id,
        scheduled_at=None,
        origin_document_type=None,
        origin_document_id=None,
        barcode=None,
        moves=[
            StockMoveSpec(
                product_id=product_id,
                product_qty=qty,
                uom_id=env.uom_id,
                unit_price=unit_price,
            )
        ],
    )
    for step in ("confirm", "assign", "validate"):
        _ = await getattr(env.di.move_engine, f"{step}_transfer")(
            company_id=env.company_id,
            transfer_id=transfer.transfer_id,
        )
    return transfer.transfer_id


async def _delivery_for(
    env: StockEnv,
    product_id: str,
    qty: Decimal,
    *,
    owner_entity_id: str | None = None,
) -> str:
    op = env.op_types[StockOperationCode.OUTGOING]
    transfer = await env.di.move_engine.create_transfer(
        company_id=env.company_id,
        warehouse_id=env.warehouse.warehouse_id,
        operation_type_id=op.operation_type_id,
        partner_entity_id=None,
        owner_entity_id=owner_entity_id,
        scheduled_at=None,
        origin_document_type=None,
        origin_document_id=None,
        barcode=None,
        moves=[
            StockMoveSpec(
                product_id=product_id,
                product_qty=qty,
                uom_id=env.uom_id,
            )
        ],
    )
    for step in ("confirm", "assign", "validate"):
        _ = await getattr(env.di.move_engine, f"{step}_transfer")(
            company_id=env.company_id,
            transfer_id=transfer.transfer_id,
        )
    return transfer.transfer_id


async def _layers_for(env: StockEnv, product_id: str) -> list[StockValueLayer]:
    return await StockValueLayer.objects.filter(
        company_id=env.company_id, product_id=product_id
    ).order_by("entry_no").all()


class TestUnvalued:
    """``unvalued`` — храним, но в деньгах не считаем."""

    async def test_receipt_delivery_move_quant_without_layers(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        product = await _product(
            env, f"nv-{unique_id}", valuation=ValuationMethod.UNVALUED
        )
        _ = await _receipt_for(
            env, product.product_id, Decimal("5"), Decimal("10")
        )
        quant = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=product.product_id,
            location_id=env.warehouse.stock_location_id,
            lot_id=None,
            owner_entity_id=None,
        )
        assert quant is not None
        assert quant.quantity == Decimal("5")
        _ = await _delivery_for(env, product.product_id, Decimal("2"))
        assert await _layers_for(env, product.product_id) == []
        quant = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=product.product_id,
            location_id=env.warehouse.stock_location_id,
            lot_id=None,
            owner_entity_id=None,
        )
        assert quant.quantity == Decimal("3")


class TestConsigned:
    """Ответхранение: наш склад, чужой товар — журнала нет."""

    async def test_consigned_receipt_no_layer_quant_under_owner(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt_for(
            env,
            env.product.product_id,
            Decimal("4"),
            Decimal("10"),
            owner_entity_id="ent-supplier",
        )
        owned = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=env.warehouse.stock_location_id,
            lot_id=None,
            owner_entity_id="ent-supplier",
        )
        free = await _stock_quant(env)
        assert owned is not None and owned.quantity == Decimal("4")
        assert free is None or free.quantity == Decimal("0")
        assert await _layers(env) == []

    async def test_consigned_delivery_consumes_owned_quant(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt_for(
            env,
            env.product.product_id,
            Decimal("4"),
            Decimal("10"),
            owner_entity_id="ent-supplier",
        )
        _ = await _delivery_for(
            env,
            env.product.product_id,
            Decimal("3"),
            owner_entity_id="ent-supplier",
        )
        owned = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=env.warehouse.stock_location_id,
            lot_id=None,
            owner_entity_id="ent-supplier",
        )
        assert owned.quantity == Decimal("1")
        # Чужой товар уехал к владельцу — наших денег это не коснулось.
        assert await _layers(env) == []


class TestInternalMove:
    """Полка→полка: физика переехала, деньги стоят."""

    async def test_bin_to_bin_writes_no_layer(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        # Ячейка создаётся ПОСЛЕ прихода: иначе putaway-рефлекс приёмки
        # волен выбрать её, и остаток ляжет не туда, откуда ждёт тест.
        _ = await _receipt(env, Decimal("5"), Decimal("4"))
        bin_b = await env.di.topology_service.create_location(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            parent_id=env.warehouse.view_location_id,
            name=f"BIN-B-{unique_id}",
            usage=StockLocationUsage.BIN,
            barcode=None,
        )
        before = await _layers(env)
        internal = env.op_types[StockOperationCode.INTERNAL]
        transfer = await env.di.move_engine.create_transfer(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            operation_type_id=internal.operation_type_id,
            partner_entity_id=None,
            owner_entity_id=None,
            scheduled_at=None,
            origin_document_type=None,
            origin_document_id=None,
            barcode=None,
            moves=[
                StockMoveSpec(
                    product_id=env.product.product_id,
                    product_qty=Decimal("2"),
                    uom_id=env.uom_id,
                    location_dest_id=bin_b.location_id,
                )
            ],
        )
        for step in ("confirm", "assign", "validate"):
            _ = await getattr(env.di.move_engine, f"{step}_transfer")(
                company_id=env.company_id,
                transfer_id=transfer.transfer_id,
            )
        # Товар физически переехал: 3 на основном запасе, 2 в BIN-B.
        src = await _stock_quant(env)
        dst = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=env.product.product_id,
            location_id=bin_b.location_id,
            lot_id=None,
            owner_entity_id=None,
        )
        assert src.quantity == Decimal("3")
        assert dst.quantity == Decimal("2")
        # А в журнале ни одной новой записи — деньги не менялись.
        assert await _layers(env) == before


class TestStandard:
    """STANDARD: приход по первичке, расход по учётной цене карточки."""

    async def test_outbound_uses_card_price_not_receipt_price(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id, ValuationMethod.STANDARD)
        env.product = await _product(
            env,
            f"std-{unique_id}",
            valuation=ValuationMethod.STANDARD,
            standard_price=Decimal("5"),
        )
        _ = await _receipt_for(
            env, env.product.product_id, Decimal("2"), Decimal("10")
        )
        _ = await _delivery_for(env, env.product.product_id, Decimal("1"))
        layers = await _layers(env)
        inbound = next(layer for layer in layers if layer.entry_kind == ValueEntryKind.INBOUND)
        outbound = next(layer for layer in layers if layer.entry_kind == ValueEntryKind.OUTBOUND)
        # Приход по счёту поставщика (10), списание по карточке (5).
        assert inbound.unit_cost == Decimal("10")
        assert outbound.unit_cost == Decimal("5")
        assert outbound.value == Decimal("-5")
        # На остатке 1 шт; баланс журнала 20 − 5 = 15.
        assert layers[-1].qty_after == Decimal("1")
        assert layers[-1].value_after == Decimal("15")

    async def test_receipt_without_price_uses_card_price(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id, ValuationMethod.STANDARD)
        env.product = await _product(
            env,
            f"std2-{unique_id}",
            valuation=ValuationMethod.STANDARD,
            standard_price=Decimal("7"),
        )
        _ = await _receipt_for(
            env, env.product.product_id, Decimal("3"), None
        )
        (layer,) = await _layers(env)
        assert layer.unit_cost == Decimal("7")
        assert layer.value == Decimal("21")
        assert layer.price_source == ValuationPriceSource.STANDARD


class TestAverage:
    """AVERAGE: каждая отгрузка ценится по текущей средней."""

    async def test_outbound_at_weighted_average(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id, ValuationMethod.AVERAGE)
        _ = await _receipt(env, Decimal("2"), Decimal("10"))
        _ = await _receipt(env, Decimal("2"), Decimal("20"))
        # 4 шт за 60 → средняя 15.
        _ = await _delivery(env, Decimal("2"))
        layers = await _layers(env)
        outbound = next(layer for layer in layers if layer.entry_kind == ValueEntryKind.OUTBOUND)
        assert outbound.unit_cost == Decimal("15")
        assert outbound.value == Decimal("-30")
        assert layers[-1].qty_after == Decimal("2")
        assert layers[-1].value_after == Decimal("30")

    async def test_product_value_reports_average(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id, ValuationMethod.AVERAGE)
        _ = await _receipt(env, Decimal("2"), Decimal("10"))
        _ = await _receipt(env, Decimal("2"), Decimal("20"))
        pv = await env.di.valuation_service.product_value(
            company_id=env.company_id,
            product_id=env.product.product_id,
            warehouse_id=None,
        )
        assert pv.quantity == Decimal("4")
        assert pv.value == Decimal("60")
        assert pv.avg_cost == Decimal("15")


class TestFifoConsumption:
    """FIFO-развязка: видно, какая приходная запись съедена отгрузкой."""

    async def test_outbound_spans_layers_and_writes_consumptions(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id, ValuationMethod.FIFO)
        _ = await _receipt(env, Decimal("2"), Decimal("3"))
        _ = await _receipt(env, Decimal("2"), Decimal("7"))
        _ = await _delivery(env, Decimal("3"))
        layers = await _layers(env)
        inbound = [layer for layer in layers if layer.entry_kind == ValueEntryKind.INBOUND]
        outbound = next(layer for layer in layers if layer.entry_kind == ValueEntryKind.OUTBOUND)
        # Съели всю старую партию (2×3) и 1 шт новой (1×7): −13.
        assert outbound.quantity == Decimal("-3")
        assert outbound.value == Decimal("-13")
        assert inbound[0].remaining_quantity == Decimal("0")
        assert inbound[0].remaining_value == Decimal("0")
        assert inbound[1].remaining_quantity == Decimal("1")
        assert inbound[1].remaining_value == Decimal("7")
        consumptions = await StockValueLayerConsumption.list_unordered_for_out_layer(
            env.company_id, outbound.layer_id
        )
        by_in = {c.in_layer_id: c for c in consumptions}
        assert by_in[inbound[0].layer_id].quantity == Decimal("2")
        assert by_in[inbound[0].layer_id].value == Decimal("6")
        assert by_in[inbound[1].layer_id].quantity == Decimal("1")
        assert by_in[inbound[1].layer_id].value == Decimal("7")
        assert sum(c.value for c in consumptions) == -outbound.value


class TestRevalue:
    """Переоценка: сумма меняется, количество — нет."""

    async def test_value_delta_moves_value_only(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("4"), Decimal("5"))
        layer = await env.di.valuation_service.revalue(
            company_id=env.company_id,
            product_id=env.product.product_id,
            value_delta=Decimal("-8"),
            new_price=None,
            description="уценка просрочки",
        )
        assert layer.entry_kind == ValueEntryKind.REVALUATION
        assert layer.price_source == ValuationPriceSource.MANUAL
        assert layer.quantity == Decimal("0")
        assert layer.value == Decimal("-8")
        assert layer.qty_after == Decimal("4")
        assert layer.value_after == Decimal("12")

    async def test_new_price_computes_delta(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("4"), Decimal("5"))
        # 4 шт по новой цене 7 = 28; было 20 → дельта +8.
        layer = await env.di.valuation_service.revalue(
            company_id=env.company_id,
            product_id=env.product.product_id,
            value_delta=None,
            new_price=Decimal("7"),
            description="дооценка",
        )
        assert layer.value == Decimal("8")
        assert layer.value_after == Decimal("28")

    async def test_revalue_idempotent_replay(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("4"), Decimal("5"))
        first = await env.di.valuation_service.revalue(
            company_id=env.company_id,
            product_id=env.product.product_id,
            value_delta=Decimal("-8"),
            new_price=None,
            description="уценка",
            idempotency_key=f"rev-{unique_id}",
        )
        second = await env.di.valuation_service.revalue(
            company_id=env.company_id,
            product_id=env.product.product_id,
            value_delta=Decimal("-8"),
            new_price=None,
            description="уценка",
            idempotency_key=f"rev-{unique_id}",
        )
        assert second.layer_id == first.layer_id
        layers = await _layers(env)
        assert len(layers) == 2  # inbound + revaluation, без дубля


class TestCorrection:
    """Сторно: точечное исправление записи со ссылкой на оригинал."""

    async def test_correction_links_and_shifts_balances(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("2"), Decimal("5"))
        (inbound,) = await _layers(env)
        layer = await env.di.valuation_service.correction(
            company_id=env.company_id,
            origin_layer_id=inbound.layer_id,
            quantity_delta=Decimal("1"),
            value_delta=Decimal("5"),
            description="не досчитались одной штуки",
        )
        assert layer.entry_kind == ValueEntryKind.CORRECTION
        assert layer.origin_layer_id == inbound.layer_id
        assert layer.quantity == Decimal("1")
        assert layer.value == Decimal("5")
        assert layer.qty_after == Decimal("3")
        assert layer.value_after == Decimal("15")

    async def test_correction_unknown_layer_not_found(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        with pytest.raises(PlatformNotFoundError) as exc:
            _ = await env.di.valuation_service.correction(
                company_id=env.company_id,
                origin_layer_id="svl-missing",
                quantity_delta=Decimal("1"),
                value_delta=Decimal("1"),
                description="стorno",
            )
        assert exc.value.error_code == "layer_not_found"


class TestRunningBalance:
    """Бесшовный журнал: номера без дыр, баланс = Σ дельт."""

    async def test_entry_no_gapless_and_balance_consistent(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id, ValuationMethod.AVERAGE)
        _ = await _receipt(env, Decimal("4"), Decimal("5"))  # +4 / +20
        _ = await _delivery(env, Decimal("1"))  # −1 / −5
        quant = await _stock_quant(env)
        _ = await env.di.move_engine.inventory_set(
            company_id=env.company_id,
            quant_id=quant.quant_id,
            inventory_quantity=Decimal("5"),
        )
        _ = await env.di.move_engine.inventory_apply(
            company_id=env.company_id, quant_id=quant.quant_id
        )  # излишек +2
        _ = await env.di.valuation_service.revalue(
            company_id=env.company_id,
            product_id=env.product.product_id,
            value_delta=Decimal("10"),
            new_price=None,
            description="дооценка",
        )
        layers = await _layers(env)
        assert [layer.entry_no for layer in layers] == list(
            range(1, len(layers) + 1)
        )
        qty_run = Decimal("0")
        val_run = Decimal("0")
        for layer in layers:
            qty_run += layer.quantity
            val_run += layer.value
            assert layer.qty_after == qty_run
            assert layer.value_after == val_run
        # Бухгалтерский остаток = физическому: quant'ы сошлись с журналом.
        # Приход 20 − отгрузка 5 + излишек 0 (gain по карточной цене 0)
        # + дооценка 10 = 25.
        assert layers[-1].qty_after == Decimal("5")
        assert layers[-1].value_after == Decimal("25")
        quants = await StockQuant.list_unordered_for_warehouse(
            env.company_id, env.warehouse.warehouse_id
        )
        on_hand = sum(
            (q.quantity for q in quants if q.product_id == env.product.product_id),
            Decimal("0"),
        )
        assert on_hand == layers[-1].qty_after


class TestZeroCostRegression:
    """Нулевая себестоимость не должна ломать запись слоя.

    Регрессия: abs(Σvalue/Σqty) при нулевой стоимости возвращал
    ``Decimal('0E+6')``, который сериализовался в «0E+6» и падал
    в Postgres на NUMERIC-привязке.
    """

    async def test_zero_cost_return_writes_layer(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id, ValuationMethod.FIFO)
        env.product = await _product(
            env,
            f"zc-{unique_id}",
            valuation=ValuationMethod.FIFO,
            standard_price=Decimal("0"),
        )
        _ = await _receipt_for(
            env, env.product.product_id, Decimal("2"), None
        )
        delivery_id = await _delivery_for(
            env, env.product.product_id, Decimal("1")
        )
        ret = await env.di.move_engine.return_transfer(
            company_id=env.company_id,
            transfer_id=delivery_id,
            move_quantities=None,
        )
        assert ret.return_of_id == delivery_id
        layers = await _layers(env)
        ret_layer = next(layer for layer in layers if layer.entry_kind == ValueEntryKind.RETURN)
        assert ret_layer.unit_cost == Decimal("0")
        assert ret_layer.value == Decimal("0")


class TestProductValueScopes:
    """Оценка по компании и по складу раздельно."""

    async def test_warehouse_scope_splits_by_quants_company_avg(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id, ValuationMethod.AVERAGE)
        second = await env.di.warehouse_service.create_warehouse(
            company_id=env.company_id,
            code=f"W2{unique_id[:8]}",
            name="Second",
            owner_user_id="test_user",
            layout_preset=StockLayoutPreset.SIMPLE,
            removal_strategy=StockRemovalStrategy.FIFO,
        )
        _ = await _receipt(env, Decimal("4"), Decimal("10"))  # avg 10
        # Перекидываем 1 шт на второй склад внутренней операцией.
        internal = env.op_types[StockOperationCode.INTERNAL]
        transfer = await env.di.move_engine.create_transfer(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            operation_type_id=internal.operation_type_id,
            partner_entity_id=None,
            owner_entity_id=None,
            scheduled_at=None,
            origin_document_type=None,
            origin_document_id=None,
            barcode=None,
            moves=[
                StockMoveSpec(
                    product_id=env.product.product_id,
                    product_qty=Decimal("1"),
                    uom_id=env.uom_id,
                    location_dest_id=second.stock_location_id,
                )
            ],
        )
        for step in ("confirm", "assign", "validate"):
            _ = await getattr(env.di.move_engine, f"{step}_transfer")(
                company_id=env.company_id,
                transfer_id=transfer.transfer_id,
            )
        pv_first = await env.di.valuation_service.product_value(
            company_id=env.company_id,
            product_id=env.product.product_id,
            warehouse_id=env.warehouse.warehouse_id,
        )
        pv_second = await env.di.valuation_service.product_value(
            company_id=env.company_id,
            product_id=env.product.product_id,
            warehouse_id=second.warehouse_id,
        )
        # Цена — общекомпанейская средняя 10; количества — по полкам.
        assert pv_first.quantity == Decimal("3")
        assert pv_first.value == Decimal("30")
        assert pv_second.quantity == Decimal("1")
        assert pv_second.value == Decimal("10")
        pv_total = await env.di.valuation_service.product_value(
            company_id=env.company_id,
            product_id=env.product.product_id,
            warehouse_id=None,
        )
        assert pv_total.quantity == Decimal("4")
        assert pv_total.value == Decimal("40")
