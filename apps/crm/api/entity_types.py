"""Типы сущностей: тонкая REST-обвязка тех же `op_*`."""

from typing import Annotated

from fastapi import APIRouter, Query

from apps.crm.dependencies import ContainerDep
from apps.crm.models.api import EntityTypeCreate, EntityTypeResponse, EntityTypeUpdate
from apps.crm.realtime.operations import (
    CrmEntityTypeKeyPayload,
    CrmEntityTypePublicFieldsPayload,
    CrmEntityTypesListPayload,
    CrmEntityTypeUpdatePayload,
    op_entity_types_create,
    op_entity_types_item,
    op_entity_types_list,
    op_entity_types_public_fields,
    op_entity_types_update,
)
from core.context import require_context
from core.pagination import OffsetPage
from core.websocket import WsCommandError

router = APIRouter(prefix="/entity-types", tags=["EntityTypes"])


@router.get("", response_model=OffsetPage[EntityTypeResponse])
async def list_entity_types(
    payload: Annotated[CrmEntityTypesListPayload, Query()],
    container: ContainerDep,
) -> OffsetPage[EntityTypeResponse]:
    return await op_entity_types_list(
        payload,
        user=require_context().user,
        container=container,
    )


@router.get("/{type_id}", response_model=EntityTypeResponse)
async def get_entity_type(
    type_id: str,
    container: ContainerDep,
    namespace: Annotated[str, Query(description="Пространство строки типа")],
) -> EntityTypeResponse:
    return await op_entity_types_item(
        CrmEntityTypeKeyPayload(type_id=type_id, namespace=namespace),
        user=require_context().user,
        container=container,
    )


@router.post("", response_model=EntityTypeResponse)
async def create_entity_type(
    body: EntityTypeCreate,
    container: ContainerDep,
) -> EntityTypeResponse:
    return await op_entity_types_create(
        body,
        user=require_context().user,
        container=container,
    )


@router.put("/{type_id}", response_model=EntityTypeResponse)
async def update_entity_type(
    type_id: str,
    body: EntityTypeUpdate,
    container: ContainerDep,
    namespace: Annotated[str, Query(description="Пространство строки типа")],
) -> EntityTypeResponse:
    return await op_entity_types_update(
        CrmEntityTypeUpdatePayload.model_validate(
            {"type_id": type_id, "namespace": namespace, **body.model_dump()}
        ),
        user=require_context().user,
        container=container,
    )


@router.put("/{type_id}/public-fields", response_model=EntityTypeResponse)
async def update_public_fields(
    type_id: str,
    payload: CrmEntityTypePublicFieldsPayload,
    container: ContainerDep,
) -> EntityTypeResponse:
    if payload.type_id != type_id:
        raise WsCommandError(
            "ws_invalid_payload",
            "type_id in path must match payload.type_id",
                  error_code='ws_invalid_payload',
              )
    return await op_entity_types_public_fields(
        payload,
        user=require_context().user,
        container=container,
    )
