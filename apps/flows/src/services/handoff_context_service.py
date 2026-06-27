"""
Opt-in shared context для handoff child (HandoffContextResource).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from apps.flows.src.db import ResourceRepository
from apps.flows.src.models.resource import ResourceType
from core.models import StrictBaseModel
from core.state import ExecutionState
from core.state.interrupt import HandoffInterrupt


class HandoffContextPolicy(StrEnum):
    EXPLICIT_ONLY = "explicit_only"
    PARENT_MESSAGES_SLICE = "parent_messages_slice"
    NESTED_SUMMARY = "nested_summary"


class HandoffContextResourceConfig(StrictBaseModel):
    policy: HandoffContextPolicy = Field(
        default=HandoffContextPolicy.EXPLICIT_ONLY,
        description="explicit_only — только variables; parent_messages_slice — копия messages; nested_summary — заглушка",
    )
    message_limit: int = Field(
        default=20,
        ge=1,
        le=200,
        description="Лимит messages при parent_messages_slice",
    )


class HandoffContextService:
    _resource_repository: ResourceRepository

    def __init__(self, *, resource_repository: ResourceRepository) -> None:
        self._resource_repository = resource_repository

    async def resolve_config(
        self,
        resource_key: str | None,
    ) -> HandoffContextResourceConfig | None:
        if resource_key is None or not resource_key.strip():
            return None
        resource = await self._resource_repository.get(resource_key)
        if resource is None:
            raise ValueError(f"handoff context resource not found: {resource_key}")
        if resource.type != ResourceType.HANDOFF_CONTEXT:
            raise ValueError(
                f"resource {resource_key!r} is not handoff_context "
                + f"(got {resource.type.value})"
            )
        return HandoffContextResourceConfig.model_validate(resource.config)

    async def apply_to_child_state(
        self,
        *,
        parent_state: ExecutionState,
        child_state: ExecutionState,
        _body: HandoffInterrupt,
        resource_key: str | None,
    ) -> ExecutionState:
        config = await self.resolve_config(resource_key)
        if config is None:
            return child_state
        if config.policy == HandoffContextPolicy.EXPLICIT_ONLY:
            return child_state
        if config.policy == HandoffContextPolicy.PARENT_MESSAGES_SLICE:
            limit = config.message_limit
            child_state.messages = list(parent_state.messages[-limit:])
            return child_state
        if config.policy == HandoffContextPolicy.NESTED_SUMMARY:
            summary = _build_nested_summary(parent_state)
            if summary:
                child_state.variables = {**child_state.variables, "handoff_context_summary": summary}
            return child_state
        raise ValueError(f"unsupported handoff context policy: {config.policy.value}")


def _build_nested_summary(parent_state: ExecutionState) -> str:
    parts: list[str] = []
    if parent_state.content:
        parts.append(f"last_user: {parent_state.content}")
    if parent_state.response:
        parts.append(f"last_assistant: {parent_state.response}")
    return "\n".join(parts)


def handoff_context_resource_key_from_body(body: HandoffInterrupt) -> str | None:
    key = body.handoff_context_resource_key
    if key is None or not key.strip():
        return None
    return key.strip()
