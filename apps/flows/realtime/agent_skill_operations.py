"""Каталог Agent Skills: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

from apps.flows.realtime.operations import (
    require_company_member,
)
from apps.flows.src.container import FlowContainer
from apps.flows.src.models.agent_skill import (
    AgentSkill,
    AgentSkillDeletedResponse,
    AgentSkillEnsureSeedResponse,
    AgentSkillIdPayload,
    AgentSkillImportRequest,
    AgentSkillListPayload,
    AgentSkillUpdatePayload,
)
from apps.flows.src.services.agent_skill_service import parse_skill_md
from apps.flows.src.services.platform_assistant_skills import (
    ensure_platform_assistant_skills_for_company,
)
from core.models.identity_models import User
from core.pagination import OffsetPage
from core.websocket import (
    EmptyPayload,
    raise_conflict,
    raise_invalid,
    raise_not_found,
)


async def op_flows_agent_skills_list(
    payload: AgentSkillListPayload,
    *,
    user: User,
    container: FlowContainer,
) -> OffsetPage[AgentSkill]:
    _ = user
    _ = await require_company_member(container)
    items = await container.agent_skill_service.list_skills(
        limit=payload.limit, offset=payload.offset
    )
    total = await container.agent_skill_service.count_skills()
    return OffsetPage[AgentSkill](
        items=items,
        total=total,
        limit=payload.limit,
        offset=payload.offset,
    )


async def op_flows_agent_skills_item(
    payload: AgentSkillIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> AgentSkill:
    _ = user
    _ = await require_company_member(container)
    try:
        return await container.agent_skill_service.get(payload.agent_skill_id)
    except LookupError as exc:
        raise_not_found(exc)


async def op_flows_agent_skills_create(
    payload: AgentSkill,
    *,
    user: User,
    container: FlowContainer,
) -> AgentSkill:
    _ = user
    _ = await require_company_member(container)
    existing = await container.agent_skill_repository.get(payload.agent_skill_id)
    if existing is not None:
        raise_conflict(ValueError(f"AgentSkill already exists: {payload.agent_skill_id}"))
    try:
        return await container.agent_skill_service.create(payload)
    except ValueError as exc:
        raise_invalid(exc)


async def op_flows_agent_skills_update(
    payload: AgentSkillUpdatePayload,
    *,
    user: User,
    container: FlowContainer,
) -> AgentSkill:
    _ = user
    _ = await require_company_member(container)
    try:
        return await container.agent_skill_service.update(payload)
    except LookupError as exc:
        raise_not_found(exc)
    except ValueError as exc:
        raise_invalid(exc)


async def op_flows_agent_skills_remove(
    payload: AgentSkillIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> AgentSkillDeletedResponse:
    _ = user
    _ = await require_company_member(container)
    try:
        await container.agent_skill_service.delete(payload.agent_skill_id)
    except LookupError as exc:
        raise_not_found(exc)
    return AgentSkillDeletedResponse(status="deleted", agent_skill_id=payload.agent_skill_id)


async def op_flows_agent_skills_import(
    payload: AgentSkillImportRequest,
    *,
    user: User,
    container: FlowContainer,
) -> AgentSkill:
    _ = user
    _ = await require_company_member(container)
    if payload.persist:
        parsed = parse_skill_md(payload.markdown, agent_skill_id=payload.agent_skill_id)
        existing = await container.agent_skill_repository.get(parsed.agent_skill_id)
        if existing is not None:
            raise_conflict(
                ValueError(f"AgentSkill already exists: {parsed.agent_skill_id}")
            )
    try:
        return await container.agent_skill_service.import_skill_md(
            payload.markdown,
            agent_skill_id=payload.agent_skill_id,
            persist=payload.persist,
        )
    except ValueError as exc:
        raise_invalid(exc)


async def op_flows_agent_skills_ensure_seed(
    payload: EmptyPayload,
    *,
    user: User,
    container: FlowContainer,
) -> AgentSkillEnsureSeedResponse:
    _ = payload
    _ = user
    scope = await require_company_member(container)
    seeded = await ensure_platform_assistant_skills_for_company(
        container.agent_skill_service,
        container.files_service,
        scope.company_id,
    )
    return AgentSkillEnsureSeedResponse(seeded=seeded)
