"""Решения рефлексов (stock_decisions) — «точки выбора склада».

«Рефлекс» — место в бизнес-процессе, где система должна выбрать
конкретный адрес: в какую ячейку положить привезённый паллет
(putaway), из какой ячейки взять товар на сборку (pick). Запись решения
фиксирует запрос («куда положить 10 шт муки на складе W»), выбранный
вариант («ячейка A-03-02»), что применилось и почему — для аудита и
переучёта стратегий.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index

from apps.stock.models.common import STOCK_DB, stock_warehouse_lane
from apps.stock.models.enums import (
    ReflexMode,
    ReflexPoint,
    StockDecisionStatus,
)
from core.lanes import LaneOutcome, LaneRun, LaneScope, run_in_lanes
from core.models.platform_model import PlatformModel
from core.utils.time import utcnow


class StockDecision(PlatformModel):
    """Запись рефлекса: запрос/ответ точки принятия решения. Таблица ``stock_decisions``.

    Когда накладная доходит до точки выбора (putaway-рефлекс на
    приёмке), сюда пишется: кто просил (``transfer_id``), что предложили
    (``candidate_location_ids``), что выбрали
    (``chosen_location_id``), статус. Это аудиторский след решений
    стратегии — почему товар положили именно сюда.
    """

    __database_alias__: ClassVar[str | None] = STOCK_DB
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "stock_decisions"
        indexes: list[Index] = [
            Index(["company_id", "transfer_id"]),
            Index(["company_id", "move_id"]),
        ]

    decision_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    warehouse_id: str = DbField(max_length=64)
    operation_type_id: str = DbField(max_length=64)
    reflex_point: ReflexPoint = DbField()
    move_id: str | None = DbField(default=None, max_length=64)
    transfer_id: str | None = DbField(default=None, max_length=64)
    mode: ReflexMode = DbField()
    flow_id: str | None = DbField(default=None, max_length=64)
    candidate_location_ids: list[str] = DbField(db_type="JSONB", default_factory=list)
    chosen_location_id: str | None = DbField(default=None, max_length=64)
    status: StockDecisionStatus = DbField(default=StockDecisionStatus.SUGGESTED)
    created_at: datetime = DbField()
    applied_at: datetime | None = DbField(default=None)

    @classmethod
    async def create(cls, row: Self) -> Self:
        return await cls.objects.create(instance=row)

    @classmethod
    async def by_id(cls, company_id: str, decision_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, decision_id=decision_id
        ).get_or_none()

    @classmethod
    async def latest_for_transfer_by_created_at_desc(
        cls, company_id: str, transfer_id: str
    ) -> Self | None:
        """Последнее решение накладной, ORDER BY created_at DESC. Несколько с одним created_at — какое именно, не задано. Нет строки — None."""
        return await cls.objects.filter(
            company_id=company_id, transfer_id=transfer_id
        ).order_by("-created_at").first()

    @classmethod
    async def mark_applied(cls, decision_id: str, chosen_location_id: str) -> None:
        _ = await cls.objects.filter(decision_id=decision_id).update(
            using=STOCK_DB,
            status=StockDecisionStatus.APPLIED,
            chosen_location_id=chosen_location_id,
            applied_at=utcnow(),
        )

    @classmethod
    async def apply_in_lane(
        cls,
        *,
        company_id: str,
        warehouse_id: str,
        decision: Self,
        idempotency_key: str,
        actor_user_id: str,
        command_type: str,
    ) -> LaneRun[Self]:
        """Запись решения рефлекса в полосе склада — идемпотентна по команде."""

        async def body(_scope: LaneScope) -> LaneOutcome[Self]:
            created = await cls.objects.create(instance=decision)
            return LaneOutcome(result=created, events=[])

        return await run_in_lanes(
            [stock_warehouse_lane(company_id, warehouse_id)],
            company_id=company_id,
            using=STOCK_DB,
            idempotency_key=idempotency_key,
            command_type=command_type,
            actor_user_id=actor_user_id,
            result_type=cls,
            body=body,
        )
