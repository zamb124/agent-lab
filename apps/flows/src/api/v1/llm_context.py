"""REST-зеркало parent LLM context: body → тот же `op_*`, что и WS."""

from fastapi import APIRouter

from apps.flows.di import Di
from apps.flows.realtime.llm_context_operations import op_flows_llm_context_resolve_parent
from apps.flows.src.models.llm_context_api import (
    LlmContextResolveParentRequest,
    LlmContextResolveParentResponse,
)
from core.context import require_context

router = APIRouter(prefix="/llm-context", tags=["llm-context"])


@router.post("/resolve-parent", response_model=LlmContextResolveParentResponse)
async def resolve_llm_context_parent(
    body: LlmContextResolveParentRequest,
    di: Di,
) -> LlmContextResolveParentResponse:
    return await op_flows_llm_context_resolve_parent(
        body,
        user=require_context().user,
        di=di,
    )
