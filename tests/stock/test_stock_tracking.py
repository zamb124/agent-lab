"""Трассировка e2e — партии и серийные номера сквозь движения.

Бизнес-правила под тестом:

* трассируемый товар не бывает «безликим»: каждая строка несёт
  ``lot_id``, quant лежит по ключу (продукт, локация, партия) —
  иначе «какой сертификат ушёл клиенту» не восстановить;
* ``serial`` — строго одна штука на строку и один серийник
  на складе: две единицы одного SN = брак в справочнике;
* FIFO по партиям — отгрузка ест партии в порядке прихода
  (``in_date``), строки распиливаются по партиям;
* FEFO (``removal_at`` на партии) побеждает FIFO: раньше
  истекает — раньше уходит, даже если пришла позже;
* срок годности денормализуется на quant при приходе —
  отбор не должен ходить за карточкой партии;
* barcode партии резолвится до lot через индекс — ТСД
  сканирует наклейку, а не id.
"""

from datetime import timedelta
from decimal import Decimal

import pytest

from apps.stock.models.common import StockMoveSpec
from apps.stock.models.enums import (
    StockBarcodeEntityType,
    StockOperationCode,
    StockRemovalStrategy,
    StockTracking,
    ValuationMethod,
)
from apps.stock.models.move import StockMove
from apps.stock.models.move_line import StockMoveLine
from apps.stock.models.quant import StockQuant
from core.errors.boundary import PlatformConflictError
from core.utils.time import utcnow

from .test_stock_domain import (
    StockEnv,
    _delivery,
    _make_env,
)


async def _env(stock_di, unique_id: str) -> StockEnv:
    return await _make_env(
        stock_di, f"co-{unique_id}", unique_id, ValuationMethod.FIFO
    )


async def _tracked_product(
    env: StockEnv, suffix: str, tracking: StockTracking, **kwargs
):
    return await env.di.stock_catalog_service.create_product(
        company_id=env.company_id,
        name=f"Trk {suffix}",
        sku=f"TRK-{suffix}",
        uom_id=env.uom_id,
        valuation_method=ValuationMethod.FIFO,
        standard_price=Decimal("0"),
        tracking=tracking,
        is_storable=True,
        category="general",
        **kwargs,
    )


async def _lot(env: StockEnv, product_id: str, name: str, **kwargs):
    return await env.di.stock_catalog_service.create_lot(
        company_id=env.company_id,
        product_id=product_id,
        name=name,
        barcode=kwargs.get("barcode"),
        expiration_at=kwargs.get("expiration_at"),
    )


async def _receipt_lot(
    env: StockEnv, product_id: str, qty: Decimal, lot_id: str
) -> str:
    """Приход трассируемого товара: строке присваиваем партию."""
    op = env.op_types[StockOperationCode.INCOMING]
    transfer = await env.di.move_engine.create_transfer(
        company_id=env.company_id,
        warehouse_id=env.warehouse.warehouse_id,
        operation_type_id=op.operation_type_id,
        partner_entity_id=None,
        owner_entity_id=None,
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
    for step in ("confirm", "assign"):
        _ = await getattr(env.di.move_engine, f"{step}_transfer")(
            company_id=env.company_id,
            transfer_id=transfer.transfer_id,
        )
    lines = await StockMoveLine.list_for_moves_by_created_at_asc(
        env.company_id,
        [
            m.move_id
            for m in await StockMove.list_for_transfer_by_created_at_asc(
                env.company_id, transfer.transfer_id
            )
        ],
    )
    _ = await env.di.task_service.update_move_line(
        company_id=env.company_id,
        move_line_id=lines[0].move_line_id,
        done_quantity=None,
        picked=None,
        lot_id=lot_id,
        location_dest_id=None,
    )
    _ = await env.di.move_engine.validate_transfer(
        company_id=env.company_id, transfer_id=transfer.transfer_id
    )
    return transfer.transfer_id


class TestLotBasics:
    async def test_quants_split_by_lot_on_same_location(
        self, stock_di, unique_id: str
    ) -> None:
        """Два прихода разных партий → два quant'а на одной ячейке:
        остаток дробится по партиям, не сливается."""
        env = await _env(stock_di, unique_id)
        product = await _tracked_product(
            env, f"lt-{unique_id}", StockTracking.LOT
        )
        lot_a = await _lot(env, product.product_id, f"LOT-A-{unique_id}")
        lot_b = await _lot(env, product.product_id, f"LOT-B-{unique_id}")
        _ = await _receipt_lot(env, product.product_id, Decimal("2"), lot_a.lot_id)
        _ = await _receipt_lot(env, product.product_id, Decimal("3"), lot_b.lot_id)
        qa = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=product.product_id,
            location_id=env.warehouse.stock_location_id,
            lot_id=lot_a.lot_id,
            owner_entity_id=None,
        )
        qb = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=product.product_id,
            location_id=env.warehouse.stock_location_id,
            lot_id=lot_b.lot_id,
            owner_entity_id=None,
        )
        assert qa.quantity == Decimal("2")
        assert qb.quantity == Decimal("3")

    async def test_delivery_splits_lines_across_lots_fifo(
        self, stock_di, unique_id: str
    ) -> None:
        """Отгрузка 4 при партиях 2+3: движок распиливает строки
        по партиям в порядке прихода — LOT-A целиком + 2 из LOT-B."""
        env = await _env(stock_di, unique_id)
        product = await _tracked_product(
            env, f"lt2-{unique_id}", StockTracking.LOT
        )
        lot_a = await _lot(env, product.product_id, f"LOT-A-{unique_id}")
        lot_b = await _lot(env, product.product_id, f"LOT-B-{unique_id}")
        _ = await _receipt_lot(env, product.product_id, Decimal("2"), lot_a.lot_id)
        _ = await _receipt_lot(env, product.product_id, Decimal("3"), lot_b.lot_id)
        env.product = product
        delivery_id = await _delivery(env, Decimal("4"))
        moves = await StockMove.list_for_transfer_by_created_at_asc(env.company_id, delivery_id)
        lines = await StockMoveLine.list_for_move_by_created_at_asc(
            env.company_id, moves[0].move_id
        )
        by_lot = {line.lot_id: line.done_quantity for line in lines}
        assert by_lot == {lot_a.lot_id: Decimal("2"), lot_b.lot_id: Decimal("2")}
        qa = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=product.product_id,
            location_id=env.warehouse.stock_location_id,
            lot_id=lot_a.lot_id,
            owner_entity_id=None,
        )
        assert qa.quantity == Decimal("0")


class TestSerial:
    async def test_serial_receipt_one_unit_per_line(
        self, stock_di, unique_id: str
    ) -> None:
        """Два серийника — два отдельных прихода по 1 шт:
        каждый SN — самостоятельный quant."""
        env = await _env(stock_di, unique_id)
        product = await _tracked_product(
            env, f"sn-{unique_id}", StockTracking.SERIAL
        )
        sn1 = await _lot(env, product.product_id, f"SN-1-{unique_id}")
        sn2 = await _lot(env, product.product_id, f"SN-2-{unique_id}")
        _ = await _receipt_lot(env, product.product_id, Decimal("1"), sn1.lot_id)
        _ = await _receipt_lot(env, product.product_id, Decimal("1"), sn2.lot_id)
        q1 = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=product.product_id,
            location_id=env.warehouse.stock_location_id,
            lot_id=sn1.lot_id,
            owner_entity_id=None,
        )
        q2 = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=product.product_id,
            location_id=env.warehouse.stock_location_id,
            lot_id=sn2.lot_id,
            owner_entity_id=None,
        )
        assert q1.quantity == Decimal("1")
        assert q2.quantity == Decimal("1")

    async def test_second_receipt_same_serial_rejected(
        self, stock_di, unique_id: str
    ) -> None:
        """SN уже лежит на складе — повторный приход того же
        серийника это ошибка ввода, не новая единица."""
        env = await _env(stock_di, unique_id)
        product = await _tracked_product(
            env, f"sn2-{unique_id}", StockTracking.SERIAL
        )
        sn = await _lot(env, product.product_id, f"SN-X-{unique_id}")
        _ = await _receipt_lot(env, product.product_id, Decimal("1"), sn.lot_id)
        with pytest.raises(PlatformConflictError) as exc:
            _ = await _receipt_lot(
                env, product.product_id, Decimal("1"), sn.lot_id
            )
        assert exc.value.error_code == "serial_quantity_invalid"

    async def test_delivery_of_specific_serial(
        self, stock_di, unique_id: str
    ) -> None:
        """Отгрузка конкретного SN: обнуляет его quant, соседний
        серийник остаётся нетронутым."""
        env = await _env(stock_di, unique_id)
        product = await _tracked_product(
            env, f"sn3-{unique_id}", StockTracking.SERIAL
        )
        sn1 = await _lot(env, product.product_id, f"SN-1-{unique_id}")
        sn2 = await _lot(env, product.product_id, f"SN-2-{unique_id}")
        _ = await _receipt_lot(env, product.product_id, Decimal("1"), sn1.lot_id)
        _ = await _receipt_lot(env, product.product_id, Decimal("1"), sn2.lot_id)
        op = env.op_types[StockOperationCode.OUTGOING]
        transfer = await env.di.move_engine.create_transfer(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            operation_type_id=op.operation_type_id,
            partner_entity_id=None,
            owner_entity_id=None,
            scheduled_at=None,
            origin_document_type=None,
            origin_document_id=None,
            barcode=None,
            moves=[
                StockMoveSpec(
                    product_id=product.product_id,
                    product_qty=Decimal("1"),
                    uom_id=env.uom_id,
                )
            ],
        )
        for step in ("confirm", "assign"):
            _ = await getattr(env.di.move_engine, f"{step}_transfer")(
                company_id=env.company_id,
                transfer_id=transfer.transfer_id,
            )
        moves = await StockMove.list_for_transfer_by_created_at_asc(
            env.company_id, transfer.transfer_id
        )
        lines = await StockMoveLine.list_for_move_by_created_at_asc(
            env.company_id, moves[0].move_id
        )
        # Движок сам выбрал SN по FIFO (sn1 пришёл первым).
        assert lines[0].lot_id == sn1.lot_id
        _ = await env.di.move_engine.validate_transfer(
            company_id=env.company_id, transfer_id=transfer.transfer_id
        )
        q1 = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=product.product_id,
            location_id=env.warehouse.stock_location_id,
            lot_id=sn1.lot_id,
            owner_entity_id=None,
        )
        q2 = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=product.product_id,
            location_id=env.warehouse.stock_location_id,
            lot_id=sn2.lot_id,
            owner_entity_id=None,
        )
        assert q1.quantity == Decimal("0")
        assert q2.quantity == Decimal("1")

    async def test_serial_receivable_again_after_shipment(
        self, stock_di, unique_id: str
    ) -> None:
        """Инвариант «SN на складе ≤ 1» считается по ОСТАТКУ:
        серийник уехал клиенту (quant=0) → тот же SN можно принять
        снова (возврат/новая единица того же производителя).
        Пока лежит — дубль запрещён, уехал — свободен."""
        env = await _env(stock_di, unique_id)
        product = await _tracked_product(
            env, f"sn4-{unique_id}", StockTracking.SERIAL
        )
        sn = await _lot(env, product.product_id, f"SN-R-{unique_id}")
        _ = await _receipt_lot(env, product.product_id, Decimal("1"), sn.lot_id)
        op = env.op_types[StockOperationCode.OUTGOING]
        transfer = await env.di.move_engine.create_transfer(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            operation_type_id=op.operation_type_id,
            partner_entity_id=None,
            owner_entity_id=None,
            scheduled_at=None,
            origin_document_type=None,
            origin_document_id=None,
            barcode=None,
            moves=[
                StockMoveSpec(
                    product_id=product.product_id,
                    product_qty=Decimal("1"),
                    uom_id=env.uom_id,
                )
            ],
        )
        for step in ("confirm", "assign", "validate"):
            _ = await getattr(env.di.move_engine, f"{step}_transfer")(
                company_id=env.company_id,
                transfer_id=transfer.transfer_id,
            )
        # SN покинул склад — тот же серийник принимается без конфликта.
        _ = await _receipt_lot(env, product.product_id, Decimal("1"), sn.lot_id)
        quant = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=product.product_id,
            location_id=env.warehouse.stock_location_id,
            lot_id=sn.lot_id,
            owner_entity_id=None,
        )
        assert quant is not None and quant.quantity == Decimal("1")


class TestFefo:
    """FEFO: раньше истекает — раньше отгружаем."""

    async def test_earliest_expiry_picked_regardless_of_receipt_order(
        self, stock_di, unique_id: str
    ) -> None:
        env = await _env(stock_di, unique_id)
        product = await _tracked_product(
            env,
            f"fefo-{unique_id}",
            StockTracking.LOT,
            removal_strategy=StockRemovalStrategy.FEFO,
        )
        now = utcnow()
        far = await _lot(
            env,
            product.product_id,
            f"FAR-{unique_id}",
            expiration_at=now + timedelta(days=90),
        )
        near = await _lot(
            env,
            product.product_id,
            f"NEAR-{unique_id}",
            expiration_at=now + timedelta(days=10),
        )
        # FAR пришёл ПЕРВЫМ — FIFO бы взял его; FEFO обязан взять NEAR.
        _ = await _receipt_lot(env, product.product_id, Decimal("2"), far.lot_id)
        _ = await _receipt_lot(env, product.product_id, Decimal("2"), near.lot_id)
        op = env.op_types[StockOperationCode.OUTGOING]
        transfer = await env.di.move_engine.create_transfer(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            operation_type_id=op.operation_type_id,
            partner_entity_id=None,
            owner_entity_id=None,
            scheduled_at=None,
            origin_document_type=None,
            origin_document_id=None,
            barcode=None,
            moves=[
                StockMoveSpec(
                    product_id=product.product_id,
                    product_qty=Decimal("1"),
                    uom_id=env.uom_id,
                )
            ],
        )
        for step in ("confirm", "assign"):
            _ = await getattr(env.di.move_engine, f"{step}_transfer")(
                company_id=env.company_id,
                transfer_id=transfer.transfer_id,
            )
        moves = await StockMove.list_for_transfer_by_created_at_asc(
            env.company_id, transfer.transfer_id
        )
        lines = await StockMoveLine.list_for_move_by_created_at_asc(
            env.company_id, moves[0].move_id
        )
        assert lines[0].lot_id == near.lot_id

    async def test_removal_at_denormalized_to_quant(
        self, stock_di, unique_id: str
    ) -> None:
        """Quant после прихода несёт removal_at партии — отбор
        не читает карточку лота на каждый резерв."""
        env = await _env(stock_di, unique_id)
        product = await _tracked_product(
            env,
            f"fefo2-{unique_id}",
            StockTracking.LOT,
            removal_days=5,
        )
        # БД хранит naive UTC — сравниваем без tzinfo.
        expiry = (utcnow() + timedelta(days=30)).replace(tzinfo=None)
        lot = await _lot(
            env, product.product_id, f"EXP-{unique_id}", expiration_at=expiry
        )
        # removal_at = expiration − removal_days (карточка даёт смещение).
        assert lot.removal_at == expiry - timedelta(days=5)
        _ = await _receipt_lot(env, product.product_id, Decimal("2"), lot.lot_id)
        quant = await StockQuant.by_key(
            company_id=env.company_id,
            product_id=product.product_id,
            location_id=env.warehouse.stock_location_id,
            lot_id=lot.lot_id,
            owner_entity_id=None,
        )
        assert quant.removal_at == lot.removal_at


class TestLotBarcode:
    async def test_lot_barcode_resolves_to_lot(
        self, stock_di, unique_id: str
    ) -> None:
        """Наклейка партии сканируется в lot_id — оператор
        на ТСД не знает внутреннего id."""
        env = await _env(stock_di, unique_id)
        product = await _tracked_product(
            env, f"bc-{unique_id}", StockTracking.LOT
        )
        lot = await _lot(
            env,
            product.product_id,
            f"LOTBC-{unique_id}",
            barcode=f"LOTBC-{unique_id}",
        )
        resolved = await env.di.barcode_service.resolve(
            company_id=env.company_id, barcode=f"LOTBC-{unique_id}"
        )
        assert resolved.entity_type == StockBarcodeEntityType.LOT
        assert resolved.entity_id == lot.lot_id
