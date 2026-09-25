"""Preview-рендер промпта: один `op_*` для REST и WS RPC."""

from __future__ import annotations

from apps.flows.di import Di
from apps.flows.realtime.operations import (
    require_company_member,
)
from apps.flows.src.models.prompt_api import RenderPromptRequest, RenderPromptResponse
from core.models.identity_models import User
from core.types import JsonObject
from core.variables import UnmatchedBracesError, VariableResolver, scan_prompt_template
from core.websocket import (
    raise_invalid,
)


async def op_flows_prompts_render(
    payload: RenderPromptRequest,
    *,
    user: User,
    di: Di,
) -> RenderPromptResponse:
    _ = user
    _ = await require_company_member(di)
    resolved_variables: JsonObject | None = None
    if payload.variables:
        try:
            resolved_variables = await di.variables_service.resolve(payload.variables)
        except ValueError as exc:
            raise_invalid(exc)
    try:
        rendered = VariableResolver.render_template(
            template=payload.prompt,
            local_vars=resolved_variables,
            safe=True,
            include_system=True,
        )
    except UnmatchedBracesError as exc:
        raise_invalid(exc)
    used_variables = list(
        dict.fromkeys(ref.name for ref in scan_prompt_template(payload.prompt).refs)
    )
    return RenderPromptResponse(rendered=rendered, used_variables=used_variables)
