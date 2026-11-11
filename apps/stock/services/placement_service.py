"""Размещение запаса: куда положить, откуда взять, что где лежит.

Агрегат «где запас»: две зеркальные задачи WMS.

* **Putaway** (вход) — подсказка «куда поставить приход»:
  ``suggest``/``collect_candidates`` читают всю топологию площадки,
  ранжируют ячейки правилами ``stock_putaway_rules`` и цепочками
  ``putaway_strategies`` типов хранения (SAP EWM); ``resolve_putaway``
  — рефлекс между ``confirm`` и ``assign``, выбор фиксируется
  аудируемым ``StockDecision``.
* **Removal** (выход) — резолвер стратегии отбора по цепочке
  «товар → тип хранения зоны → склад» (FEFO/FIFO/…): чтение
  справочников до входа в полосу, сам порядок кандидатов — чистая
  функция ``order_candidates_by_strategy_asc`` внутри lane-транзакции.
* **Quants** — «ведомость запасов»: какой товар в какой ячейке
  физически лежит и сколько зарезервировано.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import cast

from apps.stock.config import get_stock_settings
from apps.stock.models import (
    ReflexMode,
    ReflexPoint,
    StockDecision,
    StockDecisionStatus,
    StockLocation,
    StockLocationUsage,
    StockMove,
    StockOperationType,
    StockProduct,
    StockPutawayRule,
    StockPutawayStrategy,
    StockQuant,
    StockRemovalStrategy,
    StockStorageType,
    StockTransfer,
    StockWarehouse,
)
from apps.stock.models.common import STOCK_DB
from apps.stock.models.storage_rules import (
    BinContent,
    PlacementItem,
    check_placement,
)
from apps.stock.services.ids import new_id
from core.catalog.models import CatalogProduct
from core.clients.a2a_client import A2AClient, A2AClientError, A2ATaskResult
from core.config import get_settings
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.lanes import publish_lane_run
from core.pagination import OffsetPage
from core.request_scope import command_idempotency_key
from core.types import JsonObject, require_json_object
from core.utils.time import utcnow


@dataclass(frozen=True)
class PutawaySuggestion:
    """Одна подсказка «куда поставить приход» — без побочных эффектов.

    ``reason_code`` объясняет выбор/отказ стабильным кодом:

    * ``rule_match`` — ячейка дала правило размещения (`putaway_rules`);
    * ``empty_bin`` — пустая ячейка (стратегия `empty_bin`);
    * ``same_product`` — там уже лежит тот же товар (стратегия
      `existing_stock`, догрузка);
    * ``nearest`` — ячейка подошла шагом `nearest` цепочки типа
      хранения (порядок — `pick_sequence`);
    * ``available`` — ячейка без типа хранения (общего назначения);
    * ``manual`` / ``strategy_no_match`` — цепочка типа хранения не
      предлагает ячейку (`manual` — стратегия «выбирает оператор»);
    * ``storage_*`` — код нарушения `check_placement`, если ячейка
      отклонена (capacity, смешивание товаров/партий, политика тары);
    * ``location_blocked`` — приёмка в ячейку закрыта или она
      деактивирована.
    """

    location_id: str
    name: str
    reason_code: str
    allowed: bool


_PUTAWAY_USAGES = frozenset(
    {StockLocationUsage.BIN, StockLocationUsage.CONTAINER}
)


def _strategy_rank(
    strategies: list[StockPutawayStrategy],
    *,
    has_same_product: bool,
    is_empty: bool,
) -> int | None:
    """Позиция первой подходящей стратегии в цепочке типа хранения.

    Семантика шагов (SAP EWM): ``existing_stock`` — в ячейке уже лежит
    этот товар (догрузка); ``empty_bin`` — ячейка полностью свободна;
    ``nearest`` — любая допустимая ячейка, «ближайшая» выражается
    порядком ``pick_sequence``; ``manual`` — ячейка не подсказывается
    (оператор выбирает сам): шаг не матчит ничего, а тип хранения,
    чья цепочка состоит только из ``manual``, никогда не предлагается.

    ``None`` — ни одна стратегия цепочки не подошла: ячейку не
    предлагаем, даже если она физически вместит приход.
    """
    for index, strategy in enumerate(strategies):
        if strategy is StockPutawayStrategy.EXISTING_STOCK and has_same_product:
            return index
        if strategy is StockPutawayStrategy.EMPTY_BIN and is_empty:
            return index
        if strategy is StockPutawayStrategy.NEAREST:
            return index
    return None


class PlacementService:
    """Размещение и отбор запаса + ведомость остатков.

    Рефлекс `putaway` для incoming-движений и резолвер стратегии
    отбора для исходящих: обе стороны решают «в какой ячейке запас» —
    при приёмке куда поставить, при отгрузке откуда снять.
    """

    # --- Ведомость запасов ---

    async def list_quants(
        self,
        *,
        company_id: str,
        location_id: str | None,
        product_id: str | None,
        limit: int,
        owner_entity_id: str | None = None,
        offset: int,
        warehouse_id: str | None = None,
        subtree_location_id: str | None = None,
    ) -> OffsetPage[StockQuant]:
        """Остатки по локациям/товару — «ведомость запасов» с фильтром.

        Каждая строка — один товар в одной ячейке (и одной партии/
        владельце): ``quantity`` физически лежит,
        ``reserved_quantity`` обещано накладными,
        ``available = quantity - reserved`` реально можно брать.

        ``subtree_location_id`` расширяет фильтр до всего поддерева
        локации (отчёт «остатки по зоне/складу»); ``location_id``
        остаётся фильтром ровно одной ячейки — заданное поддерево
        имеет приоритет.
        """
        location_ids: list[str] | None = None
        if subtree_location_id is not None:
            location_ids = await StockLocation.list_subtree_ids_by_parent_path_asc(
                company_id, subtree_location_id
            )
        elif location_id is not None:
            location_ids = [location_id]
        rows = await StockQuant.list_by_product_and_location_asc(
            company_id,
            location_id=None,
            location_ids=location_ids,
            warehouse_id=warehouse_id,
            product_id=product_id,
            owner_entity_id=owner_entity_id,
            limit=limit,
            offset=offset,
        )
        total = await StockQuant.count_by_location_product_and_owner(
            company_id,
            location_id=None,
            location_ids=location_ids,
            warehouse_id=warehouse_id,
            product_id=product_id,
            owner_entity_id=owner_entity_id,
        )
        return OffsetPage(items=rows, total=total, limit=limit, offset=offset)

    # --- Putaway: куда поставить приход ---

    async def collect_candidates(
        self,
        *,
        company_id: str,
        warehouse: StockWarehouse,
        move: StockMove,
        owner_entity_id: str | None = None,
    ) -> list[str]:
        """Упорядоченные `location_id` кандидатов: правила → всё дерево склада.

        Вселенная кандидатов — вся топология площадки (поддерево
        ``view_location_id``): приёмку ставят и в bulk-ячейки, и в
        forward-зоны, и в контейнеры. Ранжирование внутри вселенной
        делают цепочки ``putaway_strategies`` типов хранения ячеек
        (``suggest``); фильтрацию «кому куда» — ``StockPutawayRule``.
        """
        ordered, _rule_ids = await self._collect(
            company_id, warehouse, move, owner_entity_id
        )
        return ordered

    async def _collect(
        self,
        company_id: str,
        warehouse: StockWarehouse,
        move: StockMove,
        owner_entity_id: str | None = None,
    ) -> tuple[list[str], set[str]]:
        """Кандидаты + множество id, пришедших из правил размещения."""
        product = await StockProduct.by_id(company_id, move.product_id)
        category = product.category if product is not None else ""
        subtree = await StockLocation.list_subtree_ids_by_parent_path_asc(
            company_id, warehouse.view_location_id
        )
        rules = await StockPutawayRule.list_active_matched_by_sequence_asc_and_specificity_desc(
            company_id=company_id,
            warehouse_id=warehouse.warehouse_id,
            product_id=move.product_id,
            category=category,
            location_ids=subtree + [move.location_dest_id],
            owner_entity_id=owner_entity_id,
        )
        ordered: list[str] = []
        rule_ids: set[str] = set()
        for rule in rules:
            if rule.location_out_id not in ordered:
                ordered.append(rule.location_out_id)
                rule_ids.add(rule.location_out_id)
        for location_id in subtree:
            if location_id not in ordered:
                ordered.append(location_id)
        if move.location_dest_id not in ordered:
            ordered.append(move.location_dest_id)
        return ordered, rule_ids

    async def suggest_by_allowed_group_rank_and_pick_sequence_asc(
        self,
        *,
        company_id: str,
        warehouse: StockWarehouse,
        move: StockMove,
        owner_entity_id: str | None = None,
        limit: int = 10,
        include_rejected: bool = False,
    ) -> list[PutawaySuggestion]:
        """Top-N подсказок «куда поставить приход» с причинами.

        Чистая подсказка для ТСД/UI: читает кандидатов, типы хранения
        и текущее содержимое ячеек, прогоняет ``check_placement`` и
        возвращает упорядоченные варианты. Ничего не пишет: применённый
        выбор — это отдельный аудируемый ``StockDecision``.

        Пример: приход 10 коробов муки. Кандидаты: [A-01 (из правила),
        B-02 (пустая), C-03 (там уже сахар)]. Получим:

        * A-01, ``rule_match`` — правило «муку в зону сыпучих»;
        * B-02, ``empty_bin`` — свободная ячейка;
        * C-03, ``storage_product_mixed``, allowed=False — если
          ``include_rejected``: видно, почему ячейка не предложена.
        """
        ordered, rule_ids = await self._collect(
            company_id, warehouse, move, owner_entity_id
        )
        if not ordered:
            return []
        locations = await StockLocation.found_in_company_by_ids(company_id, ordered)
        bins = [
            loc
            for loc_id in ordered
            if (loc := locations.get(loc_id)) is not None
            and loc.usage in _PUTAWAY_USAGES
        ]
        bin_ids = [loc.location_id for loc in bins]
        storage_types = await StockStorageType.found_in_company_by_ids(
            company_id,
            sorted(
                {loc.storage_type_id for loc in bins if loc.storage_type_id}
            ),
        )
        quants = await StockQuant.list_unordered_for_locations(company_id, bin_ids)
        children = await StockLocation.unordered_child_containers_by_parent(company_id, bin_ids)
        quants_by_loc: dict[str, list[StockQuant]] = {}
        for quant in quants:
            quants_by_loc.setdefault(quant.location_id, []).append(quant)

        # Вес/объём содержимого ячеек — через карточки каталога, чтобы
        # проверка ёмкости видела уже стоящий груз, а не только приход.
        product_by_id = await CatalogProduct.found_in_company_by_ids(
            company_id,
            sorted(
                {q.product_id for q in quants} | {move.product_id}
            ),
        )
        move_product = product_by_id.get(move.product_id)
        weight = (
            move_product.weight * move.product_qty
            if move_product is not None and move_product.weight is not None
            else None
        )
        volume = (
            move_product.volume * move.product_qty
            if move_product is not None and move_product.volume is not None
            else None
        )
        placing = PlacementItem(
            product_ids=frozenset({move.product_id}),
            lot_ids=frozenset(),
            container_type_id=None,
            total_weight=weight,
            total_volume=volume,
        )

        # group: 0 — совпадение правила размещения (всегда сильнее),
        # 1 — ячейка подошла по цепочке putaway_strategies её типа
        # хранения, 2 — ячейка без типа хранения (общего назначения).
        # rank: позиция правила в `ordered` / индекс стратегии в цепочке.
        ranked: list[tuple[bool, int, int, int, PutawaySuggestion]] = []
        for order, loc in enumerate(bins):
            inside = [q for q in quants_by_loc.get(loc.location_id, []) if q.quantity > 0]
            child_containers = children.get(loc.location_id, [])
            existing = BinContent(
                product_ids=frozenset(q.product_id for q in inside),
                lot_ids=frozenset(q.lot_id for q in inside if q.lot_id),
                container_type_ids=frozenset(
                    c.container_type_id for c in child_containers
                    if c.container_type_id
                ),
                container_count=len(child_containers),
                has_loose=bool(inside),
                total_weight=sum(
                    (
                        q.quantity * p.weight
                        for q in inside
                        if (p := product_by_id.get(q.product_id))
                        is not None
                        and p.weight is not None
                    ),
                    Decimal("0"),
                ),
                total_volume=sum(
                    (
                        q.quantity * p.volume
                        for q in inside
                        if (p := product_by_id.get(q.product_id))
                        is not None
                        and p.volume is not None
                    ),
                    Decimal("0"),
                ),
            )
            group, rank = 2, order
            if loc.putaway_blocked or not loc.is_active:
                reason, allowed = "location_blocked", False
            else:
                storage_type = (
                    storage_types.get(loc.storage_type_id)
                    if loc.storage_type_id is not None
                    else None
                )
                violation = (
                    check_placement(
                        storage_type=storage_type,
                        placing=placing,
                        existing=existing,
                    )
                    if storage_type is not None
                    else None
                )
                if violation is not None:
                    reason, allowed = violation, False
                elif loc.location_id in rule_ids:
                    reason, allowed, group, rank = "rule_match", True, 0, order
                elif storage_type is not None:
                    matched = _strategy_rank(
                        storage_type.putaway_strategies,
                        has_same_product=move.product_id in existing.product_ids,
                        is_empty=not inside and not child_containers,
                    )
                    if matched is None:
                        reason, allowed = (
                            ("manual", False)
                            if StockPutawayStrategy.MANUAL
                            in storage_type.putaway_strategies
                            else ("strategy_no_match", False)
                        )
                    else:
                        strategy = storage_type.putaway_strategies[matched]
                        reason = (
                            "empty_bin"
                            if strategy is StockPutawayStrategy.EMPTY_BIN
                            else (
                                "same_product"
                                if strategy is StockPutawayStrategy.EXISTING_STOCK
                                else "nearest"
                            )
                        )
                        allowed, group, rank = True, 1, matched
                else:
                    reason, allowed = "available", True
            if allowed or include_rejected:
                ranked.append(
                    (
                        not allowed,
                        group,
                        rank,
                        loc.pick_sequence or 0,
                        PutawaySuggestion(
                            location_id=loc.location_id,
                            name=loc.complete_name or loc.name or loc.location_id,
                            reason_code=reason,
                            allowed=allowed,
                        ),
                    )
                )
        ranked.sort(key=lambda row: (row[0], row[1], row[2], row[3]))
        return [row[4] for row in ranked[:limit]]

    async def resolve_putaway(
        self,
        *,
        company_id: str,
        warehouse: StockWarehouse,
        operation_type: StockOperationType,
        move: StockMove,
        owner_entity_id: str | None = None,
    ) -> StockDecision | None:
        """Выбор destination по `putaway_mode`; `None` — рефлекс не настроен.

        Возвращает НЕзаписанный `StockDecision`: строка вставляется в теле
        lane-транзакции вызывающей команды вместе с применением выбора.
        """
        mode = operation_type.putaway_mode
        candidates = await self.collect_candidates(
            company_id=company_id,
            warehouse=warehouse,
            move=move,
            owner_entity_id=owner_entity_id,
        )
        if not candidates:
            return None
        chosen: str | None = None
        status = StockDecisionStatus.APPLIED
        if mode == ReflexMode.RULE:
            suggestions = await self.suggest_by_allowed_group_rank_and_pick_sequence_asc(
                company_id=company_id,
                warehouse=warehouse,
                move=move,
                owner_entity_id=owner_entity_id,
                limit=1,
            )
            if not suggestions:
                return None
            chosen = suggestions[0].location_id
        elif mode == ReflexMode.INLINE:
            if operation_type.putaway_flow_id is None:
                raise PlatformConflictError(
                    "Operation type inline mode requires putaway_flow_id",
                    error_code="putaway_flow_missing",
                )
            chosen = await self._call_flow(
                company_id=company_id,
                flow_id=operation_type.putaway_flow_id,
                move=move,
                candidates=candidates,
            )
            if chosen is None or chosen not in candidates:
                raise PlatformConflictError(
                    "Putaway flow returned location outside candidates",
                    error_code="putaway_choice_invalid",
                )
        elif mode == ReflexMode.SHADOW:
            if operation_type.putaway_flow_id is not None:
                chosen = await self._call_flow(
                    company_id=company_id,
                    flow_id=operation_type.putaway_flow_id,
                    move=move,
                    candidates=candidates,
                )
            if chosen is None or chosen not in candidates:
                chosen = candidates[0]
            status = StockDecisionStatus.SUGGESTED
        else:
            raise PlatformConflictError(
                f"Unknown putaway mode {mode}", error_code="putaway_mode_invalid"
            )
        return StockDecision(
            decision_id=new_id("dec"),
            company_id=company_id,
            warehouse_id=warehouse.warehouse_id,
            operation_type_id=operation_type.operation_type_id,
            reflex_point=ReflexPoint.PUTAWAY,
            move_id=move.move_id,
            transfer_id=move.transfer_id,
            mode=mode,
            flow_id=operation_type.putaway_flow_id,
            candidate_location_ids=candidates,
            chosen_location_id=chosen,
            status=status,
            created_at=utcnow(),
            applied_at=utcnow() if status == StockDecisionStatus.APPLIED else None,
        )

    async def _call_flow(
        self,
        *,
        company_id: str,
        flow_id: str,
        move: StockMove,
        candidates: list[str],
    ) -> str | None:
        """Sync-вызов flow через A2A (единственный sync-вызов stock→flows)."""
        flows_base = get_settings().server.get_flows_service_url().rstrip("/")
        timeout = get_stock_settings().putaway_flow_timeout_seconds
        client = A2AClient(timeout=timeout)
        variables: JsonObject = {
            "company_id": company_id,
            "move_id": move.move_id,
            "product_id": move.product_id,
            "quantity": str(move.product_uom_qty),
            "candidate_location_ids": candidates,
        }
        try:
            result = await client.send_task(
                base_url=f"{flows_base}/flows/api/v1/{flow_id}",
                content="Stock putaway: выбери location_id из candidate_location_ids",
                metadata={"variables": variables},
                timeout=timeout,
            )
        except A2AClientError as exc:
            raise PlatformConflictError(
                "Putaway flow call failed", error_code="putaway_flow_failed"
            ) from exc
        return self._extract_choice(result)

    @staticmethod
    def _extract_choice(result: A2ATaskResult) -> str | None:
        """`chosen_location_id`/`location_id` из data-артефактов или текста ответа."""
        for artifact in result.artifacts:
            parts = artifact.get("parts")
            if not isinstance(parts, list):
                continue
            for part in parts:
                if not isinstance(part, dict):
                    continue
                data = part.get("data")
                if isinstance(data, dict):
                    found = PlacementService._choice_from_payload(data)
                    if found is not None:
                        return found
        return PlacementService._choice_from_text(result.response)

    @staticmethod
    def _choice_from_payload(payload: JsonObject) -> str | None:
        for key in ("chosen_location_id", "location_id", "location_dest_id"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    @staticmethod
    def _choice_from_text(text: str) -> str | None:
        stripped = text.strip()
        if not stripped:
            return None
        parsed = PlacementService._json_object_or_none(stripped)
        if parsed is not None:
            return PlacementService._choice_from_payload(parsed)
        if "{" in stripped:
            start = stripped.find("{")
            end = stripped.rfind("}")
            if end > start:
                parsed = PlacementService._json_object_or_none(stripped[start : end + 1])
                if parsed is None:
                    return None
                return PlacementService._choice_from_payload(parsed)
        return None

    @staticmethod
    def _json_object_or_none(text: str) -> JsonObject | None:
        try:
            return require_json_object(cast(object, json.loads(text)), "putaway_response")
        except (ValueError, TypeError):
            return None

    async def apply_decision(
        self,
        *,
        company_id: str,
        move_id: str,
        location_id: str,
        idempotency_key: str | None = None,
        actor_user_id: str = "system",
        command_type: str = "stock/move/apply_decision_requested",
    ) -> StockDecision:
        """`stock/move/apply_decision`: ручной/агентный выбор из кандидатов."""
        move = await StockMove.by_id(company_id, move_id)
        if move is None:
            raise PlatformNotFoundError("Move not found", error_code="move_not_found")
        if move.transfer_id is None:
            raise PlatformConflictError(
                "Move without transfer cannot take putaway decision",
                error_code="move_orphan",
            )
        transfer = await StockTransfer.by_id(company_id, move.transfer_id)
        if transfer is None:
            raise PlatformNotFoundError(
                "Transfer not found", error_code="transfer_not_found"
            )
        warehouse = await StockWarehouse.by_id(company_id, transfer.warehouse_id)
        operation_type = await StockOperationType.by_id(
            company_id, transfer.operation_type_id
        )
        if warehouse is None or operation_type is None:
            raise PlatformConflictError(
                "Transfer warehouse/operation type missing",
                error_code="transfer_config_invalid",
            )
        candidates = await self.collect_candidates(
            company_id=company_id,
            warehouse=warehouse,
            move=move,
            owner_entity_id=transfer.owner_entity_id,
        )
        if location_id not in candidates:
            raise PlatformConflictError(
                "Location is outside putaway candidates",
                error_code="putaway_choice_invalid",
            )
        location = await StockLocation.by_id(company_id, location_id)
        if location is None:
            raise PlatformConflictError(
                "Decision location not found", error_code="location_not_found"
            )
        decision = StockDecision(
            decision_id=new_id("dec"),
            company_id=company_id,
            warehouse_id=warehouse.warehouse_id,
            operation_type_id=operation_type.operation_type_id,
            reflex_point=ReflexPoint.PUTAWAY,
            move_id=move.move_id,
            transfer_id=move.transfer_id,
            mode=ReflexMode.RULE,
            candidate_location_ids=candidates,
            chosen_location_id=location_id,
            status=StockDecisionStatus.APPLIED,
            created_at=utcnow(),
            applied_at=utcnow(),
        )
        run = await StockDecision.apply_in_lane(
            company_id=company_id,
            warehouse_id=warehouse.warehouse_id,
            decision=decision,
            idempotency_key=command_idempotency_key(idempotency_key),
            actor_user_id=actor_user_id,
            command_type=command_type,
        )
        await publish_lane_run(run, using=STOCK_DB)
        return run.result

    # --- Removal: откуда снять при отборе ---

    async def resolve_for_move(
        self, *, company_id: str, move: StockMove
    ) -> StockRemovalStrategy:
        """Стратегия отбора одной строки накладной по цепочке приоритета.

        Более конкретное правило побеждает: ``product.removal_strategy``
        («яйца всегда по FEFO») → ``storage_type.removal_strategy``
        («в холодной зоне FIFO»; ``None`` — наследует склад) →
        ``warehouse.removal_strategy`` — обязательная политика: цепочка
        всегда замыкается здесь, незаданная политика это ошибка
        конфигурации, а не дефолт.

        Move без склада — ``removal_strategy_unresolved``: резерв
        без политики недопустим, молчаливого дефолта нет.
        """
        product = await StockProduct.by_id(company_id, move.product_id)
        if product is not None and product.removal_strategy is not None:
            return product.removal_strategy
        source = await StockLocation.by_id(company_id, move.location_id)
        if source is not None and source.storage_type_id is not None:
            storage_type = await StockStorageType.by_id(
                company_id, source.storage_type_id
            )
            if (
                storage_type is not None
                and storage_type.removal_strategy is not None
            ):
                return storage_type.removal_strategy
        if move.warehouse_id is None:
            raise PlatformConflictError(
                "Move has no warehouse to resolve removal strategy",
                error_code="removal_strategy_unresolved",
            )
        warehouse = await StockWarehouse.by_id(company_id, move.warehouse_id)
        if warehouse is None:
            raise PlatformConflictError(
                "Warehouse not found for removal strategy",
                error_code="removal_strategy_unresolved",
            )
        return warehouse.removal_strategy

    async def resolve_for_transfer(
        self, *, company_id: str, moves: list[StockMove]
    ) -> dict[str, StockRemovalStrategy]:
        """Карта ``move_id → стратегия`` для пакетной раскладки резерва."""
        result: dict[str, StockRemovalStrategy] = {}
        for move in moves:
            result[move.move_id] = await self.resolve_for_move(
                company_id=company_id, move=move
            )
        return result
