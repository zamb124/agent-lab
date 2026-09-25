"""Namespaces и шаблоны: тонкая REST-обвязка тех же `op_*`."""

from typing import Annotated

from fastapi import APIRouter, Query, Response

from apps.crm.di import Di
from apps.crm.models.api import (
    NamespaceCreateRequest,
    NamespaceEditabilityResponse,
    NamespaceResponse,
    NamespaceTemplateCreateRequest,
    NamespaceTemplateDetailsResponse,
    NamespaceTemplateResponse,
    NamespaceTemplateSchemaOptionsResponse,
    NamespaceTemplateTypeResponse,
    NamespaceTemplateTypeUpsertRequest,
    NamespaceTemplateUpdateRequest,
    NamespaceUpdateRequest,
)
from apps.crm.realtime.operations import (
    CrmNamespaceNamePayload,
    CrmNamespaceUpdatePayload,
    CrmOffsetPagePayload,
    CrmTemplateIdPayload,
    CrmTemplateTypeRemovePayload,
    CrmTemplateTypeUpsertPayload,
    CrmTemplateUpdatePayload,
    op_namespaces_create,
    op_namespaces_editability,
    op_namespaces_list,
    op_namespaces_update,
    op_templates_create,
    op_templates_item,
    op_templates_list,
    op_templates_remove,
    op_templates_schema_options,
    op_templates_type_remove,
    op_templates_type_upsert,
    op_templates_update,
)
from core.context import require_context
from core.pagination import OffsetPage
from core.websocket import EmptyPayload

router = APIRouter(prefix="/namespaces", tags=["CRM Namespaces"])


@router.get("", response_model=OffsetPage[NamespaceResponse])
async def list_namespaces(
    di: Di,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[NamespaceResponse]:
    return await op_namespaces_list(
        CrmOffsetPagePayload(limit=limit, offset=offset),
        user=require_context().user,
        di=di,
    )


@router.get("/templates", response_model=OffsetPage[NamespaceTemplateResponse])
async def list_namespace_templates(
    di: Di,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[NamespaceTemplateResponse]:
    return await op_templates_list(
        CrmOffsetPagePayload(limit=limit, offset=offset),
        user=require_context().user,
        di=di,
    )


@router.get("/templates/schema/options", response_model=NamespaceTemplateSchemaOptionsResponse)
async def get_template_schema_options(
    di: Di,
) -> NamespaceTemplateSchemaOptionsResponse:
    return await op_templates_schema_options(
        EmptyPayload(),
        user=require_context().user,
        di=di,
    )


@router.post("/templates", response_model=NamespaceTemplateResponse, status_code=201)
async def create_namespace_template(
    body: NamespaceTemplateCreateRequest,
    di: Di,
) -> NamespaceTemplateResponse:
    return await op_templates_create(
        body,
        user=require_context().user,
        di=di,
    )


@router.get("/templates/{template_id}", response_model=NamespaceTemplateDetailsResponse)
async def get_namespace_template(
    template_id: str,
    di: Di,
) -> NamespaceTemplateDetailsResponse:
    return await op_templates_item(
        CrmTemplateIdPayload(template_id=template_id),
        user=require_context().user,
        di=di,
    )


@router.put("/templates/{template_id}", response_model=NamespaceTemplateResponse)
async def update_namespace_template(
    template_id: str,
    body: NamespaceTemplateUpdateRequest,
    di: Di,
) -> NamespaceTemplateResponse:
    return await op_templates_update(
        CrmTemplateUpdatePayload(
            template_id=template_id,
            name=body.name,
            description=body.description,
            icon=body.icon,
            crm_settings=body.crm_settings,
        ),
        user=require_context().user,
        di=di,
    )


@router.delete("/templates/{template_id}", status_code=204)
async def delete_namespace_template(
    template_id: str,
    di: Di,
) -> Response:
    await op_templates_remove(
        CrmTemplateIdPayload(template_id=template_id),
        user=require_context().user,
        di=di,
    )
    return Response(status_code=204)


@router.post(
    "/templates/{template_id}/types",
    response_model=NamespaceTemplateTypeResponse,
    status_code=201,
)
async def upsert_template_type(
    template_id: str,
    body: NamespaceTemplateTypeUpsertRequest,
    di: Di,
) -> NamespaceTemplateTypeResponse:
    return await op_templates_type_upsert(
        CrmTemplateTypeUpsertPayload(
            template_id=template_id,
            type_id=body.type_id,
            parent_type_id=body.parent_type_id,
            name=body.name,
            description=body.description,
            prompt=body.prompt,
            required_fields=body.required_fields,
            optional_fields=body.optional_fields,
            icon=body.icon,
            color=body.color,
            is_event=body.is_event,
            check_duplicates=body.check_duplicates,
            weight_coefficient=body.weight_coefficient,
            namespace_ids=body.namespace_ids,
            is_context_anchor=body.is_context_anchor,
            is_voice_target=body.is_voice_target,
        ),
        user=require_context().user,
        di=di,
    )


@router.delete("/templates/{template_id}/types/{type_id}", status_code=204)
async def delete_template_type(
    template_id: str,
    type_id: str,
    di: Di,
) -> Response:
    await op_templates_type_remove(
        CrmTemplateTypeRemovePayload(template_id=template_id, type_id=type_id),
        user=require_context().user,
        di=di,
    )
    return Response(status_code=204)


@router.post("", status_code=201, response_model=NamespaceResponse)
async def create_namespace(
    body: NamespaceCreateRequest,
    di: Di,
) -> NamespaceResponse:
    return await op_namespaces_create(
        body,
        user=require_context().user,
        di=di,
    )


@router.get("/{namespace_name}/editability", response_model=NamespaceEditabilityResponse)
async def get_namespace_editability(
    namespace_name: str,
    di: Di,
) -> NamespaceEditabilityResponse:
    return await op_namespaces_editability(
        CrmNamespaceNamePayload(name=namespace_name),
        user=require_context().user,
        di=di,
    )


@router.put("/{namespace_name}", response_model=NamespaceResponse)
async def update_namespace(
    namespace_name: str,
    body: NamespaceUpdateRequest,
    di: Di,
) -> NamespaceResponse:
    payload = CrmNamespaceUpdatePayload(name=namespace_name)
    if "description" in body.model_fields_set:
        payload.description = body.description
    if "allowed_type_ids" in body.model_fields_set:
        payload.allowed_type_ids = body.allowed_type_ids
    if "crm_settings" in body.model_fields_set:
        payload.crm_settings = body.crm_settings
    return await op_namespaces_update(
        payload,
        user=require_context().user,
        di=di,
    )
