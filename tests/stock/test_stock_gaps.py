"""Пробельные поверхности аудита: ручные проводки оценки, аудируемые
решения размещения, сессии ресурсов (ТСД/техника), штрихкод-индекс
и CRUD правил putaway.

Каждый блок закрывает поверхность, которую не трогали доменные
сценарии: деньги (переоценка/сторно журнала стоимости), аудит выбора
ячейки (StockDecision), смена оператора на технике, жизненный цикл
штрихкода и администрирование правил размещения.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from apps.stock.models.barcode_index import StockBarcodeIndex
from apps.stock.models.common import StockMoveSpec, new_id
from apps.stock.models.enums import (
    StockBarcodeEntityType,
    StockDecisionStatus,
    StockLocationUsage,
    StockOperationCode,
    ValuationMethod,
    ValuationPriceSource,
    ValueEntryKind,
)
from apps.stock.models.move import StockMove
from apps.stock.models.putaway_rule import StockPutawayRule
from apps.stock.models.resource import StockResource
from apps.stock.models.value_layer import StockValueLayer
from core.errors.boundary import (
    PlatformConflictError,
    PlatformNotFoundError,
)
from core.lanes import LaneCommit
from core.utils.time import utcnow

from .test_stock_domain import StockEnv, _layers, _make_env, _receipt, _stock_quant


async def _env(stock_di, unique_id: str) -> StockEnv:
    return await _make_env(
        stock_di,
        company_id=f"co-{unique_id}",
        unique=unique_id,
        valuation=ValuationMethod.AVERAGE,
    )


async def _draft_receipt(env: StockEnv, qty: Decimal) -> tuple[str, str]:
    """Черновик INCOMING-накладной; возвращает (transfer_id, move_id)."""
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
                product_id=env.product.product_id,
                product_qty=qty,
                uom_id=env.uom_id,
                unit_price=Decimal("4"),
            )
        ],
    )
    moves = await StockMove.list_for_transfer_by_created_at_asc(env.company_id, transfer.transfer_id)
    assert len(moves) == 1
    return transfer.transfer_id, moves[0].move_id


async def _bin(env: StockEnv, suffix: str) -> str:
    loc = await env.di.topology_service.create_location(
        company_id=env.company_id,
        warehouse_id=env.warehouse.warehouse_id,
        parent_id=env.warehouse.view_location_id,
        name=f"BIN-{suffix}",
        usage=StockLocationUsage.BIN,
        barcode=None,
    )
    return loc.location_id


class TestValuationAdjustments:
    """`revalue`/`correction` — ручные проводки журнала стоимости."""

    async def test_revalue_by_delta_writes_manual_layer(self, stock_di, unique_id: str) -> None:
        """Уценка/дооценка меняет только сумму: количество остатка то же.

        Приход 10 шт по 4 ₽ (слой IN, value_after=40) →
        ``revalue(value_delta=+20)`` даёт запись ``revaluation``:
        ``quantity=0``, ``value=+20``, running balance qty_after=10 /
        value_after=60. Физика не тронута — quant остаётся 10 шт.
        """
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("10"), Decimal("4"))

        layer = await env.di.valuation_service.revalue(
            company_id=env.company_id,
            product_id=env.product.product_id,
            value_delta=Decimal("20"),
            new_price=None,
            description="дооценка запаса",
            idempotency_key=uuid.uuid7().hex,
        )

        assert layer.entry_kind == ValueEntryKind.REVALUATION
        assert layer.price_source == ValuationPriceSource.MANUAL
        assert layer.quantity == Decimal("0")
        assert layer.value == Decimal("20")
        assert layer.qty_after == Decimal("10")
        assert layer.value_after == Decimal("60")
        # Ручная запись не создаёт расходуемого остатка слоя.
        assert layer.remaining_quantity == Decimal("0")
        assert layer.remaining_value == Decimal("0")
        quant = await _stock_quant(env)
        assert quant is not None and quant.quantity == Decimal("10")

    async def test_revalue_by_new_price_computes_delta(self, stock_di, unique_id: str) -> None:
        """``new_price=7`` при остатке 10 шт и стоимости 40 ₽ → дельта +30."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("10"), Decimal("4"))

        layer = await env.di.valuation_service.revalue(
            company_id=env.company_id,
            product_id=env.product.product_id,
            value_delta=None,
            new_price=Decimal("7"),
            description="новая цена 7",
            idempotency_key=uuid.uuid7().hex,
        )

        assert layer.value == Decimal("30")
        assert layer.value_after == Decimal("70")
        assert layer.qty_after == Decimal("10")

    async def test_revalue_idempotent_replay(self, stock_di, unique_id: str) -> None:
        """Повтор команды с тем же ключом — та же запись, журнал не растёт."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("10"), Decimal("4"))
        before = await _layers(env)
        key = uuid.uuid7().hex

        first = await env.di.valuation_service.revalue(
            company_id=env.company_id,
            product_id=env.product.product_id,
            value_delta=Decimal("5"),
            new_price=None,
            description="idem",
            idempotency_key=key,
        )
        second = await env.di.valuation_service.revalue(
            company_id=env.company_id,
            product_id=env.product.product_id,
            value_delta=Decimal("5"),
            new_price=None,
            description="idem",
            idempotency_key=key,
        )

        assert second.layer_id == first.layer_id
        after = await _layers(env)
        assert len(after) == len(before) + 1

    async def test_revalue_commit_carries_event(self, stock_di, unique_id: str) -> None:
        """Коммит переоценки несёт ``stock/valuation/changed`` и publish-метку."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("4"), Decimal("5"))
        key = uuid.uuid7().hex
        _ = await env.di.valuation_service.revalue(
            company_id=env.company_id,
            product_id=env.product.product_id,
            value_delta=Decimal("8"),
            new_price=None,
            description="с событием",
            idempotency_key=key,
        )
        commit = await LaneCommit.by_idempotency_key(env.company_id, key, using="stock")
        assert commit is not None
        types = {e.type for e in commit.platform_events()}
        assert "stock/valuation/changed" in types
        assert commit.published_at is not None

    async def test_correction_partial_storno(self, stock_di, unique_id: str) -> None:
        """Сторно 2 шт из прихода 10 шт: запись со ссылкой на оригинал."""
        env = await _env(stock_di, unique_id)
        _ = await _receipt(env, Decimal("10"), Decimal("4"))
        origin = (await _layers(env))[0]

        layer = await env.di.valuation_service.correction(
            company_id=env.company_id,
            origin_layer_id=origin.layer_id,
            quantity_delta=Decimal("-2"),
            value_delta=Decimal("-8"),
            description="сторно двух штук",
            idempotency_key=uuid.uuid7().hex,
        )

        assert layer.entry_kind == ValueEntryKind.CORRECTION
        assert layer.origin_layer_id == origin.layer_id
        assert layer.quantity == Decimal("-2")
        assert layer.value == Decimal("-8")
        assert layer.qty_after == Decimal("8")
        assert layer.value_after == Decimal("32")
        # Оригинал не тронут — история честная.
        fresh_origin = await StockValueLayer.by_id(env.company_id, origin.layer_id)
        assert fresh_origin is not None
        assert fresh_origin.quantity == Decimal("10")

    async def test_correction_foreign_company_layer_not_found(
        self, stock_di, unique_id: str
    ) -> None:
        """Слой чужой компании — not_found (изоляция tenant'ов)."""
        env_a = await _env(stock_di, f"{unique_id}a")
        env_b = await _env(stock_di, f"{unique_id}b")
        _ = await _receipt(env_b, Decimal("3"), Decimal("5"))
        foreign_layer = (await _layers(env_b))[0]

        with pytest.raises(PlatformNotFoundError) as exc:
            await env_a.di.valuation_service.correction(
                company_id=env_a.company_id,
                origin_layer_id=foreign_layer.layer_id,
                quantity_delta=Decimal("1"),
                value_delta=Decimal("5"),
                description="чужой слой",
                idempotency_key=uuid.uuid7().hex,
            )
        assert exc.value.error_code == "layer_not_found"

    async def test_revalue_foreign_product_not_found(self, stock_di, unique_id: str) -> None:
        env_a = await _env(stock_di, f"{unique_id}a")
        env_b = await _env(stock_di, f"{unique_id}b")
        with pytest.raises(PlatformNotFoundError):
            await env_a.di.valuation_service.revalue(
                company_id=env_a.company_id,
                product_id=env_b.product.product_id,
                value_delta=Decimal("5"),
                new_price=None,
                description="чужой товар",
                idempotency_key=uuid.uuid7().hex,
            )


class TestApplyDecision:
    """`stock/move/apply_decision` — ручной/агентный выбор ячейки."""

    async def test_apply_writes_applied_decision(self, stock_di, unique_id: str) -> None:
        """Выбор кандидата пишет аудируемый StockDecision (status=applied)."""
        env = await _env(stock_di, unique_id)
        bin_a = await _bin(env, f"A{unique_id}")
        _, move_id = await _draft_receipt(env, Decimal("5"))

        decision = await env.di.placement_service.apply_decision(
            company_id=env.company_id,
            move_id=move_id,
            location_id=bin_a,
            idempotency_key=uuid.uuid7().hex,
        )

        assert decision.status == StockDecisionStatus.APPLIED
        assert decision.chosen_location_id == bin_a
        assert decision.move_id == move_id
        assert bin_a in decision.candidate_location_ids

    async def test_apply_rejects_location_outside_candidates(
        self, stock_di, unique_id: str
    ) -> None:
        """Ячейка чужого склада не входит во вселенную кандидатов."""
        env_a = await _env(stock_di, f"{unique_id}a")
        env_b = await _env(stock_di, f"{unique_id}b")
        foreign_bin = await _bin(env_b, f"B{unique_id}")
        _, move_id = await _draft_receipt(env_a, Decimal("5"))

        with pytest.raises(PlatformConflictError) as exc:
            await env_a.di.placement_service.apply_decision(
                company_id=env_a.company_id,
                move_id=move_id,
                location_id=foreign_bin,
                idempotency_key=uuid.uuid7().hex,
            )
        assert exc.value.error_code == "putaway_choice_invalid"

    async def test_apply_move_not_found(self, stock_di, unique_id: str) -> None:
        env = await _env(stock_di, unique_id)
        with pytest.raises(PlatformNotFoundError) as exc:
            await env.di.placement_service.apply_decision(
                company_id=env.company_id,
                move_id=f"mv_missing_{unique_id}",
                location_id=env.warehouse.stock_location_id,
                idempotency_key=uuid.uuid7().hex,
            )
        assert exc.value.error_code == "move_not_found"

    async def test_apply_orphan_move_rejected(self, stock_di, unique_id: str) -> None:
        """Move без накладной не может получить решение размещения."""
        env = await _env(stock_di, unique_id)
        orphan = await StockMove.create(
            StockMove(
                move_id=new_id("mv"),
                company_id=env.company_id,
                product_id=env.product.product_id,
                product_qty=Decimal("1"),
                product_uom_qty=Decimal("1"),
                uom_id=env.uom_id,
                location_id=env.warehouse.stock_location_id,
                location_dest_id=env.warehouse.stock_location_id,
                date=utcnow(),
                created_at=utcnow(),
            )
        )
        with pytest.raises(PlatformConflictError) as exc:
            await env.di.placement_service.apply_decision(
                company_id=env.company_id,
                move_id=orphan.move_id,
                location_id=env.warehouse.stock_location_id,
                idempotency_key=uuid.uuid7().hex,
            )
        assert exc.value.error_code == "move_orphan"

    async def test_removal_strategy_unresolved_for_orphan(self, stock_di, unique_id: str) -> None:
        """Move без склада: цепочка product→storage_type→warehouse обрывается."""
        env = await _env(stock_di, unique_id)
        orphan = await StockMove.create(
            StockMove(
                move_id=new_id("mv"),
                company_id=env.company_id,
                product_id=env.product.product_id,
                product_qty=Decimal("1"),
                product_uom_qty=Decimal("1"),
                uom_id=env.uom_id,
                location_id=env.warehouse.stock_location_id,
                location_dest_id=env.warehouse.stock_location_id,
                date=utcnow(),
                created_at=utcnow(),
            )
        )
        # У продукта нет removal_strategy, у ячейки нет storage_type,
        # у move нет warehouse → политика не резолвится.
        with pytest.raises(PlatformConflictError) as exc:
            await env.di.placement_service.resolve_for_move(company_id=env.company_id, move=orphan)
        assert exc.value.error_code == "removal_strategy_unresolved"


class TestResourceSessions:
    """Вход/выход оператора на технику — занятость и привязка."""

    async def _resource(
        self, env: StockEnv, suffix: str, barcode: str | None = None
    ) -> StockResource:
        rtype = await env.di.topology_service.create_resource_type(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            name=f"RT-{suffix}",
            allowed_container_type_ids=[],
            storage_type_ids=[],
            handles_loose=True,
            max_level=None,
        )
        return await env.di.topology_service.create_resource(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            resource_type_id=rtype.resource_type_id,
            code=f"RES-{suffix}",
            barcode=barcode,
        )

    async def test_login_logout_cycle(self, stock_di, unique_id: str) -> None:
        env = await _env(stock_di, unique_id)
        res = await self._resource(env, f"C{unique_id}")
        user = f"op-{unique_id}"

        logged = await env.di.topology_service.resource_login(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            resource_id=res.resource_id,
            barcode=None,
            user_id=user,
        )
        assert logged.current_user_id == user
        assert logged.logged_in_at is not None

        out = await env.di.topology_service.resource_logout(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            user_id=user,
        )
        assert out.resource_id == res.resource_id
        fresh = await StockResource.by_id(env.company_id, res.resource_id)
        assert fresh is not None and fresh.current_user_id is None

    async def test_login_by_barcode(self, stock_di, unique_id: str) -> None:
        """Метка ресурса: скан штрихкода находит машину и вешает сессию."""
        env = await _env(stock_di, unique_id)
        res = await self._resource(env, f"D{unique_id}", barcode=f"RESBC-{unique_id}")
        logged = await env.di.topology_service.resource_login(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            resource_id=None,
            barcode=f"RESBC-{unique_id}",
            user_id=f"op-{unique_id}",
        )
        assert logged.resource_id == res.resource_id

    async def test_user_bound_second_resource(self, stock_di, unique_id: str) -> None:
        """Оператор на одной машине: второй ресурс — конфликт."""
        env = await _env(stock_di, unique_id)
        res_a = await self._resource(env, f"E{unique_id}")
        res_b = await self._resource(env, f"F{unique_id}")
        user = f"op-{unique_id}"
        _ = await env.di.topology_service.resource_login(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            resource_id=res_a.resource_id,
            barcode=None,
            user_id=user,
        )
        with pytest.raises(PlatformConflictError) as exc:
            await env.di.topology_service.resource_login(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                resource_id=res_b.resource_id,
                barcode=None,
                user_id=user,
            )
        assert exc.value.error_code == "resource_user_bound"

    async def test_relogin_same_user_same_resource(self, stock_di, unique_id: str) -> None:
        """Повторный вход того же оператора на ту же машину — no-op."""
        env = await _env(stock_di, unique_id)
        res = await self._resource(env, f"G{unique_id}")
        user = f"op-{unique_id}"
        for _ in range(2):
            logged = await env.di.topology_service.resource_login(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                resource_id=res.resource_id,
                barcode=None,
                user_id=user,
            )
            assert logged.current_user_id == user

    async def test_logout_frees_for_other_user(self, stock_di, unique_id: str) -> None:
        env = await _env(stock_di, unique_id)
        res = await self._resource(env, f"H{unique_id}")
        _ = await env.di.topology_service.resource_login(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            resource_id=res.resource_id,
            barcode=None,
            user_id=f"op-a-{unique_id}",
        )
        _ = await env.di.topology_service.resource_logout(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            user_id=f"op-a-{unique_id}",
        )
        logged = await env.di.topology_service.resource_login(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            resource_id=res.resource_id,
            barcode=None,
            user_id=f"op-b-{unique_id}",
        )
        assert logged.current_user_id == f"op-b-{unique_id}"

    async def test_logout_without_session_is_noop(self, stock_di, unique_id: str) -> None:
        env = await _env(stock_di, unique_id)
        out = await env.di.topology_service.resource_logout(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            user_id=f"ghost-{unique_id}",
        )
        assert out.resource_id is None

    async def test_logout_other_warehouse_is_noop(self, stock_di, unique_id: str) -> None:
        """Logout в чужом складе не снимает сессию в своём."""
        env_a = await _env(stock_di, f"{unique_id}a")
        env_b = await _env(stock_di, f"{unique_id}b")
        res = await self._resource(env_a, f"I{unique_id}")
        user = f"op-{unique_id}"
        _ = await env_a.di.topology_service.resource_login(
            company_id=env_a.company_id,
            warehouse_id=env_a.warehouse.warehouse_id,
            resource_id=res.resource_id,
            barcode=None,
            user_id=user,
        )
        out = await env_b.di.topology_service.resource_logout(
            company_id=env_b.company_id,
            warehouse_id=env_b.warehouse.warehouse_id,
            user_id=user,
        )
        assert out.resource_id is None
        fresh = await StockResource.by_id(env_a.company_id, res.resource_id)
        assert fresh is not None and fresh.current_user_id == user

    async def test_login_requires_id_or_barcode(self, stock_di, unique_id: str) -> None:
        env = await _env(stock_di, unique_id)
        with pytest.raises(PlatformConflictError) as exc:
            await env.di.topology_service.resource_login(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                resource_id=None,
                barcode=None,
                user_id=f"op-{unique_id}",
            )
        assert exc.value.error_code == "resource_login_input_invalid"

    async def test_login_unknown_barcode_not_found(self, stock_di, unique_id: str) -> None:
        env = await _env(stock_di, unique_id)
        with pytest.raises(PlatformNotFoundError) as exc:
            await env.di.topology_service.resource_login(
                company_id=env.company_id,
                warehouse_id=env.warehouse.warehouse_id,
                resource_id=None,
                barcode=f"NOPE-{unique_id}",
                user_id=f"op-{unique_id}",
            )
        assert exc.value.error_code == "resource_not_found"

    async def test_login_foreign_company_resource(self, stock_di, unique_id: str) -> None:
        env_a = await _env(stock_di, f"{unique_id}a")
        env_b = await _env(stock_di, f"{unique_id}b")
        foreign = await self._resource(env_b, f"J{unique_id}")
        with pytest.raises(PlatformNotFoundError) as exc:
            _ = await env_a.di.topology_service.resource_login(
                company_id=env_a.company_id,
                warehouse_id=env_a.warehouse.warehouse_id,
                resource_id=foreign.resource_id,
                barcode=None,
                user_id=f"op-{unique_id}",
            )
        assert exc.value.error_code == "resource_not_found"


class TestBarcodeIndex:
    """Жизненный цикл штрихкода: register → replace → release."""

    async def test_replace_rebinds_code(self, stock_di, unique_id: str) -> None:
        env = await _env(stock_di, unique_id)
        old_code, new_code = f"OLD-{unique_id}", f"NEW-{unique_id}"
        _ = await env.di.barcode_service.register(
            company_id=env.company_id,
            barcode=old_code,
            entity_type=StockBarcodeEntityType.PRODUCT,
            entity_id=env.product.product_id,
        )
        await env.di.barcode_service.replace(
            company_id=env.company_id,
            barcode=new_code,
            entity_type=StockBarcodeEntityType.PRODUCT,
            entity_id=env.product.product_id,
        )
        with pytest.raises(PlatformNotFoundError):
            _ = await env.di.barcode_service.resolve(company_id=env.company_id, barcode=old_code)
        resolved = await env.di.barcode_service.resolve(company_id=env.company_id, barcode=new_code)
        assert resolved.entity_id == env.product.product_id

    async def test_release_entity_unbinds(self, stock_di, unique_id: str) -> None:
        env = await _env(stock_di, unique_id)
        code = f"REL-{unique_id}"
        _ = await env.di.barcode_service.register(
            company_id=env.company_id,
            barcode=code,
            entity_type=StockBarcodeEntityType.LOCATION,
            entity_id=env.warehouse.stock_location_id,
        )
        await StockBarcodeIndex.release_entity(env.company_id, env.warehouse.stock_location_id)
        with pytest.raises(PlatformNotFoundError) as exc:
            _ = await env.di.barcode_service.resolve(company_id=env.company_id, barcode=code)
        assert exc.value.error_code == "barcode_not_found"

    async def test_foreign_company_barcode_invisible(self, stock_di, unique_id: str) -> None:
        env_a = await _env(stock_di, f"{unique_id}a")
        env_b = await _env(stock_di, f"{unique_id}b")
        _ = await env_a.di.barcode_service.register(
            company_id=env_a.company_id,
            barcode=f"X-{unique_id}",
            entity_type=StockBarcodeEntityType.PRODUCT,
            entity_id=env_a.product.product_id,
        )
        with pytest.raises(PlatformNotFoundError):
            _ = await env_b.di.barcode_service.resolve(
                company_id=env_b.company_id, barcode=f"X-{unique_id}"
            )

    async def test_register_same_code_same_entity_noop(self, stock_di, unique_id: str) -> None:
        env = await _env(stock_di, unique_id)
        for _ in range(2):
            _ = await env.di.barcode_service.register(
                company_id=env.company_id,
                barcode=f"DUP-{unique_id}",
                entity_type=StockBarcodeEntityType.PRODUCT,
                entity_id=env.product.product_id,
            )
        resolved = await env.di.barcode_service.resolve(
            company_id=env.company_id, barcode=f"DUP-{unique_id}"
        )
        assert resolved.entity_id == env.product.product_id


class TestPutawayRuleCrud:
    """Правила размещения: update/set_active/delete и их влияние на suggest."""

    async def test_rule_prefers_bound_location(self, stock_di, unique_id: str) -> None:
        """Правило `product → BIN-B` ставит BIN-B первой (reason=rule_match)."""
        env = await _env(stock_di, unique_id)
        bin_a = await _bin(env, f"K{unique_id}")
        bin_b = await _bin(env, f"L{unique_id}")
        _ = await StockPutawayRule.create(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            location_in_id=env.warehouse.view_location_id,
            location_out_id=bin_b,
            product_id=env.product.product_id,
        )
        _, move_id = await _draft_receipt(env, Decimal("2"))
        move = await StockMove.by_id(env.company_id, move_id)
        assert move is not None
        suggestions = await env.di.placement_service.suggest_by_allowed_group_rank_and_pick_sequence_asc(
            company_id=env.company_id,
            warehouse=env.warehouse,
            move=move,
        )
        assert suggestions
        assert suggestions[0].location_id == bin_b
        assert suggestions[0].reason_code == "rule_match"
        assert bin_a in {s.location_id for s in suggestions}

    async def test_update_rule_moves_target(self, stock_di, unique_id: str) -> None:
        env = await _env(stock_di, unique_id)
        bin_a = await _bin(env, f"M{unique_id}")
        bin_b = await _bin(env, f"N{unique_id}")
        rule = await StockPutawayRule.create(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            location_in_id=env.warehouse.view_location_id,
            location_out_id=bin_b,
            product_id=env.product.product_id,
        )
        updated = await StockPutawayRule.update_locations_filters_and_sequence(
            env.company_id, rule.rule_id, location_out_id=bin_a
        )
        assert updated is not None and updated.location_out_id == bin_a
        _, move_id = await _draft_receipt(env, Decimal("2"))
        move = await StockMove.by_id(env.company_id, move_id)
        assert move is not None
        suggestions = await env.di.placement_service.suggest_by_allowed_group_rank_and_pick_sequence_asc(
            company_id=env.company_id,
            warehouse=env.warehouse,
            move=move,
        )
        assert suggestions[0].location_id == bin_a

    async def test_set_active_off_drops_rule(self, stock_di, unique_id: str) -> None:
        env = await _env(stock_di, unique_id)
        bin_b = await _bin(env, f"O{unique_id}")
        rule = await StockPutawayRule.create(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            location_in_id=env.warehouse.view_location_id,
            location_out_id=bin_b,
            product_id=env.product.product_id,
        )
        await StockPutawayRule.update_is_active(env.company_id, rule.rule_id, False)
        _, move_id = await _draft_receipt(env, Decimal("2"))
        move = await StockMove.by_id(env.company_id, move_id)
        assert move is not None
        suggestions = await env.di.placement_service.suggest_by_allowed_group_rank_and_pick_sequence_asc(
            company_id=env.company_id,
            warehouse=env.warehouse,
            move=move,
        )
        by_reason = {s.location_id: s.reason_code for s in suggestions}
        assert by_reason.get(bin_b) != "rule_match"

    async def test_delete_rule(self, stock_di, unique_id: str) -> None:
        env = await _env(stock_di, unique_id)
        bin_b = await _bin(env, f"P{unique_id}")
        rule = await StockPutawayRule.create(
            company_id=env.company_id,
            warehouse_id=env.warehouse.warehouse_id,
            location_in_id=env.warehouse.view_location_id,
            location_out_id=bin_b,
            product_id=env.product.product_id,
        )
        await StockPutawayRule.delete_rule(env.company_id, rule.rule_id)
        assert await StockPutawayRule.by_id(env.company_id, rule.rule_id) is None
        listed = await StockPutawayRule.list_for_warehouse_by_sequence_and_rule_id_asc(
            env.company_id, env.warehouse.warehouse_id
        )
        assert all(r.rule_id != rule.rule_id for r in listed)
