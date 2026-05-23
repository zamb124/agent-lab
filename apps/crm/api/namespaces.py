"""API для управления namespaces и их шаблонами в CRM."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from apps.crm.dependencies import ContainerDep
from apps.crm.models.api import (
    NamespaceCreateRequest,
    NamespaceEditabilityResponse,
    NamespaceIntegrationBadge,
    NamespaceResponse,
    NamespaceTemplateCreateRequest,
    NamespaceTemplateDetailsResponse,
    NamespaceTemplateResponse,
    NamespaceTemplateSchemaEnumSet,
    NamespaceTemplateSchemaFieldType,
    NamespaceTemplateSchemaOperator,
    NamespaceTemplateSchemaOptionsResponse,
    NamespaceTemplateTypeResponse,
    NamespaceTemplateTypeUpsertRequest,
    NamespaceTemplateUpdateRequest,
    NamespaceUpdateRequest,
    TaskBoardEditorBoardResponse,
    TaskBoardEditorStateResponse,
    TaskBoardStagesApiResponse,
)
from apps.crm.scheduled_task_constants import CRM_GENERATE_NAMESPACE_SUGGESTS_TASK_NAME
from apps.crm.services.task_board_presets import (
    build_task_board_editor_boards,
    resolve_task_board_stages,
    task_board_key,
)
from apps.crm.system_templates import REQUIRED_NAMESPACE_TEMPLATE_TYPE_IDS
from core.context import get_context
from core.logging import get_logger
from core.models.identity_models import Namespace, NamespaceCRMSettings
from core.pagination import OffsetPage
from core.scheduler.models import PlatformScheduleCreateRequest, PlatformScheduleType

logger = get_logger(__name__)

router = APIRouter(prefix="/namespaces", tags=["CRM Namespaces"])


async def _namespace_integration_badges(
    container: ContainerDep,
    *,
    namespace_name: str,
    company_id: str,
    user_id: str,
    crm_settings: NamespaceCRMSettings | None,
) -> list[NamespaceIntegrationBadge]:
    manifest = await container.integration_registry.build_manifest(
        namespace_name=namespace_name,
        company_id=company_id,
        user_id=user_id,
        crm_settings=crm_settings,
    )
    return [
        NamespaceIntegrationBadge(
            provider_id=str(row["provider_id"]),
            connected=bool(row.get("connected")),
        )
        for row in manifest
    ]


async def _namespace_response(
    container: ContainerDep,
    ns: Namespace,
) -> NamespaceResponse:
    ctx = get_context()
    badges: list[NamespaceIntegrationBadge] = []
    if ctx is not None and ctx.active_company is not None:
        badges = await _namespace_integration_badges(
            container,
            namespace_name=ns.name,
            company_id=ns.company_id,
            user_id=ctx.user.user_id,
            crm_settings=ns.crm_settings,
        )
    return NamespaceResponse(
        name=ns.name,
        company_id=ns.company_id,
        description=ns.description,
        is_default=ns.is_default,
        crm_settings=ns.crm_settings,
        integration_badges=badges,
    )


SCHEMA_OPTIONS_RESPONSE = NamespaceTemplateSchemaOptionsResponse(
    field_types=[
        NamespaceTemplateSchemaFieldType(type_id="string", label="Строка"),
        NamespaceTemplateSchemaFieldType(type_id="text", label="Текст"),
        NamespaceTemplateSchemaFieldType(type_id="number", label="Число"),
        NamespaceTemplateSchemaFieldType(type_id="integer", label="Целое число"),
        NamespaceTemplateSchemaFieldType(type_id="boolean", label="Булево"),
        NamespaceTemplateSchemaFieldType(type_id="date", label="Дата"),
        NamespaceTemplateSchemaFieldType(type_id="datetime", label="Дата и время"),
        NamespaceTemplateSchemaFieldType(
            type_id="enum", label="Enum", supports_enum_values=True, supports_enum_set=True
        ),
        NamespaceTemplateSchemaFieldType(type_id="array", label="Массив"),
        NamespaceTemplateSchemaFieldType(type_id="object", label="Объект"),
        NamespaceTemplateSchemaFieldType(type_id="external_refs", label="Внешние ссылки"),
    ],
    enum_sets=[
        NamespaceTemplateSchemaEnumSet(
            enum_set_id="priority", label="Приоритет", values=["low", "medium", "high", "urgent"]
        ),
        NamespaceTemplateSchemaEnumSet(
            enum_set_id="task_status",
            label="Статус задачи",
            values=["todo", "in_progress", "blocked", "done"],
        ),
        NamespaceTemplateSchemaEnumSet(
            enum_set_id="confidence", label="Уверенность", values=["low", "medium", "high"]
        ),
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
        value = raw_item.strip()
        if not value:
            raise HTTPException(
                status_code=422, detail="allowed_type_ids must not contain empty values"
            )
        if value not in normalized:
            normalized.append(value)
    return normalized


async def _collect_company_type_ids(container: ContainerDep) -> set[str]:
    rows = await container.entity_type_repository.load_all_entity_types_for_company()
    return {item.type_id for item in rows}


@router.get("", response_model=OffsetPage[NamespaceResponse])
async def list_namespaces(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[NamespaceResponse]:
    """Список всех namespaces текущей компании."""
    namespace_repo = container.namespace_repository
    namespaces, total = await asyncio.gather(
        namespace_repo.list(limit=limit, offset=offset),
        namespace_repo.count_all(),
    )
    responses = await asyncio.gather(
        *[_namespace_response(container, ns) for ns in namespaces],
    )
    return OffsetPage[NamespaceResponse](
        items=list(responses),
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/templates", response_model=OffsetPage[NamespaceTemplateResponse])
async def list_namespace_templates(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[NamespaceTemplateResponse]:
    """Список шаблонов namespace из БД."""
    template_repo = container.namespace_template_repository
    templates, total = await asyncio.gather(
        template_repo.list_for_company(limit=limit, offset=offset),
        template_repo.count_all(),
    )
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
    return OffsetPage[NamespaceTemplateResponse](
        items=responses,
        total=total,
        limit=limit,
        offset=offset,
    )


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
        raise HTTPException(
            status_code=409, detail=f"Template {request.template_id} already exists"
        )
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


@router.get(
    "/templates/{template_id}/task-board-editor-state",
    response_model=TaskBoardEditorStateResponse,
)
async def get_template_task_board_editor_state(
    template_id: str,
    container: ContainerDep,
) -> TaskBoardEditorStateResponse:
    template_repo = container.namespace_template_repository
    template = await template_repo.get_by_template_id(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")
    template_types = await template_repo.list_types(template.template_key)
    allowed = [item.type_id for item in template_types if item.type_id]
    crm = NamespaceCRMSettings()
    raw_crm = template.crm_settings
    if raw_crm is not None and len(raw_crm) > 0:
        crm = NamespaceCRMSettings.model_validate(raw_crm)
    raw_boards = build_task_board_editor_boards(
        allowed_type_ids=allowed,
        entity_types=template_types,
        crm=crm,
    )
    boards = [TaskBoardEditorBoardResponse.model_validate(row) for row in raw_boards]
    return TaskBoardEditorStateResponse(boards=boards)


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
    crm_detail: NamespaceCRMSettings | None = None
    raw_crm = template.crm_settings
    if raw_crm is not None and len(raw_crm) > 0:
        crm_detail = NamespaceCRMSettings.model_validate(raw_crm)
    return NamespaceTemplateDetailsResponse(
        template_id=template.template_id,
        name=template.name,
        description=template.description,
        icon=template.icon,
        is_system=template.is_system,
        entity_type_ids=[item.type_id for item in template_types],
        crm_settings=crm_detail,
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
                is_voice_target=item.is_voice_target,
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
    if request.crm_settings is not None:
        prev = NamespaceCRMSettings()
        raw_existing = template.crm_settings
        if raw_existing is not None and len(raw_existing) > 0:
            prev = NamespaceCRMSettings.model_validate(raw_existing)
        incoming = request.crm_settings
        data = prev.model_dump()
        for field_name in incoming.model_fields_set:
            data[field_name] = getattr(incoming, field_name)
        merged = NamespaceCRMSettings.model_validate(data)
        template.crm_settings = merged.model_dump(mode="json")
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
    _ = await template_repo.delete_template_with_types(template.template_key)


@router.post(
    "/templates/{template_id}/types", response_model=NamespaceTemplateTypeResponse, status_code=201
)
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
        is_voice_target=request.is_voice_target,
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
        is_voice_target=item.is_voice_target,
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
    current_ids = {t.type_id for t in await template_repo.list_types(template.template_key)}
    after_remove = current_ids - {type_id}
    if not REQUIRED_NAMESPACE_TEMPLATE_TYPE_IDS <= after_remove:
        raise HTTPException(
            status_code=422,
            detail="Нельзя удалить тип: у шаблона пространства всегда должны оставаться note и task.",
        )
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
    return await _namespace_response(container, namespace)


@router.get(
    "/{namespace_name}/task-board-stages",
    response_model=TaskBoardStagesApiResponse,
)
async def get_namespace_task_board_stages(
    namespace_name: str,
    container: ContainerDep,
    entity_subtype: Annotated[str | None, Query()] = None,
) -> TaskBoardStagesApiResponse:
    normalized_namespace_name = namespace_name.strip()
    if not normalized_namespace_name:
        raise HTTPException(status_code=422, detail="Namespace name is required")

    existing_namespace = await container.namespace_repository.get(normalized_namespace_name)
    if existing_namespace is None:
        raise HTTPException(
            status_code=404, detail=f"Namespace {normalized_namespace_name} not found"
        )

    crm = (
        existing_namespace.crm_settings
        if existing_namespace.crm_settings is not None
        else NamespaceCRMSettings()
    )
    sub = entity_subtype.strip() if isinstance(entity_subtype, str) else None
    if sub == "":
        sub = None
    key = task_board_key("task", sub)
    stages = resolve_task_board_stages(crm, key)
    return TaskBoardStagesApiResponse(board_key=key, stages=stages)


@router.get(
    "/{namespace_name}/task-board-editor-state",
    response_model=TaskBoardEditorStateResponse,
)
async def get_namespace_task_board_editor_state(
    namespace_name: str,
    container: ContainerDep,
) -> TaskBoardEditorStateResponse:
    normalized_namespace_name = namespace_name.strip()
    if not normalized_namespace_name:
        raise HTTPException(status_code=422, detail="Namespace name is required")

    existing_namespace = await container.namespace_repository.get(normalized_namespace_name)
    if existing_namespace is None:
        raise HTTPException(
            status_code=404, detail=f"Namespace {normalized_namespace_name} not found"
        )

    service = container.namespace_template_service
    payload = await service.get_namespace_editability(normalized_namespace_name)
    allowed = payload["current_allowed_type_ids"]
    types = await container.entity_type_repository.get_all_for_company(
        namespace=normalized_namespace_name,
        limit=500,
        offset=0,
    )
    crm = (
        existing_namespace.crm_settings
        if existing_namespace.crm_settings is not None
        else NamespaceCRMSettings()
    )
    raw_boards = build_task_board_editor_boards(
        allowed_type_ids=allowed,
        entity_types=types,
        crm=crm,
    )
    boards = [TaskBoardEditorBoardResponse.model_validate(row) for row in raw_boards]
    return TaskBoardEditorStateResponse(boards=boards)


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
        raise HTTPException(
            status_code=404, detail=f"Namespace {normalized_namespace_name} not found"
        )

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
        raise HTTPException(
            status_code=404, detail=f"Namespace {normalized_namespace_name} not found"
        )

    allowed_type_ids = None
    if request.allowed_type_ids is not None:
        allowed_type_ids = _normalize_allowed_type_ids(request.allowed_type_ids)
        all_type_ids = await _collect_company_type_ids(container)
        unknown_type_ids = [item for item in allowed_type_ids if item not in all_type_ids]
        if unknown_type_ids:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown type_id values: {', '.join(unknown_type_ids)}",
            )

    editability = await container.namespace_template_service.get_namespace_editability(
        normalized_namespace_name
    )
    if allowed_type_ids is not None:
        locked_type_ids = set(editability["locked_type_ids"])
        expanded = await container.namespace_template_service.expanded_allowed_type_ids_for_namespace_update(
            allowed_type_ids,
        )
        missing_locked = locked_type_ids - expanded
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
            raise HTTPException(
                status_code=404, detail=f"Namespace {normalized_namespace_name} not found"
            )
        prev = ns.crm_settings or NamespaceCRMSettings()
        incoming = request.crm_settings
        data = prev.model_dump()
        for field_name in incoming.model_fields_set:
            data[field_name] = getattr(incoming, field_name)
        new_settings = NamespaceCRMSettings.model_validate(data)

        if "suggests" in incoming.model_fields_set:
            if prev.suggests.schedule_task_id:
                _ = await container.scheduler_client.cancel_schedule(prev.suggests.schedule_task_id)
            new_settings.suggests.schedule_task_id = None

            if new_settings.suggests.enabled:
                req = PlatformScheduleCreateRequest(
                    target_service="crm",
                    task_name=CRM_GENERATE_NAMESPACE_SUGGESTS_TASK_NAME,
                    queue_name="crm",
                    schedule_type=PlatformScheduleType.CRON,
                    cron=new_settings.suggests.cron,
                    payload={"company_id": ns.company_id, "namespace": normalized_namespace_name},
                )
                created = await container.scheduler_client.create_schedule(req)
                new_settings.suggests.schedule_task_id = created.schedule_task_id

        ns.crm_settings = new_settings
        _ = await container.namespace_repository.set(ns)
        updated_namespace = ns

    return await _namespace_response(container, updated_namespace)
