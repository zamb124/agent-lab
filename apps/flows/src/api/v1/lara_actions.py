"""
REST: подтверждение Lara pending-actions из embed/UI без повторного tool-call через LLM.
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from apps.flows.src.dependencies import ContainerDep
from core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/lara", tags=["Lara"])


class LaraPendingActionsApplyBody(BaseModel):
    pending_action_id: str = Field(..., min_length=1)
    context_id: str = Field(..., min_length=1)
    idempotency_key: str | None = Field(None, description="Опционально; по умолчанию из сохранённого действия")


@router.post("/pending-actions/apply")
async def lara_pending_actions_apply(body: LaraPendingActionsApplyBody, container: ContainerDep) -> dict[str, Any]:
    facade = container.lara_facade
    try:
        return await facade.apply_pending_action_from_http(
            pending_action_id=body.pending_action_id,
            context_id=body.context_id,
            idempotency_key=body.idempotency_key,
        )
    except PermissionError as e:
        logger.warning("lara_pending_apply denied: %s", e)
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        logger.info("lara_pending_apply rejected: %s", e)
        raise HTTPException(status_code=422, detail=str(e)) from e
