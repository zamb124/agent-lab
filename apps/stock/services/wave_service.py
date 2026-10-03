"""WaveService — формирование и выпуск волн сборки.

Волна группирует открытые строки исполнения в «сменный наряд».
Сервис — тонкая обвязка над lane-методами ``StockWave``: вся
запись идёт в полосе склада, push уходит после commit.
"""

from __future__ import annotations

from apps.stock.models import StockWave, StockWaveState
from apps.stock.models.common import STOCK_DB
from apps.stock.models.transfer import StockTransfer
from core.errors.boundary import (
    PlatformConflictError,
    PlatformNotFoundError,
)
from core.lanes import publish_lane_run
from core.request_scope import command_idempotency_key


class WaveService:
    """Жизненный цикл волн: собрать → выпустить → (done по строкам)."""

    async def list(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        state: StockWaveState | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[StockWave]:
        return await StockWave.list_for_warehouse(
            company_id,
            warehouse_id,
            state=state,
            limit=limit,
            offset=offset,
        )

    async def create(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        name: str | None = None,
        move_line_ids: list[str],
        move_ids: list[str],
        priority: int = 0,
        user_id: str | None = None,
        stop_transfer_ids: list[str] | None = None,
        idempotency_key: str | None = None,
        actor_user_id: str = "system",
        command_type: str = "stock/waves/create_requested",
    ) -> StockWave:
        """Сформировать волну из открытых строк — атомарно в полосе.

        ``stop_transfer_ids`` — путевой лист рейса: ``transfer_id``
        остановок в порядке объезда; строки получают ``stop_order``
        по позиции своей накладной. Каждая остановка обязана быть
        накладной этого же склада.
        """
        if stop_transfer_ids:
            if len(set(stop_transfer_ids)) != len(stop_transfer_ids):
                raise PlatformConflictError(
                    "Wave stop is duplicated",
                    error_code="wave_stop_duplicate",
                )
            transfers = await StockTransfer.by_ids(
                company_id, stop_transfer_ids
            )
            for tid in stop_transfer_ids:
                transfer = transfers.get(tid)
                if transfer is None:
                    raise PlatformNotFoundError(
                        "Wave stop transfer not found",
                        error_code="transfer_not_found",
                    )
                if transfer.warehouse_id != warehouse_id:
                    raise PlatformConflictError(
                        "Wave stop belongs to another warehouse",
                        error_code="wave_stop_warehouse_mismatch",
                    )
        run = await StockWave.create_in_lane(
            company_id=company_id,
            warehouse_id=warehouse_id,
            name=name,
            move_line_ids=move_line_ids,
            move_ids=move_ids,
            priority=priority,
            user_id=user_id,
            stop_transfer_ids=stop_transfer_ids,
            idempotency_key=command_idempotency_key(idempotency_key),
            actor_user_id=actor_user_id,
            command_type=command_type,
        )
        await publish_lane_run(run, using=STOCK_DB)
        return run.result

    async def release(
        self,
        *,
        company_id: str,
        warehouse_id: str,
        wave_id: str,
        idempotency_key: str | None = None,
        actor_user_id: str = "system",
        command_type: str = "stock/waves/release_requested",
    ) -> StockWave:
        """Выпустить волну — строки пошли в работу, push бригаде."""
        run = await StockWave.release_in_lane(
            company_id=company_id,
            warehouse_id=warehouse_id,
            wave_id=wave_id,
            idempotency_key=command_idempotency_key(idempotency_key),
            actor_user_id=actor_user_id,
            command_type=command_type,
        )
        await publish_lane_run(run, using=STOCK_DB)
        return run.result
