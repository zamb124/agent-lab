"""API: resolve parent LLM context policy for editor placeholders."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.runtime.llm_context_resource import resolve_llm_context_resource_patch
from core.config import get_settings
from core.context import get_context
from core.llm_context import LLMContextPatch
from core.llm_context.resolver import (
    resolve_company_llm_context_patch,
    resolve_llm_context_policy,
)
from core.logging import get_logger
from core.models import StrictBaseModel
from core.models.identity_models import User
from core.types import JsonObject, require_json_object

logger = get_logger(__name__)
router = APIRouter(prefix="/llm-context", tags=["llm-context"])


class LlmContextResolveParentRequest(StrictBaseModel):
    """Черновик ресурсов редактора + optional resource key (без node overlay)."""

    llm_context_resource_key: str | None = None
    flow_resources: dict[str, JsonObject] = {}
    node_resources: dict[str, JsonObject] = {}


class LlmContextResolveParentResponse(StrictBaseModel):
    """Public shape как settings llm_context: resolved + catalogs."""

    resolved: JsonObject
    profiles: list[str]
    budgets: list[str]


def _require_authenticated_user() -> User:
    context = get_context()
    if context is None:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    return context.user


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


@router.post("/resolve-parent", response_model=LlmContextResolveParentResponse)
async def resolve_llm_context_parent(
    request: LlmContextResolveParentRequest,
    container: ContainerDep,
) -> LlmContextResolveParentResponse:
    """
    Effective policy без node/call: platform → company → resource.

    Resource слой только при явном ``llm_context_resource_key`` (без auto-infer).
    """
    _ = _require_authenticated_user()
    settings = get_settings().llm_context
    company_patch = resolve_company_llm_context_patch()
    resource_patch: LLMContextPatch | None = None
    key = (request.llm_context_resource_key or "").strip()
    if key:
        try:
            resource_patch = await resolve_llm_context_resource_patch(
                llm_context_resource_key=key,
                flow_resources=request.flow_resources,
                skill_resources=None,
                node_resources_raw=request.node_resources,
                repository=container.resource_repository,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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
    logger.info(
        "llm_context resolve-parent key=%s has_resource=%s",
        key if key else "-",
        resource_patch is not None,
    )
    return LlmContextResolveParentResponse(
        resolved=resolved_public,
        profiles=list(settings.profiles.keys()),
        budgets=list(settings.budgets.keys()),
    )
