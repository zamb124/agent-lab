"""Бизнес-функции CRM: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Literal, Never

from oxyde.exceptions import UniqueViolationError
from pydantic import Field

from apps.crm.color_palette import assign_color_from_palette
from apps.crm.constants_graph import NOTE_ROOT_ENTITY_TYPE_ID
from apps.crm.di import Di
from apps.crm.entity_type_list_filter import resolve_list_entity_query_pair
from apps.crm.integrations.protocol import NamespaceIntegrationConnector
from apps.crm.models.access_request import AccessRequest
from apps.crm.models.access_request_models import (
    AccessRequestCreate,
    AccessRequestResponse,
    AccessRequestStatus,
    AccessRequestUpdate,
)
from apps.crm.models.api import (
    ActivityTaskCreateRequest,
    ActivityTaskResponse,
    AIAnalysisDraftPatchRequest,
    AIAnalysisDraftStored,
    AttachmentAttachResponse,
    AutoNoteAiAnalyzeUpdateRequest,
    BulkCardsRequest,
    BulkCreateRequest,
    BulkCreateResponse,
    BulkDeleteRequest,
    BulkDeleteResponse,
    BulkErrorItem,
    BulkUpdateRequest,
    BulkUpdateResponse,
    DailySummaryRequest,
    EntityAttachment,
    EntityCreate,
    EntityMergeRequest,
    EntityMergeResponse,
    EntityResponse,
    EntitySearchQueryRequest,
    EntityTimelineBoundsResponse,
    EntityTypeCreate,
    EntityTypeResponse,
    EntityTypeUpdate,
    EntityUpdate,
    IntegrationAuthorizeResponse,
    IntegrationAutoSyncUpdateRequest,
    IntegrationManifestItem,
    IntegrationSyncStats,
    LaraNamespaceSummaryResponse,
    NamespaceCreateRequest,
    NamespaceEditabilityResponse,
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
    NoteAnalysisDraftRepairQueuedResponse,
    NoteMarkdownFormatQueuedResponse,
    NoteProcessingConfig,
    PeriodSummaryRequest,
    RelationshipCreate,
    RelationshipTypeCreate,
    SearchMentionsRequest,
    StartDailySummaryRequest,
    StartKnowledgeImportRequest,
    StartNoteAnalyzeRequest,
    StartPeriodSummaryRequest,
    TaskCreatedEntitiesResponse,
)
from apps.crm.models.crm_entity import CRMEntity
from apps.crm.models.entity_type import EntityType, EntityTypeFieldUpdate
from apps.crm.models.grant_models import (
    AccessGrantResponse,
    GrantResourceType,
    GrantRole,
    GrantSubjectKind,
)
from apps.crm.models.graph import (
    InfluenceGraphResponse,
    RelatedEntitiesResponse,
    ShortestPathResponse,
)
from apps.crm.models.namespace_template import NamespaceTemplate, NamespaceTemplateType
from apps.crm.models.relationship import Relationship
from apps.crm.models.relationship_type import RelationshipType
from apps.crm.models.suggest import CRMSuggest
from apps.crm.models.task import CRMTask
from apps.crm.services.crm_note_broadcast import broadcast_crm_note_event
from apps.crm.services.entity_export import CrmEntitiesExportPayload, export_entities_to_file
from apps.crm.services.entity_response_enrichment import (
    build_entity_responses_with_semantic_index,
    semantic_text_index_status_by_entity,
)
from apps.crm.services.entity_service import SchemaValidationError
from apps.crm.services.graph_service import GraphEntityLimitExceededError
from apps.crm.services.note_markdown_format_schedule import ActiveTaskExistsError
from apps.crm.system_templates import REQUIRED_NAMESPACE_TEMPLATE_TYPE_IDS
from core.api.integration_oauth_error_html import resolve_oauth_integration_locale
from core.authz.errors import AuthzDenied
from core.authz.models import AuthzObject
from core.context import resolve_namespace_or_raise
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.files.models import FileRecord
from core.i18n.service import t
from core.logging import get_logger
from core.models.base import StrictBaseModel
from core.models.identity_models import Namespace, NamespaceCRMSettings, NamespaceKind, User
from core.pagination import CursorPage, ListResponse, OffsetPage
from core.rag.constants import RAG_IN_PROCESS_PROVIDER_ID
from core.rag.factory import get_rag_provider
from core.request_scope import CompanyScope, require_company
from core.types import JsonObject
from core.websocket import (
    EmptyPayload,
    raise_conflict,
    raise_forbidden,
    raise_invalid,
    raise_not_found,
)
from core.websocket.publisher import Notification, NotificationType, notify_user
from core.worktracker.models import (
    WorkItem,
    WorkItemKind,
    WorkItemState,
    WorktrackerModel,
)

logger = get_logger(__name__)

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


class CrmCompanyInitPayload(StrictBaseModel):
    company_id: str = Field(min_length=1)


class CrmCompanyInitResponse(StrictBaseModel):
    result: dict[str, int | bool]


class CrmOffsetPagePayload(StrictBaseModel):
    limit: int = Field(default=200, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class CrmNamespaceNamePayload(StrictBaseModel):
    name: str = Field(min_length=1)


class CrmNamespaceUpdatePayload(NamespaceUpdateRequest):
    name: str = Field(min_length=1)


class CrmTemplateIdPayload(StrictBaseModel):
    template_id: str = Field(min_length=1)


class CrmTemplateUpdatePayload(NamespaceTemplateUpdateRequest):
    template_id: str = Field(min_length=1)


class CrmTemplateTypeUpsertPayload(NamespaceTemplateTypeUpsertRequest):
    template_id: str = Field(min_length=1)


class CrmTemplateTypeRemovePayload(StrictBaseModel):
    template_id: str = Field(min_length=1)
    type_id: str = Field(min_length=1)






def _company_scope() -> CompanyScope:
    return require_company()


def _template_type_response(item: NamespaceTemplateType) -> NamespaceTemplateTypeResponse:
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


async def _namespace_response(
    di: Di,
    ns: Namespace,
    scope: CompanyScope,
) -> NamespaceResponse:
    integration_badges = await di.integration_registry.build_manifest(
        namespace_name=ns.name,
        company_id=ns.company_id,
        user_id=scope.user_id,
        crm_settings=ns.crm_settings,
    )
    return NamespaceResponse(
        name=ns.name,
        company_id=ns.company_id,
        description=ns.description,
        is_default=ns.is_default,
        kind=ns.kind,
        owner_user_id=ns.owner_user_id,
        crm_settings=ns.crm_settings,
        integration_badges=integration_badges,
    )


def _normalize_allowed_type_ids(raw_value: list[str]) -> list[str]:
    normalized: list[str] = []
    for raw_item in raw_value:
        value = raw_item.strip()
        if not value:
            raise ValueError("allowed_type_ids must not contain empty values")
        if value not in normalized:
            normalized.append(value)
    return normalized


async def _collect_company_type_ids(di: Di) -> set[str]:
    _ = di
    rows = await EntityType.catalog()
    return {item.type_id for item in rows}


def _template_response(
    template: NamespaceTemplate,
    entity_type_ids: list[str],
) -> NamespaceTemplateResponse:
    return NamespaceTemplateResponse(
        template_id=template.template_id,
        name=template.name,
        description=template.description,
        icon=template.icon,
        is_system=template.is_system,
        entity_type_ids=entity_type_ids,
    )


def _raise_service_error(exc: Exception) -> Never:
    if isinstance(exc, AuthzDenied):
        raise_forbidden(exc)
    detail = str(exc)
    lowered = detail.lower()
    if "already exists" in lowered:
        raise_conflict(PlatformConflictError(detail))
    if "not found" in lowered:
        raise_not_found(PlatformNotFoundError(detail))
    raise_invalid(exc)


async def op_crm_company_init(
    payload: CrmCompanyInitPayload,
    *,
    user: User,
    di: Di,
) -> CrmCompanyInitResponse:
    """Insert-only инициализация типов, шаблонов и personal namespace новой компании.

    Зовётся idle-воркером `company_init_new_company` с internal context компании;
    `system` переинициализирует lifespan CRM (`reseed=True`).
    """
    _ = user
    scope = _company_scope()
    if payload.company_id != scope.company_id:
        raise_forbidden(
            ValueError(
                f"company_id {payload.company_id!r} does not match active company {scope.company_id!r}"
            )
        )
    result = await di.company_init_service.initialize_company(payload.company_id)
    return CrmCompanyInitResponse(result=result)


async def op_namespaces_list(
    payload: CrmOffsetPagePayload,
    *,
    user: User,
    di: Di,
) -> OffsetPage[NamespaceResponse]:
    _ = user
    scope = _company_scope()
    namespaces, total = await asyncio.gather(
        di.namespace_service.list_company_workspaces(
            limit=payload.limit, offset=payload.offset
        ),
        di.namespace_service.count(kinds=frozenset({NamespaceKind.COMPANY_WORKSPACE})),
    )
    responses = await asyncio.gather(
        *[_namespace_response(di, ns, scope) for ns in namespaces],
    )
    return OffsetPage[NamespaceResponse](
        items=list(responses),
        total=total,
        limit=payload.limit,
        offset=payload.offset,
    )


async def op_namespaces_create(
    payload: NamespaceCreateRequest,
    *,
    user: User,
    di: Di,
) -> NamespaceResponse:
    _ = user
    scope = _company_scope()
    try:
        namespace = await di.namespace_template_service.create_namespace_from_template(
            namespace_name=payload.name,
            namespace_description=payload.description,
            template_id=payload.template_id,
        )
    except ValueError as error:
        _raise_service_error(error)
    logger.info("crm.namespace_created", namespace=payload.name)
    return await _namespace_response(di, namespace, scope)


async def op_namespaces_editability(
    payload: CrmNamespaceNamePayload,
    *,
    user: User,
    di: Di,
) -> NamespaceEditabilityResponse:
    _ = user
    _ = _company_scope()
    name = payload.name.strip()
    if not name:
        raise_invalid(ValueError("Namespace name is required"))
    existing = await di.namespace_service.get(name)
    if existing is None:
        raise_not_found(PlatformNotFoundError(f"Namespace {name} not found"))
    return await di.namespace_template_service.get_namespace_editability(name)


async def op_namespaces_update(
    payload: CrmNamespaceUpdatePayload,
    *,
    user: User,
    di: Di,
) -> NamespaceResponse:
    _ = user
    scope = _company_scope()
    name = payload.name.strip()
    if not name:
        raise_invalid(ValueError("Namespace name is required"))
    existing = await di.namespace_service.get(name)
    if existing is None:
        raise_not_found(PlatformNotFoundError(f"Namespace {name} not found"))

    allowed_type_ids: list[str] | None = None
    if payload.allowed_type_ids is not None:
        try:
            allowed_type_ids = _normalize_allowed_type_ids(payload.allowed_type_ids)
        except ValueError as exc:
            raise_invalid(exc)
        all_type_ids = await _collect_company_type_ids(di)
        unknown_type_ids = [item for item in allowed_type_ids if item not in all_type_ids]
        if unknown_type_ids:
            raise_invalid(ValueError(f"Unknown type_id values: {', '.join(unknown_type_ids)}"))

    try:
        updated = await di.namespace_template_service.update_existing_namespace(
            namespace_name=name,
            description_is_set="description" in payload.model_fields_set,
            description=payload.description,
            allowed_type_ids=allowed_type_ids,
        )
    except ValueError as exc:
        raise_invalid(exc)
    except RuntimeError as exc:
        raise_not_found(PlatformNotFoundError(str(exc)))

    if payload.crm_settings is None:
        return await _namespace_response(di, updated, scope)

    ns = await di.namespace_template_service.apply_namespace_crm_settings(
        name, payload.crm_settings
    )
    return await _namespace_response(di, ns, scope)


async def op_templates_list(
    payload: CrmOffsetPagePayload,
    *,
    user: User,
    di: Di,
) -> OffsetPage[NamespaceTemplateResponse]:
    _ = user
    _ = di
    company_id = _company_scope().company_id
    page = await NamespaceTemplate.page_for_company(
        company_id,
        limit=payload.limit,
        offset=payload.offset,
    )
    responses: list[NamespaceTemplateResponse] = []
    for template in page.items:
        template_types = await NamespaceTemplateType.list_for_template(template.template_key)
        responses.append(
            _template_response(template, [item.type_id for item in template_types])
        )
    return OffsetPage[NamespaceTemplateResponse](
        items=responses,
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


async def op_templates_schema_options(
    payload: EmptyPayload,
    *,
    user: User,
    di: Di,
) -> NamespaceTemplateSchemaOptionsResponse:
    _ = payload, user, di
    _ = _company_scope()
    return SCHEMA_OPTIONS_RESPONSE


async def op_templates_create(
    payload: NamespaceTemplateCreateRequest,
    *,
    user: User,
    di: Di,
) -> NamespaceTemplateResponse:
    _ = user
    _ = di
    company_id = _company_scope().company_id
    existing = await NamespaceTemplate.by_template_id(company_id, payload.template_id)
    if existing is not None:
        raise_conflict(PlatformConflictError(f"Template {payload.template_id} already exists"))
    try:
        created = await NamespaceTemplate.create(
            NamespaceTemplate(
                template_key=str(uuid.uuid4()),
                company_id=company_id,
                template_id=payload.template_id,
                name=payload.name,
                description=payload.description,
                icon=payload.icon,
                is_system=False,
            )
        )
    except UniqueViolationError:
        raise_conflict(PlatformConflictError(f"Template {payload.template_id} already exists"))
    return _template_response(created, [])


async def op_templates_item(
    payload: CrmTemplateIdPayload,
    *,
    user: User,
    di: Di,
) -> NamespaceTemplateDetailsResponse:
    _ = user
    _ = di
    company_id = _company_scope().company_id
    template = await NamespaceTemplate.by_template_id(company_id, payload.template_id)
    if template is None:
        raise_not_found(PlatformNotFoundError(f"Template {payload.template_id} not found"))
    template_types = await NamespaceTemplateType.list_for_template(template.template_key)
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
        types=[_template_type_response(item) for item in template_types],
    )


async def op_templates_update(
    payload: CrmTemplateUpdatePayload,
    *,
    user: User,
    di: Di,
) -> NamespaceTemplateResponse:
    _ = user
    _ = di
    company_id = _company_scope().company_id
    template = await NamespaceTemplate.by_template_id(company_id, payload.template_id)
    if template is None:
        raise_not_found(PlatformNotFoundError(f"Template {payload.template_id} not found"))
    crm_settings: JsonObject | None = None
    if payload.crm_settings is not None:
        prev = NamespaceCRMSettings()
        raw_existing = template.crm_settings
        if raw_existing is not None and len(raw_existing) > 0:
            prev = NamespaceCRMSettings.model_validate(raw_existing)
        incoming = payload.crm_settings
        data = prev.model_dump()
        for field_name in incoming.model_fields_set:
            data[field_name] = getattr(incoming, field_name)
        crm_settings = NamespaceCRMSettings.model_validate(data).model_dump(mode="json")
    updated = await NamespaceTemplate.update_fields(
        template,
        name=payload.name,
        description=payload.description,
        icon=payload.icon,
        crm_settings=crm_settings,
        crm_settings_is_set=payload.crm_settings is not None,
    )
    template_types = await NamespaceTemplateType.list_for_template(updated.template_key)
    return _template_response(updated, [item.type_id for item in template_types])


async def op_templates_remove(
    payload: CrmTemplateIdPayload,
    *,
    user: User,
    di: Di,
) -> None:
    _ = user
    _ = di
    company_id = _company_scope().company_id
    template = await NamespaceTemplate.by_template_id(company_id, payload.template_id)
    if template is None:
        raise_not_found(PlatformNotFoundError(f"Template {payload.template_id} not found"))
    if template.is_system:
        raise_invalid(ValueError("System template cannot be deleted"))
    _ = await NamespaceTemplateType.delete_by_template_key(template.template_key)
    _ = await NamespaceTemplate.delete_by_id(template.template_key)


async def op_templates_type_upsert(
    payload: CrmTemplateTypeUpsertPayload,
    *,
    user: User,
    di: Di,
) -> NamespaceTemplateTypeResponse:
    _ = user
    _ = di
    company_id = _company_scope().company_id
    template = await NamespaceTemplate.by_template_id(company_id, payload.template_id)
    if template is None:
        raise_not_found(PlatformNotFoundError(f"Template {payload.template_id} not found"))
    item = await NamespaceTemplateType.upsert_by_template_key_and_type_id(
        template_key=template.template_key,
        type_id=payload.type_id,
        parent_type_id=payload.parent_type_id,
        name=payload.name,
        description=payload.description,
        prompt=payload.prompt,
        required_fields=payload.required_fields,
        optional_fields=payload.optional_fields,
        icon=payload.icon,
        color=payload.color,
        is_event=payload.is_event,
        check_duplicates=payload.check_duplicates,
        weight_coefficient=payload.weight_coefficient,
        namespace_ids=payload.namespace_ids,
        is_context_anchor=payload.is_context_anchor,
        is_voice_target=payload.is_voice_target,
    )
    return _template_type_response(item)


async def op_templates_type_remove(
    payload: CrmTemplateTypeRemovePayload,
    *,
    user: User,
    di: Di,
) -> None:
    _ = user
    _ = di
    company_id = _company_scope().company_id
    template = await NamespaceTemplate.by_template_id(company_id, payload.template_id)
    if template is None:
        raise_not_found(PlatformNotFoundError(f"Template {payload.template_id} not found"))
    current_ids = {t.type_id for t in await NamespaceTemplateType.list_for_template(template.template_key)}
    after_remove = current_ids - {payload.type_id}
    if not REQUIRED_NAMESPACE_TEMPLATE_TYPE_IDS <= after_remove:
        raise_invalid(
            ValueError(
                "cannot delete type: namespace template must always keep note and task"
            )
        )
    deleted = await NamespaceTemplateType.delete_by_template_key_and_type_id(
        template.template_key,
        payload.type_id,
    )
    if deleted != 1:
        raise_not_found(PlatformNotFoundError(f"Template type {payload.type_id} not found"))


class CrmEntityTypesListPayload(StrictBaseModel):
    namespace: str | None = None
    limit: int = Field(default=200, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class CrmEntityTypeKeyPayload(StrictBaseModel):
    type_id: str = Field(min_length=1)
    namespace: str = Field(min_length=1)


class CrmEntityTypeUpdatePayload(EntityTypeUpdate):
    type_id: str = Field(min_length=1)
    namespace: str = Field(min_length=1)


class CrmEntityTypePublicFieldsPayload(StrictBaseModel):
    type_id: str = Field(min_length=1)
    namespace: str = Field(min_length=1)
    public_fields: list[str]


def _used_type_colors(types: list[EntityType]) -> set[str]:
    used: set[str] = set()
    for entity_type in types:
        color = entity_type.color
        if color is None or not color.strip():
            continue
        used.add(color)
    return used


def _entity_type_to_response(
    entity: EntityType,
    parent_map: Mapping[str, str | None],
) -> EntityTypeResponse:
    list_entity_type, list_entity_subtype = resolve_list_entity_query_pair(
        entity.type_id, parent_map
    )
    return EntityTypeResponse(
        type_id=entity.type_id,
        company_id=entity.company_id,
        namespace=entity.namespace,
        parent_type_id=entity.parent_type_id,
        name=entity.name,
        description=entity.description,
        prompt=entity.prompt,
        required_fields=entity.required_fields,
        optional_fields=entity.optional_fields,
        public_fields=entity.public_fields,
        icon=entity.icon,
        color=entity.color,
        is_system=entity.is_system,
        is_event=entity.is_event,
        check_duplicates=entity.check_duplicates,
        weight_coefficient=entity.weight_coefficient,
        is_context_anchor=entity.is_context_anchor,
        is_voice_target=entity.is_voice_target,
        auto_resolve_suggests=entity.auto_resolve_suggests,
        extractable=entity.extractable,
        created_at=entity.created_at,
        list_entity_type=list_entity_type,
        list_entity_subtype=list_entity_subtype,
    )


async def _parent_maps_for_types(
    rows: list[EntityType],
) -> dict[str, dict[str, str | None]]:
    namespaces = {item.namespace for item in rows if item.namespace.strip()}
    out: dict[str, dict[str, str | None]] = {}
    for namespace in sorted(namespaces):
        catalog = await EntityType.catalog(
            namespace=namespace,
        )
        out[namespace] = {row.type_id: row.parent_type_id for row in catalog}
    return out


async def _backfill_missing_colors(
    rows: list[EntityType],
) -> None:
    used_colors = _used_type_colors(rows)
    for entity_type in rows:
        color = entity_type.color
        if color is not None and color.strip():
            continue
        assigned_color = assign_color_from_palette(used_colors)
        used_colors.add(assigned_color)
        await EntityType.update_fields(
            entity_type.type_id,
            namespace=entity_type.namespace,
            patch={"color": assigned_color},
        )
        entity_type.color = assigned_color


async def _list_entity_types_page(
    *,
    namespace: str | None,
    limit: int,
    offset: int,
) -> OffsetPage[EntityTypeResponse]:
    company_id = _company_scope().company_id
    listed = (
        EntityType.in_company(company_id, namespace=namespace)
        .order_by("-is_system", "type_id")
        .limit(limit)
        .offset(offset)
    )
    total_rows = EntityType.in_company(company_id, namespace=namespace)
    page, total = await asyncio.gather(listed.all(), total_rows.count())
    if len(page) == 0:
        return OffsetPage[EntityTypeResponse](
            items=[],
            total=total,
            limit=limit,
            offset=offset,
        )
    parent_maps = await _parent_maps_for_types(page)
    await _backfill_missing_colors(page)
    return OffsetPage[EntityTypeResponse](
        items=[_entity_type_to_response(item, parent_maps[item.namespace]) for item in page],
        total=total,
        limit=limit,
        offset=offset,
    )


async def _require_entity_type(
    *,
    type_id: str,
    namespace: str,
) -> EntityType:
    entity_type = await EntityType.by_company_namespace_and_type_id(
        company_id=_company_scope().company_id,
        namespace=namespace,
        type_id=type_id,
    ).get_or_none()
    if entity_type is None:
        raise_not_found(PlatformNotFoundError("EntityType not found"))
    return entity_type


def _normalize_namespace(raw: str) -> str:
    namespace = raw.strip()
    if not namespace:
        raise_invalid(ValueError("namespace is required"))
    return namespace


async def op_entity_types_list(
    payload: CrmEntityTypesListPayload,
    *,
    user: User,
    di: Di,
) -> OffsetPage[EntityTypeResponse]:
    _ = user
    _ = di
    _ = _company_scope()
    namespace = payload.namespace
    if namespace is not None:
        namespace = _normalize_namespace(namespace)
    return await _list_entity_types_page(
        namespace=namespace,
        limit=payload.limit,
        offset=payload.offset,
    )


async def op_entity_types_item(
    payload: CrmEntityTypeKeyPayload,
    *,
    user: User,
    di: Di,
) -> EntityTypeResponse:
    _ = user
    _ = di
    _ = _company_scope()
    namespace = _normalize_namespace(payload.namespace)
    entity_type = await _require_entity_type(type_id=payload.type_id, namespace=namespace)
    color = entity_type.color
    if color is None or not color.strip():
        assigned_color = assign_color_from_palette(set())
        await EntityType.update_fields(
            payload.type_id,
            namespace=namespace,
            patch={"color": assigned_color},
        )
        entity_type.color = assigned_color
    parent_rows = await EntityType.catalog(
        namespace=namespace)
    parent_map = {row.type_id: row.parent_type_id for row in parent_rows}
    return _entity_type_to_response(entity_type, parent_map)


async def op_entity_types_create(
    payload: EntityTypeCreate,
    *,
    user: User,
    di: Di,
) -> EntityTypeResponse:
    _ = user
    scope = _company_scope()
    _ = di
    namespace = _normalize_namespace(payload.namespace)
    existing = await EntityType.by_company_namespace_and_type_id(
        company_id=scope.company_id,
        namespace=namespace,
        type_id=payload.type_id,
    ).get_or_none()
    if existing is not None:
        raise_conflict(
            PlatformConflictError(
                f"EntityType {payload.type_id!r} already exists in namespace {namespace!r}"
            )
        )
    existing_types = await EntityType.catalog()
    used_colors = _used_type_colors(existing_types)
    resolved_color = payload.color
    if resolved_color is None or not resolved_color.strip():
        resolved_color = assign_color_from_palette(used_colors)
    required_fields: JsonObject = {}
    if payload.required_fields is not None:
        required_fields = payload.required_fields
    optional_fields: JsonObject = {}
    if payload.optional_fields is not None:
        optional_fields = payload.optional_fields
    created = EntityType(
        type_id=payload.type_id,
        namespace=namespace,
        name=payload.name,
        description=payload.description,
        parent_type_id=payload.parent_type_id,
        prompt=payload.prompt,
        required_fields=required_fields,
        optional_fields=optional_fields,
        icon=payload.icon,
        color=resolved_color,
        is_system=False,
        is_event=payload.is_event,
        check_duplicates=payload.check_duplicates,
        company_id=scope.company_id,
        is_context_anchor=payload.is_context_anchor,
        is_voice_target=payload.is_voice_target,
        auto_resolve_suggests=payload.auto_resolve_suggests,
    )
    refreshed = await EntityType.create(created)
    parent_rows = await EntityType.catalog(
        namespace=namespace)
    parent_map = {row.type_id: row.parent_type_id for row in parent_rows}
    return _entity_type_to_response(refreshed, parent_map)


async def op_entity_types_update(
    payload: CrmEntityTypeUpdatePayload,
    *,
    user: User,
    di: Di,
) -> EntityTypeResponse:
    _ = user
    _ = di
    _ = _company_scope()
    namespace = _normalize_namespace(payload.namespace)
    entity_type = await _require_entity_type(type_id=payload.type_id, namespace=namespace)
    fields: EntityTypeFieldUpdate = {}
    if payload.name is not None:
        fields["name"] = payload.name
    if payload.description is not None:
        fields["description"] = payload.description
    if payload.parent_type_id is not None:
        fields["parent_type_id"] = payload.parent_type_id
    if payload.prompt is not None:
        fields["prompt"] = payload.prompt
    if payload.required_fields is not None:
        fields["required_fields"] = payload.required_fields
    if payload.optional_fields is not None:
        fields["optional_fields"] = payload.optional_fields
    if payload.icon is not None:
        fields["icon"] = payload.icon
    if payload.color is not None:
        fields["color"] = payload.color
    if payload.is_context_anchor is not None:
        fields["is_context_anchor"] = payload.is_context_anchor
    if payload.is_voice_target is not None:
        fields["is_voice_target"] = payload.is_voice_target
    if payload.auto_resolve_suggests is not None:
        fields["auto_resolve_suggests"] = payload.auto_resolve_suggests
    raw_color = fields.get("color")
    resolved_color = raw_color if isinstance(raw_color, str) else entity_type.color
    if resolved_color is None or not resolved_color.strip():
        fields["color"] = assign_color_from_palette(set())
    if len(fields) > 0:
        await EntityType.update_fields(
            payload.type_id, namespace=namespace, patch=fields
        )
    refreshed = await _require_entity_type(type_id=payload.type_id, namespace=namespace)
    parent_rows = await EntityType.catalog(
        namespace=namespace)
    parent_map = {row.type_id: row.parent_type_id for row in parent_rows}
    return _entity_type_to_response(refreshed, parent_map)


async def op_entity_types_public_fields(
    payload: CrmEntityTypePublicFieldsPayload,
    *,
    user: User,
    di: Di,
) -> EntityTypeResponse:
    _ = user
    _ = _company_scope()
    _ = di
    namespace = _normalize_namespace(payload.namespace)
    _ = await _require_entity_type(type_id=payload.type_id, namespace=namespace)
    await EntityType.update_fields(
        payload.type_id,
        namespace=namespace,
        patch={"public_fields": payload.public_fields},
    )
    refreshed = await _require_entity_type(type_id=payload.type_id, namespace=namespace)
    parent_rows = await EntityType.catalog(
        namespace=namespace)
    parent_map = {row.type_id: row.parent_type_id for row in parent_rows}
    return _entity_type_to_response(refreshed, parent_map)


class CrmGrantsListPayload(StrictBaseModel):
    resource_type: GrantResourceType
    resource_id: str = Field(min_length=1)
    limit: int = Field(default=200, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class CrmGrantCreatePayload(StrictBaseModel):
    resource_type: GrantResourceType
    resource_id: str = Field(min_length=1)
    subject: GrantSubjectKind
    user_id: str | None = None
    company_id: str | None = None
    role: GrantRole = "viewer"


class CrmGrantIdPayload(StrictBaseModel):
    grant_id: str = Field(min_length=1)


async def op_grants_list(
    payload: CrmGrantsListPayload,
    *,
    user: User,
    di: Di,
) -> OffsetPage[AccessGrantResponse]:
    _ = user
    scope = _company_scope()
    resource_id = payload.resource_id.strip()
    if not resource_id:
        raise_invalid(ValueError("resource_id is required"))
    company_id: str | None = None
    if payload.resource_type == "namespace":
        company_id = scope.company_id
    try:
        grants = await di.access_grant_service.list_grants(
            payload.resource_type, resource_id, company_id
        )
    except (AuthzDenied, ValueError) as exc:
        _raise_service_error(exc)
    page = grants[payload.offset : payload.offset + payload.limit]
    return OffsetPage[AccessGrantResponse](
        items=page,
        total=len(grants),
        limit=payload.limit,
        offset=payload.offset,
    )


async def op_grants_create(
    payload: CrmGrantCreatePayload,
    *,
    user: User,
    di: Di,
) -> AccessGrantResponse:
    _ = user
    scope = _company_scope()
    resource_id = payload.resource_id.strip()
    if not resource_id:
        raise_invalid(ValueError("resource_id is required"))
    service = di.access_grant_service
    try:
        if payload.resource_type == "entity":
            if payload.subject == "public":
                return await service.grant_entity_public(
                    entity_id=resource_id, created_by=scope.user_id
                )
            if payload.subject == "user":
                user_id = payload.user_id
                if user_id is None or not user_id.strip():
                    raise_invalid(ValueError("user_id is required"))
                return await service.grant_entity_to_user(
                    entity_id=resource_id,
                    target_user_id=user_id.strip(),
                    role=payload.role,
                    created_by=scope.user_id,
                )
            company_id = payload.company_id
            if company_id is None or not company_id.strip():
                raise_invalid(ValueError("company_id is required"))
            return await service.grant_entity_to_company(
                entity_id=resource_id,
                target_company_id=company_id.strip(),
                role=payload.role,
                created_by=scope.user_id,
            )
        if payload.subject == "public":
            return await service.grant_namespace_public(
                namespace=resource_id,
                company_id=scope.company_id,
                created_by=scope.user_id,
            )
        if payload.subject == "user":
            user_id = payload.user_id
            if user_id is None or not user_id.strip():
                raise_invalid(ValueError("user_id is required"))
            return await service.grant_namespace_to_user(
                namespace=resource_id,
                company_id=scope.company_id,
                target_user_id=user_id.strip(),
                role=payload.role,
                created_by=scope.user_id,
            )
        company_id = payload.company_id
        if company_id is None or not company_id.strip():
            raise_invalid(ValueError("company_id is required"))
        return await service.grant_namespace_to_company(
            namespace=resource_id,
            company_id=scope.company_id,
            target_company_id=company_id.strip(),
            role=payload.role,
            created_by=scope.user_id,
        )
    except (AuthzDenied, ValueError) as exc:
        _raise_service_error(exc)


async def op_grants_item(
    payload: CrmGrantIdPayload,
    *,
    user: User,
    di: Di,
) -> AccessGrantResponse:
    _ = user
    _ = _company_scope()
    try:
        return await di.access_grant_service.get_grant(payload.grant_id)
    except (AuthzDenied, ValueError) as exc:
        _raise_service_error(exc)


async def op_grants_remove(
    payload: CrmGrantIdPayload,
    *,
    user: User,
    di: Di,
) -> None:
    _ = user
    scope = _company_scope()
    try:
        await di.access_grant_service.revoke_grant(payload.grant_id, scope.user_id)
    except (AuthzDenied, ValueError) as exc:
        _raise_service_error(exc)


class CrmEntityIdPayload(StrictBaseModel):
    entity_id: str = Field(min_length=1)


class CrmEntityUpdatePayload(EntityUpdate):
    entity_id: str = Field(min_length=1)


class CrmEntitiesAggregatePayload(StrictBaseModel):
    namespace: str | None = None


async def build_entity_response(di: Di, entity: CRMEntity) -> EntityResponse:
    items = await build_entity_responses_with_semantic_index(
        get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID),
        [entity],
        crm_work_item_service=di.crm_work_item_service,
    )
    return items[0]


async def _require_entity(di: Di, entity_id: str) -> CRMEntity:
    entity = await di.entity_service.get_entity(entity_id)
    if entity is None:
        raise_not_found(PlatformNotFoundError("Entity not found"))
    return entity


async def op_entities_create(
    payload: EntityCreate,
    *,
    user: User,
    di: Di,
) -> EntityResponse:
    _ = user
    _ = _company_scope()
    try:
        entity = await di.entity_service.create_entity(
            entity_type=payload.entity_type,
            name=payload.name,
            description=payload.description,
            entity_subtype=payload.entity_subtype,
            namespace=payload.namespace,
            attributes=payload.attributes,
            tags=payload.tags,
            attachment_ids=payload.attachment_ids,
            user_id=payload.user_id,
            note_date=payload.note_date,
            voice_entity_id=payload.voice_entity_id,
            context_entity_id=payload.context_entity_id,
            voice_entity_in_payload="voice_entity_id" in payload.model_fields_set,
            context_entity_in_payload="context_entity_id" in payload.model_fields_set,
        )
    except SchemaValidationError as exc:
        raise_invalid(exc)
    except ValueError as exc:
        _raise_service_error(exc)
    return await build_entity_response(di, entity)


async def op_entities_item(
    payload: CrmEntityIdPayload,
    *,
    user: User,
    di: Di,
) -> EntityResponse | JsonObject:
    _ = user
    scope = _company_scope()
    entity = await _require_entity(di, payload.entity_id)
    try:
        await di.authz_service.require_can_view(
            AuthzObject.crm_entity(entity.entity_id), user_id=scope.user_id
        )
        filtered = await di.crm_entity_access_service.filter_fields(
            entity, scope.user_id, scope.company_id
        )
    except AuthzDenied as exc:
        raise_forbidden(exc)
    if isinstance(filtered, CRMEntity):
        return await build_entity_response(di, filtered)
    return filtered


async def op_entities_update(
    payload: CrmEntityUpdatePayload,
    *,
    user: User,
    di: Di,
) -> EntityResponse:
    _ = user
    scope = _company_scope()
    entity = await _require_entity(di, payload.entity_id)
    try:
        await di.authz_service.require_can_edit(
            AuthzObject.crm_entity(entity.entity_id), user_id=scope.user_id
        )
    except AuthzDenied as exc:
        raise_forbidden(exc)
    updates = payload.model_dump(exclude_none=True)
    updates.pop("entity_id", None)
    updates.pop("voice_entity_id", None)
    updates.pop("context_entity_id", None)
    if "entity_subtype" in payload.model_fields_set:
        updates["entity_subtype"] = payload.entity_subtype
    try:
        updated = await di.entity_service.update_entity(
            payload.entity_id,
            updates,
            voice_entity_id=payload.voice_entity_id,
            voice_entity_in_payload="voice_entity_id" in payload.model_fields_set,
            context_entity_id=payload.context_entity_id,
            context_entity_in_payload="context_entity_id" in payload.model_fields_set,
        )
    except SchemaValidationError as exc:
        raise_invalid(exc)
    except ValueError as exc:
        _raise_service_error(exc)
    return await build_entity_response(di, updated)


async def op_entities_remove(
    payload: CrmEntityIdPayload,
    *,
    user: User,
    di: Di,
) -> None:
    _ = user
    scope = _company_scope()
    entity = await _require_entity(di, payload.entity_id)
    try:
        await di.authz_service.require_can_edit(
            AuthzObject.crm_entity(entity.entity_id), user_id=scope.user_id
        )
    except AuthzDenied as exc:
        raise_forbidden(exc)
    deleted = await di.entity_service.delete_entity(payload.entity_id)
    if not deleted:
        raise_not_found(PlatformNotFoundError("Entity not found"))


async def op_entities_query(
    payload: EntitySearchQueryRequest,
    *,
    user: User,
    di: Di,
) -> CursorPage[EntityResponse]:
    _ = user
    _ = _company_scope()
    filters_dict = (
        payload.filters.model_dump(by_alias=True, exclude_none=True)
        if payload.filters is not None
        else None
    )
    try:
        namespace_name = resolve_namespace_or_raise(payload.namespace)
        filter_field_types = await di.entity_service.resolve_filter_field_types(
            namespace=namespace_name,
            entity_type=payload.entity_type,
            entity_subtype=payload.entity_subtype,
            filters=filters_dict,
        )
        if payload.query is None or payload.query.strip() == "":
            entities, next_cursor, has_more = await di.entity_service.list_entities(
                entity_type=payload.entity_type,
                entity_subtype=payload.entity_subtype,
                namespace=payload.namespace,
                filters=filters_dict,
                filter_field_types=filter_field_types,
                limit=payload.limit,
                cursor=payload.cursor,
            )
            items = await build_entity_responses_with_semantic_index(
                get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID),
                entities,
                crm_work_item_service=di.crm_work_item_service,
            )
            return CursorPage[EntityResponse](
                items=items,
                next_cursor=next_cursor,
                has_more=has_more,
            )
        if payload.cursor is not None:
            raise_invalid(ValueError("cursor is not supported for search query mode"))
        query = payload.query.strip()
        if payload.search_mode == "hybrid":
            hybrid_rows = await di.entity_service.hybrid_search(
                query=query,
                entity_type=payload.entity_type,
                entity_subtype=payload.entity_subtype,
                namespace=payload.namespace,
                filters=filters_dict,
                filter_field_types=filter_field_types,
                limit=payload.limit,
            )
            items = await build_entity_responses_with_semantic_index(
                get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID),
                [row[0] for row in hybrid_rows],
                crm_work_item_service=di.crm_work_item_service,
            )
            for resp, row in zip(items, hybrid_rows, strict=True):
                resp.score = row[1]
                resp.match_type = row[2]
            return CursorPage[EntityResponse](items=items, next_cursor=None, has_more=False)
        if payload.search_mode == "text":
            text_rows = await di.entity_service.text_search(
                query=query,
                entity_type=payload.entity_type,
                entity_subtype=payload.entity_subtype,
                namespace=payload.namespace,
                filters=filters_dict,
                filter_field_types=filter_field_types,
                limit=payload.limit,
            )
            items = await build_entity_responses_with_semantic_index(
                get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID),
                [row[0] for row in text_rows],
                crm_work_item_service=di.crm_work_item_service,
            )
            for resp, row in zip(items, text_rows, strict=True):
                resp.score = row[1]
                resp.match_type = "text"
            return CursorPage[EntityResponse](items=items, next_cursor=None, has_more=False)
        semantic_rows = await di.entity_service.search_entities(
            query=query,
            entity_type=payload.entity_type,
            entity_subtype=payload.entity_subtype,
            namespace=payload.namespace,
            filters=filters_dict,
            filter_field_types=filter_field_types,
            limit=payload.limit,
        )
        items = await build_entity_responses_with_semantic_index(
            get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID),
            [row[0] for row in semantic_rows],
            crm_work_item_service=di.crm_work_item_service,
        )
        for resp, row in zip(items, semantic_rows, strict=True):
            resp.score = row[1]
            resp.match_type = "semantic"
        return CursorPage[EntityResponse](items=items, next_cursor=None, has_more=False)
    except ValueError as exc:
        _raise_service_error(exc)


async def op_entities_mentions_search(
    payload: SearchMentionsRequest,
    *,
    user: User,
    di: Di,
) -> ListResponse[EntityResponse]:
    _ = user
    _ = _company_scope()
    try:
        entities = await di.entity_service.search_mentions(
            payload.text,
            namespace=payload.namespace,
            limit=20,
        )
    except ValueError as exc:
        _raise_service_error(exc)
    items = await build_entity_responses_with_semantic_index(
        get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID),
        entities,
        crm_work_item_service=di.crm_work_item_service,
    )
    return ListResponse[EntityResponse](items=items)


async def op_entities_merge(
    payload: EntityMergeRequest,
    *,
    user: User,
    di: Di,
) -> EntityMergeResponse:
    _ = user
    scope = _company_scope()
    survivor = await di.entity_service.get_entity(payload.survivor_entity_id.strip())
    source = await di.entity_service.get_entity(payload.source_entity_id.strip())
    if survivor is None:
        raise_not_found(PlatformNotFoundError("Survivor entity not found"))
    if source is None:
        raise_not_found(PlatformNotFoundError("Source entity not found"))
    try:
        await di.authz_service.require_can_edit(
            AuthzObject.crm_entity(survivor.entity_id), user_id=scope.user_id
        )
        await di.authz_service.require_can_edit(
            AuthzObject.crm_entity(source.entity_id), user_id=scope.user_id
        )
        merged, merged_from_id = await di.entity_service.merge_entities(payload)
        filtered = await di.crm_entity_access_service.filter_fields(
            merged, scope.user_id, scope.company_id
        )
    except AuthzDenied as exc:
        raise_forbidden(exc)
    except ValueError as exc:
        _raise_service_error(exc)
    status_by_id = await semantic_text_index_status_by_entity(
        get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID),
        [merged],
    )
    merge_entity_resp = EntityResponse.model_validate(filtered).model_copy(
        update={"semantic_text_index_status": status_by_id.get(merged.entity_id)},
    )
    return EntityMergeResponse(entity=merge_entity_resp, merged_from_entity_id=merged_from_id)


async def op_entities_bulk_create(
    payload: BulkCreateRequest,
    *,
    user: User,
    di: Di,
) -> BulkCreateResponse:
    _ = user
    _ = _company_scope()
    if len(payload.items) > 200:
        raise_invalid(ValueError("Maximum 200 items per batch"))
    created_entities: list[CRMEntity] = []
    errors: list[BulkErrorItem] = []
    for idx, item in enumerate(payload.items):
        try:
            entity = await di.entity_service.create_entity(
                entity_type=item.entity_type,
                name=item.name,
                description=item.description,
                entity_subtype=item.entity_subtype,
                namespace=item.namespace,
                attributes=item.attributes,
                tags=item.tags,
                user_id=item.user_id,
                note_date=item.note_date,
            )
            created_entities.append(entity)
        except (ValueError, SchemaValidationError) as exc:
            errors.append(BulkErrorItem(index=idx, error=str(exc)))
    created = await build_entity_responses_with_semantic_index(
        get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID),
        created_entities,
        crm_work_item_service=di.crm_work_item_service,
    )
    return BulkCreateResponse(created=created, errors=errors)


async def op_entities_bulk_update(
    payload: BulkUpdateRequest,
    *,
    user: User,
    di: Di,
) -> BulkUpdateResponse:
    _ = user
    _ = _company_scope()
    if len(payload.items) > 200:
        raise_invalid(ValueError("Maximum 200 items per batch"))
    updated_entities: list[CRMEntity] = []
    errors: list[BulkErrorItem] = []
    for idx, item in enumerate(payload.items):
        try:
            entity = await di.entity_service.update_entity(item.entity_id, item.updates)
            updated_entities.append(entity)
        except ValueError as exc:
            errors.append(BulkErrorItem(index=idx, entity_id=item.entity_id, error=str(exc)))
    updated = await build_entity_responses_with_semantic_index(
        get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID),
        updated_entities,
        crm_work_item_service=di.crm_work_item_service,
    )
    return BulkUpdateResponse(updated=updated, errors=errors)


async def op_entities_bulk_delete(
    payload: BulkDeleteRequest,
    *,
    user: User,
    di: Di,
) -> BulkDeleteResponse:
    _ = user
    _ = _company_scope()
    if len(payload.entity_ids) > 200:
        raise_invalid(ValueError("Maximum 200 items per batch"))
    deleted: list[str] = []
    errors: list[BulkErrorItem] = []
    for idx, entity_id in enumerate(payload.entity_ids):
        try:
            success = await di.entity_service.delete_entity(entity_id)
            if success:
                deleted.append(entity_id)
            else:
                errors.append(
                    BulkErrorItem(index=idx, entity_id=entity_id, error="Entity not found")
                )
        except ValueError as exc:
            errors.append(BulkErrorItem(index=idx, entity_id=entity_id, error=str(exc)))
    return BulkDeleteResponse(deleted=deleted, errors=errors)


async def op_entities_card(
    payload: CrmEntityIdPayload,
    *,
    user: User,
    di: Di,
) -> JsonObject:
    _ = user
    scope = _company_scope()
    entity = await _require_entity(di, payload.entity_id)
    try:
        await di.authz_service.require_can_view(
            AuthzObject.crm_entity(entity.entity_id), user_id=scope.user_id
        )
        return await di.entity_service.get_entity_card(payload.entity_id)
    except AuthzDenied as exc:
        raise_forbidden(exc)
    except ValueError as exc:
        _raise_service_error(exc)


async def op_entities_aggregate(
    payload: CrmEntitiesAggregatePayload,
    *,
    user: User,
    di: Di,
) -> JsonObject:
    _ = user
    _ = _company_scope()
    return await di.entity_service.aggregate_facets(namespace=payload.namespace)


async def op_entities_export(
    payload: CrmEntitiesExportPayload,
    *,
    user: User,
    di: Di,
) -> FileRecord:
    """Выгрузка сущностей в CSV/JSON; клиент скачивает файл по `download_url`."""
    _ = user
    _ = _company_scope()
    return await export_entities_to_file(
        di.entity_service,
        di.crm_work_item_service,
        di.files_service,
        payload,
    )


class CrmNoteIdPayload(StrictBaseModel):
    note_id: str = Field(min_length=1)


class CrmNoteAnalysisDraftSavePayload(AIAnalysisDraftPatchRequest):
    note_id: str = Field(min_length=1)


async def op_notes_analysis_draft_save(
    payload: CrmNoteAnalysisDraftSavePayload,
    *,
    user: User,
    di: Di,
) -> AIAnalysisDraftStored:
    _ = user
    scope = _company_scope()
    note = await _require_entity(di, payload.note_id)
    try:
        await di.authz_service.require_can_edit(
            AuthzObject.crm_entity(note.entity_id), user_id=scope.user_id
        )
        return await di.entity_service.patch_analysis_draft(payload.note_id, payload)
    except AuthzDenied as exc:
        raise_forbidden(exc)
    except PlatformConflictError as exc:
        raise_conflict(exc)
    except ValueError as exc:
        _raise_service_error(exc)


async def op_notes_analysis_draft_discard(
    payload: CrmNoteIdPayload,
    *,
    user: User,
    di: Di,
) -> None:
    _ = user
    scope = _company_scope()
    note = await _require_entity(di, payload.note_id)
    try:
        await di.authz_service.require_can_edit(
            AuthzObject.crm_entity(note.entity_id), user_id=scope.user_id
        )
        await di.entity_service.discard_note_analysis_draft(payload.note_id)
    except AuthzDenied as exc:
        raise_forbidden(exc)
    except ValueError as exc:
        _raise_service_error(exc)


async def op_notes_analysis_error_dismiss(
    payload: CrmNoteIdPayload,
    *,
    user: User,
    di: Di,
) -> None:
    _ = user
    scope = _company_scope()
    note = await _require_entity(di, payload.note_id)
    try:
        await di.authz_service.require_can_edit(
            AuthzObject.crm_entity(note.entity_id), user_id=scope.user_id
        )
        await di.entity_service.clear_note_analysis_error(payload.note_id)
    except AuthzDenied as exc:
        raise_forbidden(exc)
    except ValueError as exc:
        _raise_service_error(exc)


async def op_notes_analysis_draft_repair(
    payload: CrmNoteIdPayload,
    *,
    user: User,
    di: Di,
) -> NoteAnalysisDraftRepairQueuedResponse:
    _ = user
    scope = _company_scope()
    note = await _require_entity(di, payload.note_id)
    try:
        await di.authz_service.require_can_edit(
            AuthzObject.crm_entity(note.entity_id), user_id=scope.user_id
        )
    except AuthzDenied as exc:
        raise_forbidden(exc)
    raw_attrs = note.attributes
    if not isinstance(raw_attrs.get("ai_analysis_draft"), dict):
        raise_invalid(ValueError("note has no ai_analysis_draft"))
    summary_raw = raw_attrs.get("ai_analysis_last_error")
    summary_ok = isinstance(summary_raw, str) and summary_raw.strip() != ""
    failures_raw = raw_attrs.get("ai_analysis_apply_failures")
    failures_ok = isinstance(failures_raw, list) and len(failures_raw) > 0
    if not summary_ok and not failures_ok:
        raise_invalid(ValueError("no stored draft apply error"))
    namespace = resolve_namespace_or_raise(note.namespace)
    note_date_iso = note.note_date.isoformat() if note.note_date is not None else None
    await broadcast_crm_note_event(
        company_id=scope.company_id,
        namespace=namespace,
        note_id=payload.note_id,
        note_date_iso=note_date_iso,
        action="updated",
        note=note,
        authz=di.authz_service,
        skip_notification_center=True,
        draft_repair={"phase": "started"},
    )
    try:
        row = await di.task_service.start_note_analysis_draft_repair(
            note_id=payload.note_id
        )
    except ActiveTaskExistsError as exc:
        raise_conflict(exc)
    except ValueError as exc:
        _raise_service_error(exc)
    return NoteAnalysisDraftRepairQueuedResponse(
        note_id=payload.note_id,
        task_id=row.task_id,
        queued=True,
    )


async def op_notes_markdown_format(
    payload: CrmNoteIdPayload,
    *,
    user: User,
    di: Di,
) -> NoteMarkdownFormatQueuedResponse:
    _ = user
    scope = _company_scope()
    note = await _require_entity(di, payload.note_id)
    try:
        await di.authz_service.require_can_edit(
            AuthzObject.crm_entity(note.entity_id), user_id=scope.user_id
        )
        row = await di.task_service.start_note_markdown_format(note_id=payload.note_id)
    except AuthzDenied as exc:
        raise_forbidden(exc)
    except ActiveTaskExistsError as exc:
        raise_conflict(exc)
    except ValueError as exc:
        _raise_service_error(exc)
    return NoteMarkdownFormatQueuedResponse(note_id=payload.note_id, task_id=row.task_id)


async def op_notes_analyze(
    payload: StartNoteAnalyzeRequest,
    *,
    user: User,
    di: Di,
) -> CRMTask:
    _ = user
    scope = _company_scope()
    note = await _require_entity(di, payload.note_id)
    config = NoteProcessingConfig(
        include_attachments=payload.include_attachments,
        attachment_chars_limit_per_file=payload.attachment_chars_limit_per_file,
        check_duplicates=payload.check_duplicates,
        extract_entity_types=payload.extract_entity_types,
        extract_relationship_types=payload.extract_relationship_types,
        mentioned_entity_ids=payload.mentioned_entity_ids,
    )
    ns = resolve_namespace_or_raise(note.namespace)
    try:
        await di.authz_service.require_can_edit(
            AuthzObject.crm_entity(note.entity_id), user_id=scope.user_id
        )
        row = await di.task_service.start_note_analyze(
            note_id=payload.note_id,
            note_name=note.name,
            namespace=ns,
            mode=payload.mode,
            config=config,
        )
    except AuthzDenied as exc:
        raise_forbidden(exc)
    except ActiveTaskExistsError as exc:
        raise_conflict(exc)
    except ValueError as exc:
        _raise_service_error(exc)
    return CRMTask.model_validate(row)


async def op_entities_cards_bulk(
    payload: BulkCardsRequest,
    *,
    user: User,
    di: Di,
) -> dict[str, JsonObject]:
    _ = user
    _ = _company_scope()
    return await di.entity_service.get_bulk_entity_cards(payload.entity_ids)


def _raise_graph_error(exc: Exception) -> Never:
    if isinstance(exc, AuthzDenied):
        raise_forbidden(exc)
    if isinstance(exc, GraphEntityLimitExceededError):
        raise_invalid(exc)
    if isinstance(exc, ValueError):
        _raise_service_error(exc)
    raise exc


class CrmEntitiesTimelineBoundsPayload(StrictBaseModel):
    entity_type: str | None = None
    entity_subtype: str | None = None
    namespace: str | None = None


class CrmOverviewGraphPayload(StrictBaseModel):
    entity_ids: list[str]
    max_depth: int = Field(default=3, ge=1, le=5)
    relationship_types: list[str] | None = None
    created_at_from: datetime | None = None
    created_at_to: datetime | None = None
    namespace: str | None = None
    include_all_namespaces: bool = False


class CrmEntitiesInfluenceGraphPayload(StrictBaseModel):
    entity_id: str = Field(min_length=1)
    max_depth: int = Field(default=3, ge=1, le=5)
    relationship_types: list[str] | None = None
    created_at_from: datetime | None = None
    created_at_to: datetime | None = None
    namespace: str | None = None
    include_all_namespaces: bool = False


class CrmEntitiesRelatedPayload(StrictBaseModel):
    entity_id: str = Field(min_length=1)
    direction: Literal["incoming", "outgoing", "both"] = "both"
    relationship_type: str | None = None
    created_at_from: datetime | None = None
    created_at_to: datetime | None = None
    namespace: str | None = None
    include_all_namespaces: bool = False


class CrmRelationshipsPathPayload(StrictBaseModel):
    source_entity_id: str = Field(min_length=1)
    target_entity_id: str = Field(min_length=1)
    max_depth: int = Field(default=10, ge=1, le=20)
    created_at_from: datetime | None = None
    created_at_to: datetime | None = None
    namespace: str | None = None
    include_all_namespaces: bool = False


class CrmEntityRelationshipsResponse(StrictBaseModel):
    relationships: list[Relationship]


class CrmExclusiveRelatedResponse(StrictBaseModel):
    entities: list[JsonObject]


async def op_entities_person_self(
    payload: EmptyPayload,
    *,
    user: User,
    di: Di,
) -> EntityResponse:
    _ = payload
    scope = _company_scope()
    person_id = await di.user_person_service.get_or_create_person_entity_id(
        user.user_id,
        scope.company_id,
    )
    entity = await CRMEntity.get(person_id)
    if entity is None:
        raise_not_found(PlatformNotFoundError("Person entity not found"))
    return await build_entity_response(di, entity)


async def op_entities_timeline_bounds(
    payload: CrmEntitiesTimelineBoundsPayload,
    *,
    user: User,
    di: Di,
) -> EntityTimelineBoundsResponse:
    _ = user
    _ = _company_scope()
    bounds = await di.entity_service.get_timeline_bounds(
        entity_type=payload.entity_type,
        entity_subtype=payload.entity_subtype,
        namespace=payload.namespace,
    )
    return EntityTimelineBoundsResponse.model_validate(bounds)


async def op_entities_overview_graph(
    payload: CrmOverviewGraphPayload,
    *,
    user: User,
    di: Di,
) -> InfluenceGraphResponse:
    _ = user
    _ = _company_scope()
    if len(payload.entity_ids) == 0:
        raise_invalid(ValueError("entity_ids must not be empty"))
    try:
        return await di.graph_service.build_overview_graph(
            entity_ids=payload.entity_ids,
            max_depth=payload.max_depth,
            relationship_types=payload.relationship_types,
            created_at_from=payload.created_at_from,
            created_at_to=payload.created_at_to,
            namespace=payload.namespace,
            include_all_namespaces=payload.include_all_namespaces,
        )
    except (AuthzDenied, GraphEntityLimitExceededError, ValueError) as exc:
        _raise_graph_error(exc)


async def op_entities_influence_graph(
    payload: CrmEntitiesInfluenceGraphPayload,
    *,
    user: User,
    di: Di,
) -> InfluenceGraphResponse:
    _ = user
    _ = _company_scope()
    try:
        return await di.graph_service.build_influence_graph(
            entity_id=payload.entity_id,
            max_depth=payload.max_depth,
            relationship_types=payload.relationship_types,
            created_at_from=payload.created_at_from,
            created_at_to=payload.created_at_to,
            namespace=payload.namespace,
            include_all_namespaces=payload.include_all_namespaces,
        )
    except (AuthzDenied, GraphEntityLimitExceededError, ValueError) as exc:
        _raise_graph_error(exc)


async def op_entities_related(
    payload: CrmEntitiesRelatedPayload,
    *,
    user: User,
    di: Di,
) -> RelatedEntitiesResponse:
    _ = user
    _ = _company_scope()
    try:
        return await di.graph_service.get_related_entities(
            entity_id=payload.entity_id,
            direction=payload.direction,
            relationship_type=payload.relationship_type,
            created_at_from=payload.created_at_from,
            created_at_to=payload.created_at_to,
            namespace=payload.namespace,
            include_all_namespaces=payload.include_all_namespaces,
        )
    except (AuthzDenied, GraphEntityLimitExceededError, ValueError) as exc:
        _raise_graph_error(exc)


async def op_entities_relationships(
    payload: CrmEntityIdPayload,
    *,
    user: User,
    di: Di,
) -> CrmEntityRelationshipsResponse:
    _ = user
    scope = _company_scope()
    entity = await _require_entity(di, payload.entity_id)
    try:
        await di.authz_service.require_can_view(
            AuthzObject.crm_entity(entity.entity_id), user_id=scope.user_id
        )
    except AuthzDenied as exc:
        raise_forbidden(exc)
    rows = await Relationship.touching_in_company(
        payload.entity_id,
        scope.company_id,
    ).all()
    return CrmEntityRelationshipsResponse(relationships=rows)


async def op_entities_exclusive_related(
    payload: CrmEntityIdPayload,
    *,
    user: User,
    di: Di,
) -> CrmExclusiveRelatedResponse:
    _ = user
    scope = _company_scope()
    entity = await _require_entity(di, payload.entity_id)
    if entity.entity_type != NOTE_ROOT_ENTITY_TYPE_ID:
        raise_invalid(ValueError("Only notes have exclusive related entities"))
    try:
        await di.authz_service.require_can_edit(
            AuthzObject.crm_entity(entity.entity_id), user_id=scope.user_id
        )
    except AuthzDenied as exc:
        raise_forbidden(exc)
    entities = await di.entity_service.get_exclusive_related_entities_for_note(
        payload.entity_id
    )
    return CrmExclusiveRelatedResponse(entities=entities)


async def op_relationships_path(
    payload: CrmRelationshipsPathPayload,
    *,
    user: User,
    di: Di,
) -> ShortestPathResponse:
    _ = user
    _ = _company_scope()
    try:
        return await di.graph_service.find_shortest_path(
            from_entity_id=payload.source_entity_id,
            to_entity_id=payload.target_entity_id,
            max_depth=payload.max_depth,
            created_at_from=payload.created_at_from,
            created_at_to=payload.created_at_to,
            namespace=payload.namespace,
            include_all_namespaces=payload.include_all_namespaces,
        )
    except (AuthzDenied, GraphEntityLimitExceededError, ValueError) as exc:
        _raise_graph_error(exc)


class CrmRelationshipIdPayload(StrictBaseModel):
    relationship_id: str = Field(min_length=1)


class CrmRelationshipsListPayload(StrictBaseModel):
    entity_id: str | None = None
    namespace: str | None = None
    cursor: str | None = None
    limit: int = Field(default=200, ge=1, le=1000)


async def op_relationships_list(
    payload: CrmRelationshipsListPayload,
    *,
    user: User,
    di: Di,
) -> CursorPage[Relationship]:
    _ = user
    _ = di
    _ = _company_scope()
    if payload.namespace is not None and payload.namespace.strip() == "":
        raise_invalid(ValueError("namespace must not be empty"))
    if payload.entity_id is not None and payload.entity_id != "":
        relationships = await Relationship.touching_in_company(
            payload.entity_id,
            _company_scope().company_id,
        ).all()
        if payload.namespace is not None:
            relationships = [row for row in relationships if row.namespace == payload.namespace]
        return CursorPage[Relationship](
            items=relationships,
            next_cursor=None,
            has_more=False,
        )
    page = await Relationship.graph_page(
        limit=payload.limit,
        cursor=payload.cursor,
    )
    batch = page.items
    if payload.namespace is not None:
        batch = [row for row in batch if row.namespace == payload.namespace]
    return CursorPage[Relationship](
        items=batch,
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


async def op_relationships_item(
    payload: CrmRelationshipIdPayload,
    *,
    user: User,
    di: Di,
) -> Relationship:
    _ = user
    _ = _company_scope()
    _ = di
    relationship = await Relationship.get(payload.relationship_id)
    if relationship is None:
        raise_not_found(PlatformNotFoundError("Relationship not found"))
    return relationship


async def op_relationships_create(
    payload: RelationshipCreate,
    *,
    user: User,
    di: Di,
) -> Relationship:
    _ = user
    _ = di
    scope = _company_scope()
    all_types = await RelationshipType.in_company(
        scope.company_id,
        include_system=True,
    ).all()
    valid_type_ids = {row.type_id for row in all_types}
    if payload.relationship_type not in valid_type_ids:
        raise_invalid(ValueError(f"Unknown relationship_type: {payload.relationship_type}"))
    now = datetime.now(UTC)
    relationship = Relationship(
        relationship_id=str(uuid.uuid4()),
        source_entity_id=payload.source_entity_id,
        target_entity_id=payload.target_entity_id,
        relationship_type=payload.relationship_type,
        namespace=payload.namespace,
        weight=payload.weight,
        confidence=payload.confidence,
        attributes=payload.attributes,
        company_id=scope.company_id,
        created_at=now,
        updated_at=now,
    )
    try:
        created = await Relationship.create(relationship)
    except UniqueViolationError:
        raise_conflict(PlatformConflictError("Relationship already exists"))
    return created


async def op_relationships_remove(
    payload: CrmRelationshipIdPayload,
    *,
    user: User,
    di: Di,
) -> None:
    _ = user
    _ = di
    _ = _company_scope()
    deleted = await Relationship.delete_by_id(payload.relationship_id)
    if not deleted:
        raise_not_found(PlatformNotFoundError("Relationship not found"))


async def op_relationship_types_list(
    payload: CrmOffsetPagePayload,
    *,
    user: User,
    di: Di,
) -> OffsetPage[RelationshipType]:
    _ = user
    _ = di
    company_id = _company_scope().company_id
    rows = RelationshipType.in_company(
        company_id,
        include_system=True,
    )
    total = await rows.count()
    types = await rows.order_by("type_id").limit(payload.limit).offset(payload.offset).all()
    return OffsetPage[RelationshipType](
        items=types,
        total=total,
        limit=payload.limit,
        offset=payload.offset,
    )


async def op_relationship_types_create(
    payload: RelationshipTypeCreate,
    *,
    user: User,
    di: Di,
) -> RelationshipType:
    _ = user
    _ = di
    scope = _company_scope()
    rel_type = RelationshipType(
        company_id=scope.company_id,
        type_id=payload.type_id,
        name=payload.name,
        description=payload.description,
        prompt=payload.prompt,
        is_directed=payload.is_directed,
        inverse_type_id=payload.inverse_type_id,
        icon=payload.icon,
        color=payload.color,
        weight_default=payload.weight_default,
        is_system=False,
    )
    try:
        created = await RelationshipType.create(rel_type)
    except UniqueViolationError:
        raise_conflict(PlatformConflictError(f"Relationship type {payload.type_id} already exists"))
    return created


class CrmSuggestsListPayload(StrictBaseModel):
    namespace: str = Field(min_length=1)
    status: str | None = "pending"
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class CrmSuggestKeyPayload(StrictBaseModel):
    namespace: str = Field(min_length=1)
    suggest_id: str = Field(min_length=1)


async def op_suggests_list(
    payload: CrmSuggestsListPayload,
    *,
    user: User,
    di: Di,
) -> OffsetPage[CRMSuggest]:
    _ = user
    _ = _company_scope()
    return await di.suggest_service.list_suggests(
        payload.namespace, payload.status, payload.limit, payload.offset
    )


async def op_suggests_resolve(
    payload: CrmSuggestKeyPayload,
    *,
    user: User,
    di: Di,
) -> CRMSuggest:
    _ = user
    _ = _company_scope()
    try:
        return await di.suggest_service.resolve_suggest(
            payload.suggest_id, namespace=payload.namespace
        )
    except ValueError as exc:
        raise_invalid(exc)


async def op_suggests_dismiss(
    payload: CrmSuggestKeyPayload,
    *,
    user: User,
    di: Di,
) -> CRMSuggest:
    _ = user
    _ = _company_scope()
    try:
        return await di.suggest_service.dismiss_suggest(
            payload.suggest_id, namespace=payload.namespace
        )
    except ValueError as exc:
        raise_invalid(exc)


class CrmAccessRequestIdPayload(StrictBaseModel):
    access_request_id: str = Field(min_length=1)


class CrmAccessRequestUpdatePayload(AccessRequestUpdate):
    access_request_id: str = Field(min_length=1)


class CrmAccessRequestListPayload(StrictBaseModel):
    status: str | None = None
    limit: int = Field(default=100, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


async def op_access_requests_create(
    payload: AccessRequestCreate,
    *,
    user: User,
    di: Di,
) -> AccessRequestResponse:
    scope = _company_scope()
    _ = user
    try:
        row = await di.access_request_service.create_access_request(
            entity_id=payload.resource_id,
            requester_user_id=scope.user_id,
            requester_company_id=scope.company_id,
            message=payload.message,
            include_dependencies=payload.include_dependencies,
            max_depth=payload.max_depth,
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except AuthzDenied as exc:
        raise_forbidden(exc)
    return AccessRequestResponse.model_validate(row)


async def op_access_requests_item(
    payload: CrmAccessRequestIdPayload,
    *,
    user: User,
    di: Di,
) -> AccessRequestResponse:
    _ = user
    _ = di
    _ = _company_scope()
    row = await AccessRequest.get(payload.access_request_id)
    if row is None:
        raise_not_found(PlatformNotFoundError("Request not found"))
    return AccessRequestResponse.model_validate(row)


async def op_access_requests_update(
    payload: CrmAccessRequestUpdatePayload,
    *,
    user: User,
    di: Di,
) -> AccessRequestResponse:
    scope = _company_scope()
    _ = user
    try:
        if payload.status == AccessRequestStatus.APPROVED:
            row = await di.access_request_service.approve_access_request(
                payload.access_request_id, scope.user_id
            )
        elif payload.status == AccessRequestStatus.REJECTED:
            row = await di.access_request_service.reject_access_request(
                payload.access_request_id, scope.user_id
            )
        else:
            raise_invalid(ValueError("Invalid status"))
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformConflictError as exc:
        raise_conflict(exc)
    except AuthzDenied as exc:
        raise_forbidden(exc)
    return AccessRequestResponse.model_validate(row)


async def op_access_requests_list(
    payload: CrmAccessRequestListPayload,
    *,
    user: User,
    di: Di,
) -> OffsetPage[AccessRequestResponse]:
    _ = user
    scope = _company_scope()
    rows, total = await asyncio.gather(
        di.access_request_service.list_access_requests(
            company_id=scope.company_id,
            status=payload.status,
            limit=payload.limit,
            offset=payload.offset,
        ),
        di.access_request_service.count_access_requests(
            company_id=scope.company_id, status=payload.status
        ),
    )
    return OffsetPage[AccessRequestResponse](
        items=[AccessRequestResponse.model_validate(row) for row in rows],
        total=total,
        limit=payload.limit,
        offset=payload.offset,
    )


class CrmLaraSummaryPayload(StrictBaseModel):
    namespace: str = Field(min_length=1)


async def op_entities_daily_summary(
    payload: DailySummaryRequest,
    *,
    user: User,
    di: Di,
) -> JsonObject:
    _ = user
    _ = _company_scope()
    return await di.entity_service.get_daily_summary_cached(
        date_str=payload.date,
        namespace=payload.namespace,
        force_rebuild=payload.force_rebuild,
    )


async def op_entities_period_summary(
    payload: PeriodSummaryRequest,
    *,
    user: User,
    di: Di,
) -> JsonObject:
    scope = _company_scope()
    _ = user
    summary = await di.entity_service.get_period_summary_cached(
        date_from=payload.date_from,
        date_to=payload.date_to,
        namespace=payload.namespace,
        force_rebuild=payload.force_rebuild,
    )
    if summary.get("period_truncated") is not True:
        return summary
    max_d_raw = summary.get("period_summary_max_days")
    req_d_raw = summary.get("requested_period_days")
    if not isinstance(max_d_raw, int) or not isinstance(req_d_raw, int):
        raise RuntimeError("Invalid period summary truncation metadata")
    await notify_user(
        user_id=scope.user_id,
        notification=Notification(
            type=NotificationType.SYSTEM,
            title=t("crm.notifications.period_summary_range_clamped_title"),
            title_i18n_key="crm:notifications.period_summary_range_clamped_title",
            message=t(
                "crm.notifications.period_summary_range_clamped_message",
                max_days=max_d_raw,
                requested_days=req_d_raw,
            ),
            message_i18n_key="crm:notifications.period_summary_range_clamped_message",
            message_i18n_vars={
                "max_days": max_d_raw,
                "requested_days": req_d_raw,
            },
            service="crm",
            data={
                "event": "crm/period_summary/range_clamped",
                "requested_date_from": summary["requested_date_from"],
                "requested_date_to": summary["requested_date_to"],
                "effective_date_from": summary["date_from"],
                "effective_date_to": summary["date_to"],
                "period_summary_max_days": max_d_raw,
                "requested_period_days": req_d_raw,
                "max_days": max_d_raw,
                "requested_days": req_d_raw,
            },
        ),
    )
    return summary


async def op_namespaces_lara_summary(
    payload: CrmLaraSummaryPayload,
    *,
    user: User,
    di: Di,
) -> LaraNamespaceSummaryResponse:
    _ = user
    _ = _company_scope()
    try:
        return await di.lara_namespace_service.get_summary(payload.namespace)
    except ValueError as exc:
        raise_invalid(exc)


async def op_tasks_daily_summary_start(
    payload: StartDailySummaryRequest,
    *,
    user: User,
    di: Di,
) -> CRMTask:
    _ = user
    _ = _company_scope()
    try:
        row = await di.task_service.start_daily_summary(
            namespace=payload.namespace,
            date_str=payload.date_str,
            reason=payload.reason,
        )
    except ActiveTaskExistsError as exc:
        raise_conflict(exc)
    except ValueError as exc:
        raise_invalid(exc)
    return CRMTask.model_validate(row)


async def op_tasks_period_summary_start(
    payload: StartPeriodSummaryRequest,
    *,
    user: User,
    di: Di,
) -> CRMTask:
    _ = user
    _ = _company_scope()
    try:
        row = await di.task_service.start_period_summary(
            namespace=payload.namespace,
            date_from=payload.date_from,
            date_to=payload.date_to,
            reason=payload.reason,
        )
    except ActiveTaskExistsError as exc:
        raise_conflict(exc)
    except ValueError as exc:
        raise_invalid(exc)
    return CRMTask.model_validate(row)


class CrmTaskIdPayload(StrictBaseModel):
    task_id: str = Field(min_length=1)


class CrmTasksListPayload(StrictBaseModel):
    namespace: str | None = None
    task_type: str | None = None
    note_id: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


async def op_tasks_list(
    payload: CrmTasksListPayload,
    *,
    user: User,
    di: Di,
) -> OffsetPage[CRMTask]:
    _ = user
    _ = _company_scope()
    rows, total = await asyncio.gather(
        di.task_service.list_tasks(
            payload.namespace,
            task_type=payload.task_type,
            note_id=payload.note_id,
            limit=payload.limit,
            offset=payload.offset,
        ),
        di.task_service.count_tasks(
            payload.namespace, task_type=payload.task_type, note_id=payload.note_id
        ),
    )
    return OffsetPage[CRMTask](
        items=[CRMTask.model_validate(row) for row in rows],
        total=total,
        limit=payload.limit,
        offset=payload.offset,
    )


async def op_tasks_item(
    payload: CrmTaskIdPayload,
    *,
    user: User,
    di: Di,
) -> CRMTask:
    _ = user
    scope = _company_scope()
    row = await di.task_service.get_task(payload.task_id)
    try:
        if row is None:
            await di.authz_service.require_can_view(
                AuthzObject.company(scope.company_id), user_id=scope.user_id
            )
            raise_not_found(PlatformNotFoundError("task not found"))
        await di.authz_service.require_can_view(
            AuthzObject.crm_namespace(scope.company_id, row.namespace),
            user_id=scope.user_id,
        )
    except AuthzDenied as exc:
        raise_forbidden(exc)
    return CRMTask.model_validate(row)


async def op_tasks_created_entities(
    payload: CrmTaskIdPayload,
    *,
    user: User,
    di: Di,
) -> TaskCreatedEntitiesResponse:
    _ = user
    _ = _company_scope()
    try:
        return await di.task_service.get_task_created_entities(payload.task_id)
    except LookupError:
        raise_not_found(PlatformNotFoundError("task not found"))
    except ValueError as exc:
        raise_invalid(exc)


async def op_tasks_knowledge_import_start(
    payload: StartKnowledgeImportRequest,
    *,
    user: User,
    di: Di,
) -> CRMTask:
    _ = user
    scope = _company_scope()
    try:
        await di.authz_service.require_can_edit(
            AuthzObject.crm_namespace(scope.company_id, payload.namespace.strip()),
            user_id=scope.user_id,
        )
        row = await di.task_service.start_knowledge_import(
            namespace=payload.namespace,
            mode=payload.mode,
            source_file_ids=payload.source_file_ids,
            source_text=payload.source_text,
            extract_entity_types=payload.extract_entity_types,
            split_by_headings=payload.split_by_headings,
            chunk_max_chars=payload.chunk_max_chars,
        )
    except AuthzDenied as exc:
        raise_forbidden(exc)
    except ActiveTaskExistsError as exc:
        raise_conflict(exc)
    except ValueError as exc:
        raise_invalid(exc)
    return CRMTask.model_validate(row)


async def op_tasks_review_complete(
    payload: CrmTaskIdPayload,
    *,
    user: User,
    di: Di,
) -> CRMTask:
    _ = user
    _ = _company_scope()
    try:
        row = await di.task_service.complete_task_review(payload.task_id)
    except LookupError:
        raise_not_found(PlatformNotFoundError("task not found"))
    except ValueError as exc:
        raise_invalid(exc)
    return CRMTask.model_validate(row)


async def op_tasks_cancel(
    payload: CrmTaskIdPayload,
    *,
    user: User,
    di: Di,
) -> CRMTask:
    _ = user
    _ = _company_scope()
    try:
        row = await di.task_service.request_cancel(payload.task_id)
    except ValueError as exc:
        _raise_service_error(exc)
    return CRMTask.model_validate(row)


async def op_tasks_rollback(
    payload: CrmTaskIdPayload,
    *,
    user: User,
    di: Di,
) -> CRMTask:
    _ = user
    _ = _company_scope()
    try:
        row = await di.task_service.rollback_task(payload.task_id)
    except ValueError as exc:
        _raise_service_error(exc)
    return CRMTask.model_validate(row)


async def op_tasks_retry(
    payload: CrmTaskIdPayload,
    *,
    user: User,
    di: Di,
) -> CRMTask:
    _ = user
    _ = _company_scope()
    try:
        row = await di.task_service.retry_task(payload.task_id)
    except LookupError:
        raise_not_found(PlatformNotFoundError("task not found"))
    except ActiveTaskExistsError as exc:
        raise_conflict(exc)
    except ValueError as exc:
        raise_invalid(exc)
    return CRMTask.model_validate(row)


class CrmActivityTasksListPayload(WorktrackerModel):
    namespace: str | None = None
    state: WorkItemState | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


async def op_activity_tasks_create(
    payload: ActivityTaskCreateRequest,
    *,
    user: User,
    di: Di,
) -> ActivityTaskResponse:
    _ = user
    scope = _company_scope()
    try:
        entity = await di.entity_service.create_entity(
            entity_type="task",
            name=payload.title,
            description=payload.description,
            entity_subtype=payload.entity_subtype,
            tags=payload.tags,
            namespace=payload.namespace,
            user_id=scope.user_id,
            priority=payload.priority,
            due_date=payload.due_date,
            assignees=payload.assignees,
        )
    except SchemaValidationError as exc:
        raise_invalid(exc)
    except ValueError as exc:
        _raise_service_error(exc)
    work_item = await di.crm_work_item_service.get_for_task(
        company_id=entity.company_id,
        entity_id=entity.entity_id,
    )
    if work_item is None:
        raise RuntimeError("Paired WorkItem was not created for the CRM task")
    return ActivityTaskResponse(
        entity=await build_entity_response(di, entity),
        work_item=work_item,
    )


async def op_activity_tasks_list(
    payload: CrmActivityTasksListPayload,
    *,
    user: User,
    di: Di,
) -> OffsetPage[WorkItem]:
    _ = user
    scope = _company_scope()
    items = await di.crm_work_item_service.list_crm_activity_work_items(
        company_id=scope.company_id,
        namespace=payload.namespace,
        state=payload.state,
        limit=payload.limit,
        offset=payload.offset,
    )
    total = await WorkItem.count_work_items(
        scope.company_id,
        namespace=payload.namespace,
        kind=WorkItemKind.CRM_ACTIVITY,
        state=payload.state,
    )
    return OffsetPage[WorkItem](
        items=items,
        total=total,
        limit=payload.limit,
        offset=payload.offset,
    )


class CrmAttachmentsAttachPayload(StrictBaseModel):
    entity_id: str = Field(min_length=1)
    file_id: str = Field(min_length=1)


class CrmAttachmentsRemovePayload(StrictBaseModel):
    entity_id: str = Field(min_length=1)
    attachment_id: str = Field(min_length=1)


async def op_attachments_list(
    payload: CrmEntityIdPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[EntityAttachment]:
    _ = user
    _ = _company_scope()
    try:
        rows = await di.attachment_service.get_attachments(entity_id=payload.entity_id)
    except ValueError as exc:
        _raise_service_error(exc)
    return ListResponse[EntityAttachment](
        items=[EntityAttachment.model_validate(row) for row in rows]
    )


async def op_attachments_attach(
    payload: CrmAttachmentsAttachPayload,
    *,
    user: User,
    di: Di,
) -> AttachmentAttachResponse:
    _ = user
    _ = _company_scope()
    try:
        row = await di.attachment_service.add_attachment(
            entity_id=payload.entity_id,
            file_id=payload.file_id,
        )
    except ValueError as exc:
        _raise_service_error(exc)
    return AttachmentAttachResponse.model_validate(row)


async def op_attachments_remove(
    payload: CrmAttachmentsRemovePayload,
    *,
    user: User,
    di: Di,
) -> None:
    _ = user
    _ = _company_scope()
    try:
        await di.attachment_service.remove_attachment(
            entity_id=payload.entity_id,
            document_id=payload.attachment_id,
        )
    except LookupError as exc:
        raise_not_found(exc)
    except ValueError as exc:
        _raise_service_error(exc)


class CrmIntegrationNamespacePayload(StrictBaseModel):
    namespace_name: str = Field(min_length=1)


class CrmIntegrationProviderPayload(StrictBaseModel):
    namespace_name: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)


class CrmIntegrationAuthorizePayload(StrictBaseModel):
    namespace_name: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    subdomain: str = Field(min_length=1)
    return_path: str = Field(min_length=1)
    return_origin: str | None = None
    accept_language: str | None = None
    language_cookie: str | None = None
    brand_host: str | None = None


class CrmIntegrationAutoSyncPayload(IntegrationAutoSyncUpdateRequest):
    namespace_name: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)


class CrmIntegrationAutoNoteAiPayload(AutoNoteAiAnalyzeUpdateRequest):
    namespace_name: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)


def _optional_header_value(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if stripped == "":
        raise_invalid(ValueError(f"{field} must not be blank"))
    return stripped


async def _require_integration_namespace(
    di: Di,
    scope: CompanyScope,
    namespace_name: str,
) -> Namespace:
    ns = await di.namespace_service.get(namespace_name.strip())
    if ns is None or ns.company_id != scope.company_id:
        raise_not_found(PlatformNotFoundError("namespace not found"))
    return ns


def _integration_connector(
    di: Di, provider_id: str
) -> NamespaceIntegrationConnector:
    try:
        return di.integration_registry.get(provider_id.strip())
    except KeyError as exc:
        raise_invalid(exc)


async def _refreshed_manifest_item(
    di: Di,
    connector: NamespaceIntegrationConnector,
    *,
    namespace_name: str,
    company_id: str,
    user_id: str,
) -> IntegrationManifestItem:
    refreshed = await di.namespace_service.get(namespace_name)
    if refreshed is None:
        raise_not_found(PlatformNotFoundError("namespace not found"))
    return await connector.manifest_item(
        namespace_name=namespace_name,
        company_id=company_id,
        user_id=user_id,
        crm_settings=refreshed.crm_settings,
    )


async def op_namespace_integrations_list(
    payload: CrmIntegrationNamespacePayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[IntegrationManifestItem]:
    _ = user
    scope = _company_scope()
    ns = await _require_integration_namespace(di, scope, payload.namespace_name)
    items = await di.integration_registry.build_manifest(
        namespace_name=ns.name,
        company_id=scope.company_id,
        user_id=scope.user_id,
        crm_settings=ns.crm_settings,
    )
    return ListResponse[IntegrationManifestItem](items=items)


async def op_namespace_integrations_authorize(
    payload: CrmIntegrationAuthorizePayload,
    *,
    user: User,
    di: Di,
) -> IntegrationAuthorizeResponse:
    _ = user
    scope = _company_scope()
    _ = await _require_integration_namespace(di, scope, payload.namespace_name)
    connector = _integration_connector(di, payload.provider_id)
    if not payload.return_path.startswith("/") or payload.return_path.startswith("//"):
        raise_invalid(ValueError("return_path must be a single-segment path"))
    return_origin = _optional_header_value(payload.return_origin, "return_origin")
    brand_host = _optional_header_value(payload.brand_host, "brand_host")
    oauth_ui_locale = resolve_oauth_integration_locale(
        payload.accept_language,
        language_cookie=payload.language_cookie,
    )
    try:
        url = await connector.build_authorize_url(
            namespace_name=payload.namespace_name.strip(),
            subdomain=payload.subdomain,
            return_path=payload.return_path,
            company_id=scope.company_id,
            user_id=scope.user_id,
            return_origin=return_origin,
            oauth_ui_locale=oauth_ui_locale,
            brand_host=brand_host,
        )
    except ValueError as exc:
        raise_invalid(exc)
    return IntegrationAuthorizeResponse(authorize_url=url)


async def op_namespace_integrations_auto_sync(
    payload: CrmIntegrationAutoSyncPayload,
    *,
    user: User,
    di: Di,
) -> IntegrationManifestItem:
    _ = user
    scope = _company_scope()
    ns = await _require_integration_namespace(di, scope, payload.namespace_name)
    connector = _integration_connector(di, payload.provider_id)
    try:
        _ = await di.integration_auto_sync_service.apply_integration_auto_sync(
            company_id=scope.company_id,
            acting_user_id=scope.user_id,
            namespace_name=ns.name,
            provider_id=payload.provider_id.strip(),
            auto_sync_enabled=payload.auto_sync_enabled,
            auto_sync_cron=payload.auto_sync_cron,
            auto_sync_timezone=payload.auto_sync_timezone,
        )
    except ValueError as exc:
        _raise_service_error(exc)
    return await _refreshed_manifest_item(
        di,
        connector,
        namespace_name=ns.name,
        company_id=scope.company_id,
        user_id=scope.user_id,
    )


async def op_namespace_integrations_auto_note_ai(
    payload: CrmIntegrationAutoNoteAiPayload,
    *,
    user: User,
    di: Di,
) -> IntegrationManifestItem:
    _ = user
    scope = _company_scope()
    ns = await _require_integration_namespace(di, scope, payload.namespace_name)
    connector = _integration_connector(di, payload.provider_id)
    try:
        _ = await di.integration_auto_sync_service.apply_auto_note_ai_analyze(
            company_id=scope.company_id,
            namespace_name=ns.name,
            provider_id=payload.provider_id.strip(),
            auto_note_ai_analyze=payload.auto_note_ai_analyze,
        )
    except ValueError as exc:
        _raise_service_error(exc)
    return await _refreshed_manifest_item(
        di,
        connector,
        namespace_name=ns.name,
        company_id=scope.company_id,
        user_id=scope.user_id,
    )


async def op_namespace_integrations_sync(
    payload: CrmIntegrationProviderPayload,
    *,
    user: User,
    di: Di,
) -> CRMTask | IntegrationSyncStats:
    _ = user
    _ = _company_scope()
    connector = _integration_connector(di, payload.provider_id)
    ns = payload.namespace_name.strip()
    pid = payload.provider_id.strip()
    if connector.entities_sync_runs_in_worker():
        try:
            row = await di.task_service.start_namespace_integration_job(
                namespace=ns,
                provider_id=pid,
                job="entities",
            )
        except ActiveTaskExistsError as exc:
            raise_conflict(exc)
        except ValueError as exc:
            raise_invalid(exc)
        return CRMTask.model_validate(row)
    try:
        stats = await connector.sync_entities(ns)
    except ValueError as exc:
        raise_invalid(exc)
    return IntegrationSyncStats(items=stats)


async def op_namespace_integrations_custom_fields_sync(
    payload: CrmIntegrationProviderPayload,
    *,
    user: User,
    di: Di,
) -> CRMTask | IntegrationSyncStats:
    _ = user
    _ = _company_scope()
    connector = _integration_connector(di, payload.provider_id)
    ns = payload.namespace_name.strip()
    pid = payload.provider_id.strip()
    if connector.custom_fields_sync_runs_in_worker():
        try:
            row = await di.task_service.start_namespace_integration_job(
                namespace=ns,
                provider_id=pid,
                job="custom_fields",
            )
        except ActiveTaskExistsError as exc:
            raise_conflict(exc)
        except ValueError as exc:
            raise_invalid(exc)
        return CRMTask.model_validate(row)
    try:
        stats = await connector.sync_custom_field_catalog(ns)
    except ValueError as exc:
        raise_invalid(exc)
    return IntegrationSyncStats(items=stats)
