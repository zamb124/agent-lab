"""Каталог Agent Skills: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

from apps.flows.di import Di
from apps.flows.realtime.operations import (
    require_company_member,
)
from apps.flows.src.models.agent_skill import (
    AgentSkill,
    AgentSkillDeletedResponse,
    AgentSkillEnsureSeedResponse,
    AgentSkillIdPayload,
    AgentSkillImportRequest,
    AgentSkillListPayload,
    AgentSkillUpdatePayload,
    parse_skill_md,
)
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
    di: Di,
) -> OffsetPage[AgentSkill]:
    _ = user
    _ = await require_company_member(di)
    items = await AgentSkill.list_skills(
        limit=payload.limit, offset=payload.offset
    )
    total = await AgentSkill.count_skills()
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
    di: Di,
) -> AgentSkill:
    _ = user
    _ = await require_company_member(di)
    try:
        return await AgentSkill.require_by_agent_skill_id(payload.agent_skill_id)
    except LookupError as exc:
        raise_not_found(exc)


async def op_flows_agent_skills_create(
    payload: AgentSkill,
    *,
    user: User,
    di: Di,
) -> AgentSkill:
    _ = user
    _ = await require_company_member(di)
    existing = await AgentSkill.get(AgentSkill.row_id(payload.agent_skill_id))
    if existing is not None:
        raise_conflict(ValueError(f"AgentSkill already exists: {payload.agent_skill_id}"))
    try:
        return await AgentSkill.create(payload)
    except ValueError as exc:
        raise_invalid(exc)


async def op_flows_agent_skills_update(
    payload: AgentSkillUpdatePayload,
    *,
    user: User,
    di: Di,
) -> AgentSkill:
    _ = user
    _ = await require_company_member(di)
    try:
        return await AgentSkill.update(payload)
    except LookupError as exc:
        raise_not_found(exc)
    except ValueError as exc:
        raise_invalid(exc)


async def op_flows_agent_skills_remove(
    payload: AgentSkillIdPayload,
    *,
    user: User,
    di: Di,
) -> AgentSkillDeletedResponse:
    _ = user
    _ = await require_company_member(di)
    try:
        await AgentSkill.delete_by_agent_skill_id(payload.agent_skill_id)
    except LookupError as exc:
        raise_not_found(exc)
    return AgentSkillDeletedResponse(status="deleted", agent_skill_id=payload.agent_skill_id)


async def op_flows_agent_skills_import(
    payload: AgentSkillImportRequest,
    *,
    user: User,
    di: Di,
) -> AgentSkill:
    _ = user
    _ = await require_company_member(di)
    if payload.persist:
        parsed = parse_skill_md(payload.markdown, agent_skill_id=payload.agent_skill_id)
        existing = await AgentSkill.get(AgentSkill.row_id(parsed.agent_skill_id))
        if existing is not None:
            raise_conflict(
                ValueError(f"AgentSkill already exists: {parsed.agent_skill_id}")
            )
    try:
        return await AgentSkill.import_skill_md(
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
    di: Di,
) -> AgentSkillEnsureSeedResponse:
    _ = payload
    _ = user
    scope = await require_company_member(di)
    seeded = await ensure_platform_assistant_skills_for_company(
        di.files_service,
        scope.company_id,
    )
    return AgentSkillEnsureSeedResponse(seeded=seeded)
