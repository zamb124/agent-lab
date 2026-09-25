"""REST-зеркало transfers/move-lines/decisions stock."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from apps.stock.di import Di
from apps.stock.models import StockDecision, StockMoveLine, StockTransfer, StockTransferState
from apps.stock.models.api import (
    StockMoveApplyDecisionPayload,
    StockMoveLineUpdatePayload,
    StockTransferCreatePayload,
    StockTransferDetail,
    StockTransferIdPayload,
    StockTransferReturnPayload,
    StockTransfersListPayload,
)
from apps.stock.realtime.operations import (
    op_move_apply_decision,
    op_move_lines_update,
    op_transfers_assign,
    op_transfers_cancel,
    op_transfers_confirm,
    op_transfers_create,
    op_transfers_item,
    op_transfers_list,
    op_transfers_return,
    op_transfers_validate,
)
from core.context import require_context
from core.pagination import OffsetPage
from core.websocket import raise_invalid

router = APIRouter(tags=["stock-transfers"])


def _user():
    return require_context().user


@router.get("/transfers", response_model=OffsetPage[StockTransfer])
async def list_transfers(
    di: Di,
    warehouse_id: str | None = None,
    state: StockTransferState | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[StockTransfer]:
    return await op_transfers_list(
        StockTransfersListPayload(
            warehouse_id=warehouse_id,
            state=state,
            limit=limit,
            offset=offset,
        ),
        user=_user(),
        di=di,
    )


@router.post("/transfers", response_model=StockTransfer)
async def create_transfer(
    di: Di, body: StockTransferCreatePayload
) -> StockTransfer:
    return await op_transfers_create(body, user=_user(), di=di)


@router.get("/transfers/{transfer_id}", response_model=StockTransferDetail)
async def get_transfer(di: Di, transfer_id: str) -> StockTransferDetail:
    return await op_transfers_item(
        StockTransferIdPayload(transfer_id=transfer_id), user=_user(), di=di
    )


@router.post("/transfers/{transfer_id}/confirm", response_model=StockTransfer)
async def confirm_transfer(di: Di, transfer_id: str) -> StockTransfer:
    return await op_transfers_confirm(
        StockTransferIdPayload(transfer_id=transfer_id), user=_user(), di=di
    )


@router.post("/transfers/{transfer_id}/assign", response_model=StockTransfer)
async def assign_transfer(di: Di, transfer_id: str) -> StockTransfer:
    return await op_transfers_assign(
        StockTransferIdPayload(transfer_id=transfer_id), user=_user(), di=di
    )


@router.post("/transfers/{transfer_id}/validate", response_model=StockTransfer)
async def validate_transfer(di: Di, transfer_id: str) -> StockTransfer:
    return await op_transfers_validate(
        StockTransferIdPayload(transfer_id=transfer_id), user=_user(), di=di
    )


@router.post("/transfers/{transfer_id}/cancel", response_model=StockTransfer)
async def cancel_transfer(di: Di, transfer_id: str) -> StockTransfer:
    return await op_transfers_cancel(
        StockTransferIdPayload(transfer_id=transfer_id), user=_user(), di=di
    )


@router.post("/transfers/{transfer_id}/return", response_model=StockTransfer)
async def return_transfer(
    di: Di, transfer_id: str, body: StockTransferReturnPayload
) -> StockTransfer:
    if body.transfer_id != transfer_id:
        raise_invalid(ValueError("transfer_id mismatch"), error_code="path_id_mismatch")
    return await op_transfers_return(body, user=_user(), di=di)


@router.patch("/move-lines/{move_line_id}", response_model=StockMoveLine)
async def update_move_line(
    di: Di, move_line_id: str, body: StockMoveLineUpdatePayload
) -> StockMoveLine:
    if body.move_line_id != move_line_id:
        raise_invalid(ValueError("move_line_id mismatch"), error_code="path_id_mismatch")
    return await op_move_lines_update(body, user=_user(), di=di)


@router.post("/moves/apply-decision", response_model=StockDecision)
async def apply_decision(
    di: Di, body: StockMoveApplyDecisionPayload
) -> StockDecision:
    return await op_move_apply_decision(body, user=_user(), di=di)
