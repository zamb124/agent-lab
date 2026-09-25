"""REST-зеркало веток flow: тот же `op_*`, что и WS."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from apps.flows.di import Di
from apps.flows.realtime.operations import (
    FlowsBranchIdPayload,
    op_flows_branch_create,
    op_flows_branch_remove,
    op_flows_branch_update,
)
from apps.flows.src.models import (
    BranchCreateRequest,
    BranchMutationResponse,
    BranchUpdateRequest,
)
from core.context import require_context

router = APIRouter(tags=["branches"])


@router.post("/{flow_id}/branches")
async def create_branch(
    flow_id: str,
    body: BranchCreateRequest,
    di: Di,
) -> JSONResponse:
    result = await op_flows_branch_create(
        body.model_copy(update={"flow_id": flow_id}),
        user=require_context().user,
        di=di,
    )
    return JSONResponse(result.model_dump(), status_code=201)


@router.put("/{flow_id}/branches/{branch_id}", response_model=BranchMutationResponse)
async def update_branch(
    flow_id: str,
    branch_id: str,
    body: BranchUpdateRequest,
    di: Di,
) -> BranchMutationResponse:
    return await op_flows_branch_update(
        body.model_copy(update={"flow_id": flow_id, "branch_id": branch_id}),
        user=require_context().user,
        di=di,
    )


@router.delete("/{flow_id}/branches/{branch_id}", response_model=BranchMutationResponse)
async def delete_branch(
    flow_id: str, branch_id: str, di: Di
) -> BranchMutationResponse:
    return await op_flows_branch_remove(
        FlowsBranchIdPayload(flow_id=flow_id, branch_id=branch_id),
        user=require_context().user,
        di=di,
    )
