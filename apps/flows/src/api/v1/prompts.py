"""REST-зеркало preview-рендера промпта: body → тот же `op_*`, что и WS."""

from fastapi import APIRouter

from apps.flows.di import Di
from apps.flows.realtime.prompt_operations import op_flows_prompts_render
from apps.flows.src.models.prompt_api import RenderPromptRequest, RenderPromptResponse
from core.context import require_context

router = APIRouter(tags=["prompts"])


@router.post("/render", response_model=RenderPromptResponse)
async def render_prompt(
    body: RenderPromptRequest,
    di: Di,
) -> RenderPromptResponse:
    return await op_flows_prompts_render(
        body,
        user=require_context().user,
        di=di,
    )
