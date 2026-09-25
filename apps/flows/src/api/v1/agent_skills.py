"""REST-зеркало каталога Agent Skills: path/query → тот же `op_*`, что и WS."""

from typing import Annotated

from fastapi import APIRouter, Query

from apps.flows.di import Di
from apps.flows.realtime.agent_skill_operations import (
    op_flows_agent_skills_create,
    op_flows_agent_skills_ensure_seed,
    op_flows_agent_skills_import,
    op_flows_agent_skills_item,
    op_flows_agent_skills_list,
    op_flows_agent_skills_remove,
    op_flows_agent_skills_update,
)
from apps.flows.src.models.agent_skill import (
    AgentSkill,
    AgentSkillDeletedResponse,
    AgentSkillEnsureSeedResponse,
    AgentSkillIdPayload,
    AgentSkillImportRequest,
    AgentSkillListPayload,
    AgentSkillUpdatePayload,
    AgentSkillUpdateRequest,
)
from core.context import require_context
from core.pagination import OffsetPage
from core.websocket import EmptyPayload

router = APIRouter(tags=["agent-skills"])


@router.get("/agent-skills")
async def list_agent_skills(
    di: Di,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[AgentSkill]:
    return await op_flows_agent_skills_list(
        AgentSkillListPayload(limit=limit, offset=offset),
        user=require_context().user,
        di=di,
    )


@router.post("/agent-skills", status_code=201)
async def create_agent_skill(
    payload: AgentSkill,
    di: Di,
) -> AgentSkill:
    return await op_flows_agent_skills_create(
        payload,
        user=require_context().user,
        di=di,
    )


@router.post("/agent-skills/import", status_code=201)
async def import_agent_skill_md(
    payload: AgentSkillImportRequest,
    di: Di,
) -> AgentSkill:
    return await op_flows_agent_skills_import(
        payload,
        user=require_context().user,
        di=di,
    )


@router.post("/agent-skills/ensure-seed")
async def ensure_agent_skills_seed(
    di: Di,
) -> AgentSkillEnsureSeedResponse:
    return await op_flows_agent_skills_ensure_seed(
        EmptyPayload(),
        user=require_context().user,
        di=di,
    )


@router.get("/agent-skills/{agent_skill_id}")
async def get_agent_skill(
    agent_skill_id: str,
    di: Di,
) -> AgentSkill:
    return await op_flows_agent_skills_item(
        AgentSkillIdPayload(agent_skill_id=agent_skill_id),
        user=require_context().user,
        di=di,
    )


@router.put("/agent-skills/{agent_skill_id}")
async def update_agent_skill(
    agent_skill_id: str,
    body: AgentSkillUpdateRequest,
    di: Di,
) -> AgentSkill:
    return await op_flows_agent_skills_update(
        AgentSkillUpdatePayload.model_validate(
            {"agent_skill_id": agent_skill_id, **body.model_dump()}
        ),
        user=require_context().user,
        di=di,
    )


@router.delete("/agent-skills/{agent_skill_id}", response_model=AgentSkillDeletedResponse)
async def delete_agent_skill(
    agent_skill_id: str,
    di: Di,
) -> AgentSkillDeletedResponse:
    return await op_flows_agent_skills_remove(
        AgentSkillIdPayload(agent_skill_id=agent_skill_id),
        user=require_context().user,
        di=di,
    )
