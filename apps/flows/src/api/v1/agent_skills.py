"""API endpoints для Agent Skills catalog."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models.agent_skill import AgentSkill, AgentSkillActivation
from apps.flows.src.models.tool_reference import ToolReference
from apps.flows.src.services.agent_skill_service import (
    AgentSkillCreateInput,
    AgentSkillUpdateInput,
)
from apps.flows.src.services.platform_assistant_skills import (
    ensure_platform_assistant_skills_for_company,
)
from core.context import require_active_company
from core.files.file_ref import FileRef
from core.logging import get_logger
from core.models import StrictBaseModel
from core.pagination import OffsetPage

logger = get_logger(__name__)

router = APIRouter(tags=["agent-skills"])

_SKILLS_MAX_LIMIT = 200


class AgentSkillCreateRequest(StrictBaseModel):
    agent_skill_id: str
    name: str
    description: str
    body_markdown: str
    tool_refs: list[ToolReference] = []
    depends_on: list[str] = []
    references: list[FileRef] = []
    assets: list[FileRef] = []
    activation: AgentSkillActivation = "explicit"


class AgentSkillUpdateRequest(StrictBaseModel):
    name: str
    description: str
    body_markdown: str
    tool_refs: list[ToolReference] = []
    depends_on: list[str] = []
    references: list[FileRef] = []
    assets: list[FileRef] = []
    activation: AgentSkillActivation = "explicit"


class AgentSkillImportRequest(StrictBaseModel):
    markdown: str
    agent_skill_id: str | None = None
    persist: bool = True


class AgentSkillEnsureSeedResponse(StrictBaseModel):
    seeded: int


@router.get("/agent-skills")
async def list_agent_skills(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=_SKILLS_MAX_LIMIT)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[AgentSkill]:
    service = container.agent_skill_service
    items = await service.list_skills(limit=limit, offset=offset)
    total = await service.count_skills()
    return OffsetPage(items=items, total=total, limit=limit, offset=offset)


@router.post("/agent-skills", status_code=201)
async def create_agent_skill(
    payload: AgentSkillCreateRequest,
    container: ContainerDep,
) -> AgentSkill:
    try:
        return await container.agent_skill_service.create(
            AgentSkillCreateInput.model_validate(payload.model_dump(mode="python"))
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/agent-skills/import", status_code=201)
async def import_agent_skill_md(
    payload: AgentSkillImportRequest,
    container: ContainerDep,
) -> AgentSkill:
    try:
        return await container.agent_skill_service.import_skill_md(
            payload.markdown,
            agent_skill_id=payload.agent_skill_id,
            persist=payload.persist,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/agent-skills/ensure-seed")
async def ensure_agent_skills_seed(
    container: ContainerDep,
) -> AgentSkillEnsureSeedResponse:
    company = require_active_company()
    seeded = await ensure_platform_assistant_skills_for_company(
        container.agent_skill_service,
        container.files_service,
        company.company_id,
    )
    return AgentSkillEnsureSeedResponse(seeded=seeded)


@router.get("/agent-skills/{agent_skill_id}")
async def get_agent_skill(
    agent_skill_id: str,
    container: ContainerDep,
) -> AgentSkill:
    try:
        return await container.agent_skill_service.get(agent_skill_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/agent-skills/{agent_skill_id}")
async def update_agent_skill(
    agent_skill_id: str,
    payload: AgentSkillUpdateRequest,
    container: ContainerDep,
) -> AgentSkill:
    try:
        return await container.agent_skill_service.update(
            agent_skill_id,
            AgentSkillUpdateInput.model_validate(payload.model_dump(mode="python")),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/agent-skills/{agent_skill_id}", status_code=204)
async def delete_agent_skill(
    agent_skill_id: str,
    container: ContainerDep,
) -> None:
    try:
        await container.agent_skill_service.delete(agent_skill_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
