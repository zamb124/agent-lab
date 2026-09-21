"""REST-зеркало команд `secrets/variables/*`."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from apps.secrets.dependencies import ContainerDep
from apps.secrets.realtime.operations import (
    SecretsVariableDeletedResponse,
    SecretsVariableKeyPayload,
    SecretsVariablesListPayload,
    SecretsVariableVersionsPayload,
    op_variables_create,
    op_variables_item,
    op_variables_list,
    op_variables_remove,
    op_variables_resolve,
    op_variables_versions,
)
from core.context import require_context
from core.pagination import OffsetPage
from core.secrets.models import (
    VariableResolveRequest,
    VariableResolveResponse,
    VariableWriteRequest,
)
from core.variables.models import PlatformVariable

router = APIRouter(prefix="/variables", tags=["variables"])


@router.get("", response_model=OffsetPage[PlatformVariable])
async def list_variables(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[PlatformVariable]:
    return await op_variables_list(
        SecretsVariablesListPayload(limit=limit, offset=offset),
        user=require_context().user,
        container=container,
    )


@router.post("", response_model=PlatformVariable)
async def upsert_variable(
    container: ContainerDep, body: VariableWriteRequest
) -> PlatformVariable:
    return await op_variables_create(body, user=require_context().user, container=container)


@router.post("/resolve", response_model=VariableResolveResponse)
async def resolve_variables(
    container: ContainerDep, body: VariableResolveRequest
) -> VariableResolveResponse:
    return await op_variables_resolve(body, user=require_context().user, container=container)


@router.get("/{variable_key}/versions", response_model=OffsetPage[PlatformVariable])
async def list_variable_versions(
    container: ContainerDep,
    variable_key: str,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[PlatformVariable]:
    return await op_variables_versions(
        SecretsVariableVersionsPayload(variable_key=variable_key, limit=limit, offset=offset),
        user=require_context().user,
        container=container,
    )


@router.get("/{variable_key}", response_model=PlatformVariable)
async def get_variable(container: ContainerDep, variable_key: str) -> PlatformVariable:
    return await op_variables_item(
        SecretsVariableKeyPayload(variable_key=variable_key),
        user=require_context().user,
        container=container,
    )


@router.delete("/{variable_key}", response_model=SecretsVariableDeletedResponse)
async def delete_variable(
    container: ContainerDep, variable_key: str
) -> SecretsVariableDeletedResponse:
    return await op_variables_remove(
        SecretsVariableKeyPayload(variable_key=variable_key),
        user=require_context().user,
        container=container,
    )
