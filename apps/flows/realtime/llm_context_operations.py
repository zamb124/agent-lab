"""Parent LLM context policy: один `op_*` для REST и WS RPC."""

from __future__ import annotations

from apps.flows.di import Di
from apps.flows.realtime.operations import (
    require_company_member,
)
from apps.flows.src.models.llm_context_api import (
    LlmContextResolveParentRequest,
    LlmContextResolveParentResponse,
)
from apps.flows.src.runtime.llm_context_resource import resolve_llm_context_resource_patch
from core.config import get_settings
from core.llm_context import LLMContextPatch
from core.llm_context.resolver import (
    resolve_company_llm_context_patch,
    resolve_llm_context_policy,
)
from core.logging import get_logger
from core.models.identity_models import User
from core.types import require_json_object
from core.websocket import (
    raise_invalid,
)

logger = get_logger(__name__)


def _parent_profile_key(
    *,
    default_profile: str,
    company: LLMContextPatch | None,
    resource: LLMContextPatch | None,
) -> str:
    if resource is not None and resource.profile is not None:
        return resource.profile
    if company is not None and company.profile is not None:
        return company.profile
    return default_profile


async def op_flows_llm_context_resolve_parent(
    payload: LlmContextResolveParentRequest,
    *,
    user: User,
    di: Di,
) -> LlmContextResolveParentResponse:
    _ = user
    _ = await require_company_member(di)
    settings = get_settings().llm_context
    company_patch = resolve_company_llm_context_patch()
    resource_patch: LLMContextPatch | None = None
    key = payload.llm_context_resource_key.strip() if payload.llm_context_resource_key else ""
    if key:
        try:
            resource_patch = await resolve_llm_context_resource_patch(
                llm_context_resource_key=key,
                flow_resources=payload.flow_resources,
                skill_resources=None,
                node_resources_raw=payload.node_resources,
            )
        except ValueError as exc:
            raise_invalid(exc)

    resolved = resolve_llm_context_policy(
        config=settings,
        company=company_patch,
        resource=resource_patch,
        node=None,
        call=None,
    )
    resolved_public = require_json_object(
        resolved.model_dump(mode="json"),
        "resolved LLM context policy",
    )
    resolved_public["profile"] = _parent_profile_key(
        default_profile=settings.default_profile,
        company=company_patch,
        resource=resource_patch,
    )
    logger.info("flows.llm_context", key=key if key else '-', has_resource=resource_patch is not None)
    return LlmContextResolveParentResponse(
        resolved=resolved_public,
        profiles=list(settings.profiles.keys()),
        budgets=list(settings.budgets.keys()),
    )
