"""API для управления namespaces и их шаблонами в CRM."""

from typing import List
from fastapi import APIRouter, HTTPException

from core.logging import get_logger
from core.context import get_context
from apps.crm.dependencies import ContainerDep
from apps.crm.models.api import (
    NamespaceCreateRequest,
    NamespaceEditabilityResponse,
    NamespaceListResponse,
    NamespaceResponse,
    NamespaceTemplateCreateRequest,
    NamespaceTemplateDetailsResponse,
    NamespaceTemplateSchemaEnumSet,
    NamespaceTemplateSchemaFieldType,
    NamespaceTemplateSchemaOperator,
    NamespaceTemplateSchemaOptionsResponse,
    NamespaceTemplateResponse,
    NamespaceTemplateTypeResponse,
    NamespaceTemplateTypeUpsertRequest,
    NamespaceTemplateUpdateRequest,
    NamespaceUpdateRequest,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/namespaces", tags=["CRM Namespaces"])

SCHEMA_OPTIONS_RESPONSE = NamespaceTemplateSchemaOptionsResponse(
    field_types=[
        NamespaceTemplateSchemaFieldType(type_id="string", label="Строка"),
        NamespaceTemplateSchemaFieldType(type_id="text", label="Текст"),
        NamespaceTemplateSchemaFieldType(type_id="number", label="Число"),
        NamespaceTemplateSchemaFieldType(type_id="integer", label="Целое число"),
        NamespaceTemplateSchemaFieldType(type_id="boolean", label="Булево"),
        NamespaceTemplateSchemaFieldType(type_id="date", label="Дата"),
        NamespaceTemplateSchemaFieldType(type_id="datetime", label="Дата и время"),
        NamespaceTemplateSchemaFieldType(type_id="enum", label="Enum", supports_enum_values=True, supports_enum_set=True),
        NamespaceTemplateSchemaFieldType(type_id="array", label="Массив"),
        NamespaceTemplateSchemaFieldType(type_id="object", label="Объект"),
    ],
    enum_sets=[
        NamespaceTemplateSchemaEnumSet(enum_set_id="priority", label="Приоритет", values=["low", "medium", "high", "urgent"]),
        NamespaceTemplateSchemaEnumSet(enum_set_id="task_status", label="Статус задачи", values=["todo", "in_progress", "blocked", "done"]),
        NamespaceTemplateSchemaEnumSet(enum_set_id="confidence", label="Уверенность", values=["low", "medium", "high"]),
        NamespaceTemplateSchemaEnumSet(enum_set_id="yes_no", label="Да/Нет", values=["yes", "no"]),
    ],
    operators=[
        NamespaceTemplateSchemaOperator(operator_id="eq", label="Равно"),
        NamespaceTemplateSchemaOperator(operator_id="neq", label="Не равно"),
        NamespaceTemplateSchemaOperator(operator_id="in", label="В списке"),
        NamespaceTemplateSchemaOperator(operator_id="contains", label="Содержит"),
    ],
    defaults={"field_type": "string"},
    validation_limits={"max_fields_per_section": 128, "max_enum_values": 64},
)


def _normalize_allowed_type_ids(raw_value: list[str]) -> list[str]:
    normalized: list[str] = []
    for raw_item in raw_value:
        if not isinstance(raw_item, str):
            raise HTTPException(status_code=422, detail="allowed_type_ids must contain only strings")
        value = raw_item.strip()
        if not value:
            raise HTTPException(status_code=422, detail="allowed_type_ids must not contain empty values")
        if value not in normalized:
            normalized.append(value)
    return normalized


@router.get("", response_model=NamespaceListResponse)
async def list_namespaces(
    container: ContainerDep,
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
                is_default=ns.is_default,
                crm_settings=ns.crm_settings,
            )
            for ns in namespaces
        ],
        company_id=company_id
    )


@router.get("/templates", response_model=List[NamespaceTemplateResponse])
async def list_namespace_templates(
    container: ContainerDep,
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


@router.get("/templates/schema/options", response_model=NamespaceTemplateSchemaOptionsResponse)
async def get_template_schema_options(
    container: ContainerDep,
) -> NamespaceTemplateSchemaOptionsResponse:
    """Динамические опции конструктора полей для UI."""
    _ = container
    return SCHEMA_OPTIONS_RESPONSE


@router.post("/templates", response_model=NamespaceTemplateResponse, status_code=201)
async def create_namespace_template(
    request: NamespaceTemplateCreateRequest,
    container: ContainerDep,
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
    container: ContainerDep,
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
                is_context_anchor=item.is_context_anchor,
            )
            for item in template_types
        ],
    )


@router.put("/templates/{template_id}", response_model=NamespaceTemplateResponse)
async def update_namespace_template(
    template_id: str,
    request: NamespaceTemplateUpdateRequest,
    container: ContainerDep,
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
    container: ContainerDep,
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
    container: ContainerDep,
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
        is_context_anchor=request.is_context_anchor,
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
        is_context_anchor=item.is_context_anchor,
    )


@router.delete("/templates/{template_id}/types/{type_id}", status_code=204)
async def delete_template_type(
    template_id: str,
    type_id: str,
    container: ContainerDep,
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
    container: ContainerDep,
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
        is_default=namespace.is_default,
        crm_settings=namespace.crm_settings,
    )


@router.get("/{namespace_name}/editability", response_model=NamespaceEditabilityResponse)
async def get_namespace_editability(
    namespace_name: str,
    container: ContainerDep,
) -> NamespaceEditabilityResponse:
    normalized_namespace_name = namespace_name.strip()
    if not normalized_namespace_name:
        raise HTTPException(status_code=422, detail="Namespace name is required")

    existing_namespace = await container.namespace_repository.get(normalized_namespace_name)
    if existing_namespace is None:
        raise HTTPException(status_code=404, detail=f"Namespace {normalized_namespace_name} not found")

    service = container.namespace_template_service
    payload = await service.get_namespace_editability(normalized_namespace_name)
    return NamespaceEditabilityResponse(**payload)


@router.put("/{namespace_name}", response_model=NamespaceResponse)
async def update_namespace(
    namespace_name: str,
    request: NamespaceUpdateRequest,
    container: ContainerDep,
) -> NamespaceResponse:
    normalized_namespace_name = namespace_name.strip()
    if not normalized_namespace_name:
        raise HTTPException(status_code=422, detail="Namespace name is required")

    existing_namespace = await container.namespace_repository.get(normalized_namespace_name)
    if existing_namespace is None:
        raise HTTPException(status_code=404, detail=f"Namespace {normalized_namespace_name} not found")

    allowed_type_ids = None
    if request.allowed_type_ids is not None:
        allowed_type_ids = _normalize_allowed_type_ids(request.allowed_type_ids)
        all_types = await container.entity_type_repository.get_all_for_company()
        all_type_ids = {item.type_id for item in all_types}
        unknown_type_ids = [item for item in allowed_type_ids if item not in all_type_ids]
        if unknown_type_ids:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown type_id values: {', '.join(unknown_type_ids)}",
            )

    editability = await container.namespace_template_service.get_namespace_editability(normalized_namespace_name)
    if allowed_type_ids is not None:
        locked_type_ids = set(editability["locked_type_ids"])
        requested_set = set(allowed_type_ids)
        missing_locked = locked_type_ids - requested_set
        if missing_locked:
            raise HTTPException(
                status_code=422,
                detail=f"Нельзя убрать типы с существующими сущностями: {', '.join(sorted(missing_locked))}",
            )

    service = container.namespace_template_service
    updated_namespace = await service.update_existing_namespace(
        namespace_name=normalized_namespace_name,
        description_is_set="description" in request.model_fields_set,
        description=request.description,
        allowed_type_ids=allowed_type_ids,
    )

    if request.crm_settings is not None:
        ns = await container.namespace_repository.get(normalized_namespace_name)
        if ns is None:
            raise HTTPException(status_code=404, detail=f"Namespace {normalized_namespace_name} not found")
        ns.crm_settings = request.crm_settings
        await container.namespace_repository.set(ns)
        updated_namespace = ns

    return NamespaceResponse(
        name=updated_namespace.name,
        company_id=updated_namespace.company_id,
        description=updated_namespace.description,
        is_default=updated_namespace.is_default,
        crm_settings=updated_namespace.crm_settings,
    )
