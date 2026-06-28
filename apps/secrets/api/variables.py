"""REST API версионируемых переменных и секретов компании."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from apps.secrets.dependencies import ContainerDep
from core.context import require_active_company, require_context
from core.pagination import OffsetPage
from core.secrets.models import (
    VariableResolveRequest,
    VariableResolveResponse,
    VariableWriteRequest,
)
from core.variables.models import PlatformVariable, ResolutionContext

router = APIRouter(prefix="/variables", tags=["variables"])


def _current_company_id() -> str:
    return require_active_company().company_id


def _current_user_id() -> str | None:
    return require_context().user.user_id


@router.get("", response_model=OffsetPage[PlatformVariable])
async def list_variables(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[PlatformVariable]:
    company_id = _current_company_id()
    service = container.secrets_service
    items = await service.list(company_id, limit=limit, offset=offset)
    total = await service.count(company_id)
    return OffsetPage[PlatformVariable](items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=PlatformVariable)
async def upsert_variable(
    container: ContainerDep, body: VariableWriteRequest
) -> PlatformVariable:
    return await container.secrets_service.upsert(
        company_id=_current_company_id(),
        request=body,
        created_by=_current_user_id(),
    )


@router.post("/resolve", response_model=VariableResolveResponse)
async def resolve_variables(
    container: ContainerDep, body: VariableResolveRequest
) -> VariableResolveResponse:
    context = ResolutionContext(
        company_id=_current_company_id(),
        user_id=body.user_id,
        namespace=body.namespace,
        channel=body.channel,
    )
    items = await container.secrets_service.resolve_bundle(context)
    return VariableResolveResponse(items=items)


@router.get("/{variable_key}/versions", response_model=OffsetPage[PlatformVariable])
async def list_variable_versions(
    container: ContainerDep,
    variable_key: str,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[PlatformVariable]:
    company_id = _current_company_id()
    service = container.secrets_service
    current = await service.get(company_id, variable_key)
    if current is None:
        raise HTTPException(status_code=404, detail="Variable not found")
    items = await service.list_versions(company_id, variable_key, limit=limit, offset=offset)
    total = await service.count_versions(company_id, variable_key)
    return OffsetPage[PlatformVariable](items=items, total=total, limit=limit, offset=offset)


@router.get("/{variable_key}", response_model=PlatformVariable)
async def get_variable(container: ContainerDep, variable_key: str) -> PlatformVariable:
    variable = await container.secrets_service.get(_current_company_id(), variable_key)
    if variable is None:
        raise HTTPException(status_code=404, detail="Variable not found")
    return variable


@router.delete("/{variable_key}")
async def delete_variable(container: ContainerDep, variable_key: str) -> dict[str, str]:
    deleted = await container.secrets_service.delete(_current_company_id(), variable_key)
    if not deleted:
        raise HTTPException(status_code=404, detail="Variable not found")
    return {"status": "deleted", "variable_key": variable_key}
