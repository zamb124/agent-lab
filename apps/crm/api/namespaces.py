"""API для управления namespaces и их шаблонами в CRM."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException

from core.logging import get_logger
from core.context import get_context
from apps.crm.container import CRMContainer
from apps.crm.dependencies import get_container_dep
from apps.crm.models.api import (
    NamespaceCreateRequest,
    NamespaceListResponse,
    NamespaceResponse,
    NamespaceTemplateCreateRequest,
    NamespaceTemplateDetailsResponse,
    NamespaceTemplateResponse,
    NamespaceTemplateTypeResponse,
    NamespaceTemplateTypeUpsertRequest,
    NamespaceTemplateUpdateRequest,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/namespaces", tags=["CRM Namespaces"])


@router.get("", response_model=NamespaceListResponse)
async def list_namespaces(
    container: CRMContainer = Depends(get_container_dep)
) -> NamespaceListResponse:
    """
    Список всех namespaces текущей компании.
    Если пусто - автоматически создается default.
    """
    context = get_context()
    company_id = context.active_company.company_id
    
    namespace_repo = container.namespace_repository
    namespaces = await namespace_repo.list_all()
    
    return NamespaceListResponse(
        namespaces=[
            NamespaceResponse(
                name=ns.name,
                company_id=ns.company_id,
                description=ns.description,
                is_default=ns.is_default
            )
            for ns in namespaces
        ],
        company_id=company_id
    )


@router.get("/templates", response_model=List[NamespaceTemplateResponse])
async def list_namespace_templates(
    container: CRMContainer = Depends(get_container_dep)
) -> List[NamespaceTemplateResponse]:
    """Список шаблонов namespace из БД."""
    template_repo = container.namespace_template_repository
    templates = await template_repo.list_for_company()
    responses: list[NamespaceTemplateResponse] = []
    for template in templates:
        template_types = await template_repo.list_types(template.template_key)
        responses.append(
            NamespaceTemplateResponse(
                template_id=template.template_id,
                name=template.name,
                description=template.description,
                icon=template.icon,
                is_system=template.is_system,
                entity_type_ids=[item.type_id for item in template_types],
            )
        )
    return responses


@router.post("/templates", response_model=NamespaceTemplateResponse, status_code=201)
async def create_namespace_template(
    request: NamespaceTemplateCreateRequest,
    container: CRMContainer = Depends(get_container_dep),
) -> NamespaceTemplateResponse:
    template_repo = container.namespace_template_repository
    existing = await template_repo.get_by_template_id(request.template_id)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Template {request.template_id} already exists")
    created = await template_repo.create_template(
        template_id=request.template_id,
        name=request.name,
        description=request.description,
        icon=request.icon,
        is_system=False,
    )
    return NamespaceTemplateResponse(
        template_id=created.template_id,
        name=created.name,
        description=created.description,
        icon=created.icon,
        is_system=created.is_system,
        entity_type_ids=[],
    )


@router.get("/templates/{template_id}", response_model=NamespaceTemplateDetailsResponse)
async def get_namespace_template(
    template_id: str,
    container: CRMContainer = Depends(get_container_dep),
) -> NamespaceTemplateDetailsResponse:
    template_repo = container.namespace_template_repository
    template = await template_repo.get_by_template_id(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")
    template_types = await template_repo.list_types(template.template_key)
    return NamespaceTemplateDetailsResponse(
        template_id=template.template_id,
        name=template.name,
        description=template.description,
        icon=template.icon,
        is_system=template.is_system,
        entity_type_ids=[item.type_id for item in template_types],
        types=[
            NamespaceTemplateTypeResponse(
                type_id=item.type_id,
                parent_type_id=item.parent_type_id,
                name=item.name,
                description=item.description,
                prompt=item.prompt,
                required_fields=item.required_fields,
                optional_fields=item.optional_fields,
                icon=item.icon,
                color=item.color,
                is_event=item.is_event,
                check_duplicates=item.check_duplicates,
                weight_coefficient=item.weight_coefficient,
                namespace_ids=item.namespace_ids,
            )
            for item in template_types
        ],
    )


@router.put("/templates/{template_id}", response_model=NamespaceTemplateResponse)
async def update_namespace_template(
    template_id: str,
    request: NamespaceTemplateUpdateRequest,
    container: CRMContainer = Depends(get_container_dep),
) -> NamespaceTemplateResponse:
    template_repo = container.namespace_template_repository
    template = await template_repo.get_by_template_id(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")
    if request.name is not None:
        template.name = request.name
    if request.description is not None:
        template.description = request.description
    if request.icon is not None:
        template.icon = request.icon
    updated = await template_repo.update(template)
    template_types = await template_repo.list_types(updated.template_key)
    return NamespaceTemplateResponse(
        template_id=updated.template_id,
        name=updated.name,
        description=updated.description,
        icon=updated.icon,
        is_system=updated.is_system,
        entity_type_ids=[item.type_id for item in template_types],
    )


@router.delete("/templates/{template_id}", status_code=204)
async def delete_namespace_template(
    template_id: str,
    container: CRMContainer = Depends(get_container_dep),
) -> None:
    template_repo = container.namespace_template_repository
    template = await template_repo.get_by_template_id(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")
    if template.is_system:
        raise HTTPException(status_code=422, detail="System template cannot be deleted")
    await template_repo.delete_template_with_types(template.template_key)


@router.post("/templates/{template_id}/types", response_model=NamespaceTemplateTypeResponse, status_code=201)
async def upsert_template_type(
    template_id: str,
    request: NamespaceTemplateTypeUpsertRequest,
    container: CRMContainer = Depends(get_container_dep),
) -> NamespaceTemplateTypeResponse:
    template_repo = container.namespace_template_repository
    template = await template_repo.get_by_template_id(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")
    item = await template_repo.upsert_type(
        template_key=template.template_key,
        type_id=request.type_id,
        parent_type_id=request.parent_type_id,
        name=request.name,
        description=request.description,
        prompt=request.prompt,
        required_fields=request.required_fields,
        optional_fields=request.optional_fields,
        icon=request.icon,
        color=request.color,
        is_event=request.is_event,
        check_duplicates=request.check_duplicates,
        weight_coefficient=request.weight_coefficient,
        namespace_ids=request.namespace_ids,
    )
    return NamespaceTemplateTypeResponse(
        type_id=item.type_id,
        parent_type_id=item.parent_type_id,
        name=item.name,
        description=item.description,
        prompt=item.prompt,
        required_fields=item.required_fields,
        optional_fields=item.optional_fields,
        icon=item.icon,
        color=item.color,
        is_event=item.is_event,
        check_duplicates=item.check_duplicates,
        weight_coefficient=item.weight_coefficient,
        namespace_ids=item.namespace_ids,
    )


@router.delete("/templates/{template_id}/types/{type_id}", status_code=204)
async def delete_template_type(
    template_id: str,
    type_id: str,
    container: CRMContainer = Depends(get_container_dep),
) -> None:
    template_repo = container.namespace_template_repository
    template = await template_repo.get_by_template_id(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")
    deleted = await template_repo.delete_type(template.template_key, type_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Template type {type_id} not found")


@router.post("", status_code=201, response_model=NamespaceResponse)
async def create_namespace(
    request: NamespaceCreateRequest,
    container: CRMContainer = Depends(get_container_dep)
) -> NamespaceResponse:
    """Создает namespace и применяет DB-шаблон."""
    try:
        namespace = await container.namespace_template_service.create_namespace_from_template(
            namespace_name=request.name,
            namespace_description=request.description,
            template_id=request.template_id,
        )
    except ValueError as error:
        detail = str(error)
        status_code = 404 if "not found" in detail.lower() else 422
        if "already exists" in detail.lower():
            status_code = 409
        raise HTTPException(status_code=status_code, detail=detail) from error

    logger.info(f"Создан namespace {request.name}")
    return NamespaceResponse(
        name=namespace.name,
        company_id=namespace.company_id,
        description=namespace.description,
        is_default=namespace.is_default
    )
