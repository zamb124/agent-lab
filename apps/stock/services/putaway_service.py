"""Putaway-рефлекс: кандидаты — ядро, выбор — rule|inline|shadow.

Рефлекс срабатывает только между `confirm` и `assign`: ядро собирает
`candidate_location_ids` (PutawayRule + поддерево stock-локации склада),
режим `inline` вызывает произвольный `putaway_flow_id` через A2A. Ответ вне
кандидатов, пустой ответ или таймаут → `raise`: move остаётся `confirmed`.
"""

from __future__ import annotations

import json
from typing import cast

from apps.stock.config import get_stock_settings
from apps.stock.models import (
    ReflexMode,
    ReflexPoint,
    StockDecision,
    StockDecisionStatus,
    StockLocation,
    StockMove,
    StockOperationType,
    StockProduct,
    StockProductTemplate,
    StockPutawayRule,
    StockTransfer,
    StockWarehouse,
)
from apps.stock.services.ids import new_id
from core.clients.a2a_client import A2AClient, A2AClientError, A2ATaskResult
from core.config import get_settings
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.types import JsonObject, require_json_object
from core.utils.time import utcnow


class PutawayService:
    """Точка рефлекса `putaway` для incoming-движений."""

    async def collect_candidates(
        self,
        *,
        company_id: str,
        warehouse: StockWarehouse,
        move: StockMove,
    ) -> list[str]:
        """Упорядоченные `location_id` кандидатов: правила → поддерево склада."""
        product = await StockProduct.by_id(company_id, move.product_id)
        category = ""
        if product is not None:
            template = await StockProductTemplate.by_id(company_id, product.template_id)
            if template is not None:
                category = template.category
        subtree = await StockLocation.list_subtree_ids(
            company_id, warehouse.stock_location_id
        )
        rules = await StockPutawayRule.candidates_for(
            company_id=company_id,
            warehouse_id=warehouse.warehouse_id,
            product_id=move.product_id,
            category=category,
            location_ids=subtree + [move.location_dest_id],
        )
        ordered: list[str] = []
        for rule in rules:
            if rule.location_out_id not in ordered:
                ordered.append(rule.location_out_id)
        for location_id in subtree:
            if location_id not in ordered:
                ordered.append(location_id)
        if move.location_dest_id not in ordered:
            ordered.append(move.location_dest_id)
        return ordered

    async def resolve_putaway(
        self,
        *,
        company_id: str,
        warehouse: StockWarehouse,
        operation_type: StockOperationType,
        move: StockMove,
    ) -> StockDecision | None:
        """Выбор destination по `putaway_mode`; `None` — рефлекс не настроен (rule без кандидатов = текущий dest)."""
        mode = operation_type.putaway_mode
        candidates = await self.collect_candidates(
            company_id=company_id,
            warehouse=warehouse,
            move=move,
        )
        if not candidates:
            return None
        chosen: str | None = None
        status = StockDecisionStatus.APPLIED
        if mode == ReflexMode.RULE:
            chosen = candidates[0]
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
        decision = StockDecision(
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
        return await StockDecision.objects.create(instance=decision)

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
                    found = PutawayService._choice_from_payload(data)
                    if found is not None:
                        return found
        return PutawayService._choice_from_text(result.response)

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
        parsed = PutawayService._json_object_or_none(stripped)
        if parsed is not None:
            return PutawayService._choice_from_payload(parsed)
        if "{" in stripped:
            start = stripped.find("{")
            end = stripped.rfind("}")
            if end > start:
                parsed = PutawayService._json_object_or_none(stripped[start : end + 1])
                if parsed is None:
                    return None
                return PutawayService._choice_from_payload(parsed)
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
        return await StockDecision.objects.create(instance=decision)
