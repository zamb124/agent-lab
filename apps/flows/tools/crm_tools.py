"""CRM tools for flow employees / Lara via ServiceClient (same REST as CRM UI).

Require authenticated user context in the worker.
"""
from __future__ import annotations

import asyncio
import json
from datetime import date as Date
from typing import TYPE_CHECKING, ClassVar, Literal
from urllib.parse import quote, urlencode

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from apps.crm.models.api import (
    AIAnalysisDraftStored,
    DailySummaryRequest,
    EntityCreate,
    EntityMergeRequest,
    EntityMergeResponse,
    EntityResponse,
    EntitySearchFilterNode,
    EntitySearchQueryRequest,
    EntityTypeResponse,
    EntityUpdate,
    PeriodSummaryRequest,
    RelationshipCreate,
    RelationshipResponse,
    StartNoteAnalyzeRequest,
    TaskResponse,
)
from apps.flows.src.runtime_helpers.state_utils import push_ui_event
from apps.flows.src.services.platform_facades import get_lara_facade
from apps.flows.src.tools.decorator import tool
from core.clients.service_client import ServiceClient, ServiceClientError
from core.context import resolve_namespace_or_raise
from core.pagination import CursorPage, OffsetPage
from core.types import (
    JsonObject,
    JsonValue,
    parse_json_object,
    require_json_array,
    require_json_object,
)
from core.worktracker.models import WorkItem, WorkItemState

if TYPE_CHECKING:
    from core.state import ExecutionState


def _require_context_namespace() -> str:
    return resolve_namespace_or_raise()


def _compact_entity_hit(raw: EntityResponse) -> JsonObject:
    desc = raw.description
    if isinstance(desc, str) and len(desc) > 400:
        desc = desc[:400] + "…"
    return {
        "entity_id": raw.entity_id,
        "name": raw.name,
        "entity_type": raw.entity_type,
        "entity_subtype": raw.entity_subtype,
        "description": desc,
        "namespace": raw.namespace,
    }


class CrmSearchEntitiesArgs(BaseModel):
    """Аргументы POST /crm/api/v1/entities/query — та же семантика, что поле «Поиск» в UI."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("query", "search"),
        description=(
            "Текст семантического поиска (вектор по name/description), как в строке «Поиск» в списке сущностей: "
            "имена, фрагменты названий, ключевые слова; не пересказ всего диалога. Имя аргумента в вызове — query."
        ),
    )
    entity_type: str | None = Field(
        None,
        description="Только если пользователь явно ограничил тип сущности; иначе не передавай (null).",
    )
    entity_subtype: str | None = Field(
        None,
        description="Только при явном запросе подтипа; иначе null.",
    )
    namespace: str | None = Field(
        None,
        description="Пространство имён; null — берётся active_namespace из сессии CRM, не подставляй default сам.",
    )
    limit: int = Field(
        100,
        ge=1,
        le=1000,
        description="Максимум результатов (в UI часто 100).",
    )

    @field_validator("entity_type", "entity_subtype", "namespace", mode="before")
    @classmethod
    def _optional_str(cls, v: JsonValue) -> JsonValue:
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v


class CrmCreateNoteArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    mode: Literal["propose", "apply"] = Field(
        "propose",
        description="propose — подготовить создание заметки для подтверждения; apply — выполнить по pending_action_id.",
    )
    name: str | None = Field(None, description="Заголовок заметки (обязателен при mode=propose).")
    description: str | None = Field(None, description="Текст заметки (обязателен при mode=propose).")
    note_date: str | None = Field(
        None,
        description="Дата заметки YYYY-MM-DD; только если уместно по смыслу.",
    )
    namespace: str | None = Field(
        None,
        description="Пространство имён CRM; null — из контекста сессии.",
    )
    pending_action_id: str | None = Field(
        None,
        description="ID действия из propose. Обязателен для mode=apply.",
    )
    idempotency_key: str | None = Field(
        None,
        description="Идемпотентный ключ выполнения. Если не передан, используется pending_action_id.",
    )

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, v: JsonValue) -> JsonValue:
        if v is None:
            return None
        if isinstance(v, str):
            return v.strip() or None
        return v

    @field_validator("description", mode="before")
    @classmethod
    def _strip_description(cls, v: JsonValue) -> JsonValue:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s if s else None
        return v

    @model_validator(mode="after")
    def _mode_requirements(self) -> "CrmCreateNoteArgs":
        if self.mode == "apply":
            if self.pending_action_id is None or not str(self.pending_action_id).strip():
                raise ValueError("pending_action_id is required when mode='apply'")
            return self
        if self.name is None:
            raise ValueError("name is required when mode='propose'")
        if self.description is None:
            raise ValueError("description is required when mode='propose'")
        return self

    @field_validator("note_date", "namespace", "pending_action_id", mode="before")
    @classmethod
    def _optional_str_note(cls, v: JsonValue) -> JsonValue:
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v


class CrmAnalyzeNoteTextArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    note_id: str = Field(..., min_length=1, description="entity_id созданной или существующей заметки.")
    extract_entity_types: list[str] | None = Field(
        None,
        description="Ограничить извлечение указанными типами сущностей; иначе не передавай.",
    )
    mentioned_entity_ids: list[str] | None = Field(
        None,
        description="Уже известные id сущностей для контекста анализа; опционально.",
    )

    @field_validator("note_id", mode="before")
    @classmethod
    def _strip_note_id(cls, v: JsonValue) -> JsonValue:
        if isinstance(v, str):
            return v.strip() or None
        return v


class CrmCreateNoteAndAnalyzeArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, description="Заголовок новой заметки.")
    description: str = Field(..., min_length=1, description="Текст заметки; по нему же выполняется анализ.")
    note_date: str | None = Field(None, description="Дата YYYY-MM-DD; опционально.")
    extract_entity_types: list[str] | None = Field(
        None,
        description="Типы сущностей для извлечения при анализе; опционально.",
    )
    mentioned_entity_ids: list[str] | None = Field(
        None,
        description="Упомянутые id для контекста анализа; опционально.",
    )
    namespace: str | None = Field(None, description="Пространство имён; null — из контекста.")

    @field_validator("note_date", "namespace", mode="before")
    @classmethod
    def _optional_str_combo(cls, v: JsonValue) -> JsonValue:
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v


@tool(
    name="crm_search_entities",
    description=(
        "Гибридный поиск по сущностям CRM (полнотекст + семантика, как строка «Поиск» в списке сущностей). "
        "Не добавляй фильтры по типу или пространству, если пользователь об этом не просил. "
        "Ответ — JSON: успех, список совпадений и блоки для чата."
    ),
    tags=["crm"],
    parameters_model=CrmSearchEntitiesArgs,
)
async def crm_search_entities(
    query: str | None = None,
    search: str | None = None,
    entity_type: str | None = None,
    entity_subtype: str | None = None,
    namespace: str | None = None,
    limit: int = 100,
    *,
    state: "ExecutionState",
) -> str:
    _ = state
    q = (query or "").strip() if query else ""
    if not q and search:
        q = str(search).strip()
    if not q:
        raise ValueError(
            "Нужен непустой параметр query — короткая строка семантического поиска (ключевые слова из запроса пользователя)."
        )
    ns = namespace if namespace else _require_context_namespace()
    request = EntitySearchQueryRequest(
        query=q,
        namespace=ns,
        search_mode="hybrid",
        limit=max(1, min(1000, int(limit))),
        entity_type=entity_type,
        entity_subtype=entity_subtype,
    )
    payload = require_json_object(
        request.model_dump(mode="json", exclude_none=True),
        "crm.entities.query.request",
    )

    client = ServiceClient()
    try:
        raw_response = await client.post("crm", "/crm/api/v1/entities/query", json=payload)
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)

    try:
        page = CursorPage[EntityResponse].model_validate(raw_response)
    except ValueError:
        return json.dumps({"success": False, "error": "CRM search: invalid response"}, ensure_ascii=False)

    hits = [_compact_entity_hit(item) for item in page.items]
    summary = f"Найдено сущностей: {len(hits)}."
    blocks: list[JsonObject] = [{"type": "text", "text": summary}]
    if hits:
        rows: list[JsonObject] = [
            {
                "entity_id": h.get("entity_id"),
                "name": h.get("name"),
                "type": h.get("entity_type"),
                "subtype": h.get("entity_subtype"),
            }
            for h in hits[:20]
        ]
        blocks.append(
            require_json_object(
                {
                    "type": "table",
                    "title": "Результаты поиска",
                    "columns": [
                        {"key": "name", "label": "Имя"},
                        {"key": "type", "label": "Тип"},
                        {"key": "entity_id", "label": "ID"},
                    ],
                    "rows": rows,
                },
                "crm.search_entities.table_block",
            )
        )

    return json.dumps(
        {"success": True, "hits": hits, "blocks": blocks},
        ensure_ascii=False,
    )


@tool(
    name="crm_create_note",
    description=(
        "Создаёт заметку в CRM NetWorkle. Передай name (заголовок), description (текст). "
        "note_date — ISO дата YYYY-MM-DD (опционально). namespace — опционально, иначе берётся из контекста. "
        "Возвращает JSON: entity, blocks (карточка для чата)."
    ),
    tags=["crm"],
    parameters_model=CrmCreateNoteArgs,
)
async def crm_create_note(
    name: str | None = None,
    description: str | None = None,
    note_date: str | None = None,
    namespace: str | None = None,
    mode: Literal["propose", "apply"] = "propose",
    pending_action_id: str | None = None,
    idempotency_key: str | None = None,
    *,
    state: "ExecutionState",
) -> str:
    ns = namespace if namespace and str(namespace).strip() else _require_context_namespace()
    facade = get_lara_facade()
    clean_note_date = str(note_date).strip() if note_date and str(note_date).strip() else None

    if mode == "propose":
        if name is None or description is None:
            raise ValueError("name and description are required for mode=propose")
        action = await facade.preview_crm_create_note(
            name=name.strip(),
            description=description,
            note_date=clean_note_date,
            namespace=ns,
            state=state,
            idempotency_key=idempotency_key,
        )
        action_payload = require_json_object(
            action.model_dump(mode="json"),
            "crm.note.preview.action",
        )
        action_button = {
            "action_id": "crm.note.create.apply",
            "action_kind": "apply",
            "label": "Создать заметку",
            "pending_action_id": action.pending_action_id,
            "arguments": {"pending_action_id": action.pending_action_id},
            "context": {"capability": "crm.note", "operation": "create"},
        }
        preview_blocks = [
            {"type": "text", "text": "Черновик создания заметки готов. Подтвердите применение."},
            {"type": "actions", "buttons": [action_button]},
        ]
        _ = push_ui_event(
            state,
            event_type="action_previewed",
            payload={
                "action": action_payload,
                "capability": "crm.note",
                "operation": "create",
                "blocks": preview_blocks,
            },
            event_id=f"crm-note-preview-{action.pending_action_id}",
            version="1.0.0",
        )
        return json.dumps(
            {
                "success": True,
                "mode": "propose",
                "pending_action_id": action.pending_action_id,
                "action": action_payload,
                "blocks": preview_blocks,
            },
            ensure_ascii=False,
        )

    if not pending_action_id:
        raise ValueError("pending_action_id is required for mode=apply")
    action = await facade.apply_crm_create_note(
        pending_action_id=pending_action_id,
        state=state,
        idempotency_key=idempotency_key,
    )
    action_payload = require_json_object(
        action.model_dump(mode="json"),
        "crm.note.apply.action",
    )
    result_payload = action.result
    if result_payload is None:
        raise ValueError("Invalid apply result payload")
    entity = result_payload.get("entity")
    if not isinstance(entity, dict):
        raise ValueError("CRM create note: invalid response")
    entity_response = EntityResponse.model_validate(entity)
    entity_payload = require_json_object(
        entity_response.model_dump(mode="json"),
        "crm.note.apply.entity",
    )
    eid = entity_response.entity_id
    open_entity_button = {
        "action_id": "crm.entity.open",
        "action_kind": "open_entity",
        "label": "Открыть сущность",
        "arguments": {"entity_id": eid},
        "context": {"entity_id": eid, "entity_type": "note"},
    }
    result = {
        "success": True,
        "mode": "apply",
        "pending_action_id": pending_action_id,
        "entity_id": eid,
        "entity": entity_payload,
        "blocks": [
            {
                "type": "card",
                "title": entity_response.name or "Note",
                "subtitle": eid,
            },
            {"type": "actions", "buttons": [open_entity_button]},
        ],
    }
    _ = push_ui_event(
        state,
        event_type="action_applied",
        payload={
            "action": action_payload,
            "capability": "crm.note",
            "operation": "create",
            "entity_id": eid,
            "blocks": [{"type": "actions", "buttons": [open_entity_button]}],
        },
        event_id=f"crm-note-apply-{pending_action_id}",
        version="1.0.0",
    )
    return json.dumps(result, ensure_ascii=False)


@tool(
    name="crm_create_note_and_analyze",
    description=(
        "Создаёт заметку в CRM и сразу запускает AI-анализ того же текста (извлечение сущностей). "
        "Передай name, description. Опционально note_date (YYYY-MM-DD), extract_entity_types, mentioned_entity_ids, namespace."
    ),
    tags=["crm"],
    parameters_model=CrmCreateNoteAndAnalyzeArgs,
)
async def crm_create_note_and_analyze(
    name: str,
    description: str,
    note_date: str | None = None,
    extract_entity_types: list[str] | None = None,
    mentioned_entity_ids: list[str] | None = None,
    namespace: str | None = None,
    *,
    state: "ExecutionState",
) -> str:
    ns = namespace if namespace and str(namespace).strip() else _require_context_namespace()
    entity_create = EntityCreate(
        entity_type="note",
        namespace=ns,
        name=name.strip(),
        description=description,
        note_date=Date.fromisoformat(str(note_date).strip())
        if note_date and str(note_date).strip()
        else None,
    )
    create_payload = require_json_object(
        entity_create.model_dump(mode="json", exclude_none=True),
        "crm.note.create_and_analyze.create_payload",
    )
    client = ServiceClient()
    created = EntityResponse.model_validate(
        await client.post("crm", "/crm/api/v1/entities", json=create_payload)
    )
    created_payload = require_json_object(
        created.model_dump(mode="json"),
        "crm.note.create_and_analyze.created",
    )
    eid = created.entity_id

    analyze_args: JsonObject = {"note_id": eid}
    if extract_entity_types:
        analyze_args["extract_entity_types"] = require_json_array(
            extract_entity_types,
            "crm.note.create_and_analyze.extract_entity_types",
        )
    if mentioned_entity_ids:
        analyze_args["mentioned_entity_ids"] = require_json_array(
            mentioned_entity_ids,
            "crm.note.create_and_analyze.mentioned_entity_ids",
        )

    analyzed_raw = await crm_analyze_note_text.run(analyze_args, state)
    if not isinstance(analyzed_raw, str):
        raise ValueError("create_note: analyze tool result must be a JSON string")
    analyzed = parse_json_object(analyzed_raw, "crm_analyze_note_text.result")
    if not analyzed.get("success"):
        return json.dumps(
            {
                "success": False,
                "error": analyzed.get("error", "analyze failed"),
                "entity_id": eid,
                "create": created_payload,
                "analyze": analyzed,
            },
            ensure_ascii=False,
        )

    blocks_out: list[JsonObject] = []
    analyzed_blocks = analyzed.get("blocks")
    if isinstance(analyzed_blocks, list):
        for block in analyzed_blocks:
            if isinstance(block, dict):
                blocks_out.append(require_json_object(block, "crm_analyze_note_text.blocks[]"))

    return json.dumps(
        {
            "success": True,
            "entity_id": eid,
            "entity": created_payload,
            "analyze": analyzed.get("analyze"),
            "blocks": blocks_out,
        },
        ensure_ascii=False,
    )


@tool(
    name="crm_analyze_note_text",
    description=(
        "Запускает AI-анализ заметки (mode=analyze): пишет ai_analysis_draft, "
        "не применяет изменения в граф. Обязательно: note_id. "
        "После согласия пользователя — crm_apply_analysis_draft или crm_discard_analysis_draft. "
        "Не вызывать без явного согласия на анализ."
    ),
    tags=["crm"],
    parameters_model=CrmAnalyzeNoteTextArgs,
)
async def crm_analyze_note_text(
    note_id: str,
    extract_entity_types: list[str] | None = None,
    mentioned_entity_ids: list[str] | None = None,
    *,
    state: "ExecutionState",
) -> str:
    _ = state
    nid = str(note_id).strip()
    request = StartNoteAnalyzeRequest(
        note_id=nid,
        mode="analyze",
        include_attachments=True,
        check_duplicates=True,
        extract_entity_types=extract_entity_types,
        mentioned_entity_ids=mentioned_entity_ids,
    )
    body = require_json_object(
        request.model_dump(mode="json", exclude_none=True),
        "crm.note_analyze.request",
    )

    client = ServiceClient()
    try:
        start = TaskResponse.model_validate(
            await client.post(
                "crm",
                "/crm/api/v1/tasks/note-analyze",
                json=body,
                timeout=60.0,
            )
        )
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)

    return await _poll_note_analyze_task(
        client=client,
        task_id=start.task_id.strip(),
        note_id=nid,
        mode="analyze",
    )


class CrmGetEntityArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    entity_id: str = Field(..., min_length=1, description="entity_id CRM.")


class CrmCreateEntityArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    entity_type: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    entity_subtype: str | None = None
    namespace: str | None = None
    description: str | None = None
    attributes: JsonObject | None = None
    tags: list[str] | None = None


class CrmCreateRelationshipArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_entity_id: str = Field(..., min_length=1)
    target_entity_id: str = Field(..., min_length=1)
    relationship_type: str = Field(..., min_length=1)
    namespace: str | None = None
    weight: float = Field(default=1.0, ge=0.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class CrmListEntityTypesArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    namespace: str | None = None


class CrmDailySummaryArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    date: str = Field(..., min_length=10, max_length=10, description="YYYY-MM-DD.")
    namespace: str | None = None
    force_rebuild: bool = False


@tool(
    name="crm_get_entity",
    description=(
        "Загружает сущность CRM по entity_id (GET /crm/api/v1/entities/{id}). "
        "Возвращает JSON и card-блок для чата."
    ),
    tags=["crm"],
    parameters_model=CrmGetEntityArgs,
)
async def crm_get_entity(entity_id: str, *, state: "ExecutionState") -> str:
    _ = state
    cid = entity_id.strip()
    if not cid:
        raise ValueError("entity_id is required")
    client = ServiceClient()
    try:
        raw = await client.get("crm", f"/crm/api/v1/entities/{quote(cid, safe='')}")
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    try:
        entity = EntityResponse.model_validate(raw)
    except ValueError:
        return json.dumps({"success": False, "error": "crm_get_entity: invalid response"}, ensure_ascii=False)
    entity_payload = require_json_object(entity.model_dump(mode="json"), "crm.get_entity.entity")
    blocks: list[JsonObject] = [
        {
            "type": "card",
            "title": entity.name or cid,
            "subtitle": entity.entity_type,
        },
    ]
    return json.dumps({"success": True, "entity": entity_payload, "blocks": blocks}, ensure_ascii=False)


@tool(
    name="crm_create_entity",
    description=(
        "Создаёт сущность CRM (POST /crm/api/v1/entities): entity_type и name обязательны. "
        "namespace берётся из active_namespace если не указан. Для confirm-first заметок используй crm_create_note."
    ),
    tags=["crm"],
    parameters_model=CrmCreateEntityArgs,
)
async def crm_create_entity(
    entity_type: str,
    name: str,
    entity_subtype: str | None = None,
    namespace: str | None = None,
    description: str | None = None,
    attributes: JsonObject | None = None,
    tags: list[str] | None = None,
    *,
    state: "ExecutionState",
) -> str:
    _ = state
    ns = namespace if namespace and str(namespace).strip() else _require_context_namespace()
    entity_create = EntityCreate(
        entity_type=entity_type.strip(),
        name=name.strip(),
        entity_subtype=entity_subtype.strip() if entity_subtype and str(entity_subtype).strip() else None,
        namespace=ns,
        description=description.strip() if description and str(description).strip() else None,
        attributes=attributes,
        tags=tags,
    )
    body = require_json_object(
        entity_create.model_dump(mode="json", exclude_none=True),
        "crm.create_entity.body",
    )
    client = ServiceClient()
    try:
        created = EntityResponse.model_validate(
            await client.post("crm", "/crm/api/v1/entities", json=body)
        )
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    created_payload = require_json_object(created.model_dump(mode="json"), "crm.create_entity.response")
    blocks: list[JsonObject] = [
        {"type": "card", "title": created.name or "Entity", "subtitle": created.entity_id}
    ]
    return json.dumps({"success": True, "entity": created_payload, "blocks": blocks}, ensure_ascii=False)


@tool(
    name="crm_create_relationship",
    description=(
        "Создаёт связь (POST /crm/api/v1/relationships между source и target)."
    ),
    tags=["crm"],
    parameters_model=CrmCreateRelationshipArgs,
)
async def crm_create_relationship(
    source_entity_id: str,
    target_entity_id: str,
    relationship_type: str,
    namespace: str | None = None,
    weight: float = 1.0,
    confidence: float = 1.0,
    *,
    state: "ExecutionState",
) -> str:
    _ = state
    ns = namespace if namespace and str(namespace).strip() else _require_context_namespace()
    relationship_create = RelationshipCreate(
        source_entity_id=source_entity_id.strip(),
        target_entity_id=target_entity_id.strip(),
        relationship_type=relationship_type.strip(),
        namespace=ns,
        weight=weight,
        confidence=confidence,
    )
    payload_obj = require_json_object(
        relationship_create.model_dump(mode="json", exclude_none=True),
        "crm.create_relationship.body",
    )
    client = ServiceClient()
    try:
        relationship = RelationshipResponse.model_validate(
            await client.post("crm", "/crm/api/v1/relationships", json=payload_obj)
        )
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    relationship_payload = require_json_object(
        relationship.model_dump(mode="json"),
        "crm.create_relationship.response",
    )
    bid = relationship.relationship_id
    txt = (
        f"Связь {relationship_type.strip()} создана ({bid}): "
        f"{relationship.source_entity_id} → {relationship.target_entity_id}."
    )
    blocks: list[JsonObject] = [{"type": "text", "text": txt}]
    return json.dumps(
        {"success": True, "relationship": relationship_payload, "blocks": blocks},
        ensure_ascii=False,
    )


@tool(
    name="crm_list_entity_types",
    description=("Каталог типов для namespace (GET /crm/api/v1/entity-types?namespace=)."),
    tags=["crm"],
    parameters_model=CrmListEntityTypesArgs,
)
async def crm_list_entity_types(
    namespace: str | None = None,
    *,
    state: "ExecutionState",
) -> str:
    _ = state
    ns = namespace if namespace and str(namespace).strip() else _require_context_namespace()
    client = ServiceClient()
    qp = quote(ns, safe="")
    path = f"/crm/api/v1/entity-types?namespace={qp}"
    try:
        raw = await client.get("crm", path)
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    try:
        page = OffsetPage[EntityTypeResponse].model_validate(raw)
    except ValueError:
        return json.dumps({"success": False, "error": "crm_list_entity_types: invalid response envelope"}, ensure_ascii=False)
    compact = [
        {"type_id": item.type_id, "name": item.name, "parent_type_id": item.parent_type_id}
        for item in page.items
    ]
    lines = compact[:80]
    blocks: list[JsonObject] = [
        require_json_object(
            {
                "type": "table",
                "title": "Типы сущностей",
                "columns": [
                    {"key": "type_id", "label": "type_id"},
                    {"key": "name", "label": "Имя"},
                    {"key": "parent_type_id", "label": "Родитель"},
                ],
                "rows": lines,
            },
            "crm.list_entity_types.table_block",
        )
    ]
    return json.dumps(
        {"success": True, "namespace": ns, "count": len(compact), "items": compact, "blocks": blocks},
        ensure_ascii=False,
    )


@tool(
    name="crm_daily_summary",
    description=(
        "Сводка заметок за один день "
        "(POST /crm/api/v1/entities/daily-summary, date YYYY-MM-DD). "
        "Для диапазона дат — crm_period_summary."
    ),
    tags=["crm"],
    parameters_model=CrmDailySummaryArgs,
)
async def crm_daily_summary(
    date: str,
    namespace: str | None = None,
    force_rebuild: bool = False,
    *,
    state: "ExecutionState",
) -> str:
    _ = state
    d_raw = date.strip()
    if not d_raw:
        raise ValueError("date is required")
    ns_clear = namespace if namespace and str(namespace).strip() else None
    request = DailySummaryRequest(
        date=d_raw,
        namespace=ns_clear,
        force_rebuild=bool(force_rebuild),
    )
    body = require_json_object(
        request.model_dump(mode="json", exclude_none=True),
        "crm.daily_summary.request",
    )
    client = ServiceClient()
    try:
        raw = await client.post("crm", "/crm/api/v1/entities/daily-summary", json=body)
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    if not isinstance(raw, dict):
        return json.dumps({"success": False, "error": "crm_daily_summary: invalid response"}, ensure_ascii=False)
    response = require_json_object(raw, "crm.daily_summary.response")
    summary_text = response.get("summary")
    if isinstance(summary_text, str) and summary_text.strip():
        main = summary_text.strip()
    else:
        main = json.dumps(response, ensure_ascii=False)[:2500]
    blocks: list[JsonObject] = [{"type": "text", "text": main}]
    return json.dumps({"success": True, "response": response, "blocks": blocks}, ensure_ascii=False)


class CrmUpdateEntityArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    entity_id: str = Field(..., min_length=1, description="entity_id from search/get. Never invent.")
    name: str | None = Field(default=None, description="New display name; omit to keep.")
    description: str | None = Field(default=None, description="New description; omit to keep.")
    status: str | None = Field(default=None, description="Entity status; omit to keep.")
    entity_type: str | None = Field(default=None, description="Change type only if user asked.")
    entity_subtype: str | None = Field(default=None, description="Change subtype only if user asked.")
    tags: list[str] | None = Field(default=None, description="Replace tags list when provided.")
    note_date: str | None = Field(
        default=None,
        description="For notes: YYYY-MM-DD note_date; omit to keep.",
    )


class CrmDeleteEntityArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    entity_id: str = Field(
        ...,
        min_length=1,
        description="entity_id to cascade-delete. Confirm with the user first. Never invent.",
    )


class CrmListNotesArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    date_from: str = Field(
        ...,
        min_length=10,
        max_length=10,
        description="Inclusive note_date start YYYY-MM-DD.",
    )
    date_to: str | None = Field(
        default=None,
        description="Inclusive note_date end YYYY-MM-DD; omit — same as date_from.",
    )
    namespace: str | None = Field(
        default=None,
        description="Namespace; null — active_namespace from session.",
    )
    query: str | None = Field(
        default=None,
        description="Optional text/semantic query over notes; omit for pure date listing.",
    )
    limit: int = Field(default=50, ge=1, le=1000)
    cursor: str | None = Field(default=None, description="Opaque next_cursor.")


class CrmApplyAnalysisDraftArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    note_id: str = Field(
        ...,
        min_length=1,
        description="note_id / entity_id of the note with ai_analysis_draft. Never invent.",
    )


class CrmDiscardAnalysisDraftArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    note_id: str = Field(
        ...,
        min_length=1,
        description="note_id whose analysis draft to discard. Never invent.",
    )


class CrmMergeEntitiesArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    survivor_entity_id: str = Field(
        ...,
        min_length=1,
        description="entity_id that remains after merge.",
    )
    source_entity_id: str = Field(
        ...,
        min_length=1,
        description="entity_id that is merged into survivor and deleted.",
    )


class CrmPeriodSummaryArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    date_from: str = Field(..., min_length=10, max_length=10, description="Period start YYYY-MM-DD.")
    date_to: str = Field(..., min_length=10, max_length=10, description="Period end YYYY-MM-DD.")
    namespace: str | None = Field(default=None, description="Namespace; null — session.")
    force_rebuild: bool = False


class CrmCreateActivityTaskArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(..., min_length=1, description="Task title (CRM entity name).")
    description: str | None = Field(default=None, description="Optional task description.")
    namespace: str | None = Field(
        default=None,
        description="Namespace; null — active_namespace.",
    )
    entity_subtype: str | None = Field(default=None, description="Optional task subtype.")
    priority: str | None = Field(
        default=None,
        description="WorkItem priority (low/normal/high/urgent) when creating the pair.",
    )
    due_date: str | None = Field(default=None, description="Optional due_date YYYY-MM-DD.")
    assignees: list[str] | None = Field(
        default=None,
        description="user_id assignees from team_resolve_user / team_list_members. Never invent.",
    )
    tags: list[str] | None = Field(default=None, description="Optional tags.")


class CrmListActivityTasksArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    namespace: str | None = Field(default=None, description="Namespace filter; null — all company.")
    work_item_state: str | None = Field(
        default=None,
        description="WorkItemState filter: open/in_progress/blocked/done/cancelled/failed.",
    )
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


async def _poll_note_analyze_task(
    *,
    client: ServiceClient,
    task_id: str,
    note_id: str,
    mode: Literal["analyze", "apply"],
) -> str:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 120.0
    terminal: TaskResponse | None = None
    while loop.time() < deadline:
        try:
            row = TaskResponse.model_validate(
                await client.get(
                    "crm",
                    f"/crm/api/v1/tasks/{quote(task_id, safe='')}",
                    timeout=30.0,
                )
            )
        except ServiceClientError as exc:
            return json.dumps(
                {"success": False, "error": str(exc), "task_id": task_id},
                ensure_ascii=False,
            )
        terminal = row
        if row.status in ("completed", "failed", "cancelled"):
            break
        await asyncio.sleep(0.35)
    else:
        last_task = (
            require_json_object(terminal.model_dump(mode="json"), "crm.note_analyze.last_task")
            if terminal is not None
            else None
        )
        return json.dumps(
            {
                "success": False,
                "error": f"crm note-analyze ({mode}) timed out",
                "task_id": task_id,
                "task": last_task,
            },
            ensure_ascii=False,
        )

    assert terminal is not None
    terminal_payload = require_json_object(
        terminal.model_dump(mode="json"),
        "crm.note_analyze.terminal",
    )
    if terminal.status != "completed":
        return json.dumps(
            {
                "success": False,
                "error": terminal.error_message or f"note-analyze {mode} {terminal.status}",
                "task_id": task_id,
                "task": terminal_payload,
            },
            ensure_ascii=False,
        )

    if mode == "apply":
        return json.dumps(
            {
                "success": True,
                "note_id": note_id,
                "task_id": task_id,
                "mode": "apply",
                "task": terminal_payload,
                "blocks": [
                    {
                        "type": "text",
                        "text": "Черновик анализа применён к графу.",
                    }
                ],
            },
            ensure_ascii=False,
        )

    draft_payload: JsonObject = {}
    try:
        entity = EntityResponse.model_validate(
            await client.get(
                "crm",
                f"/crm/api/v1/entities/{quote(note_id, safe='')}",
                timeout=60.0,
            )
        )
    except ServiceClientError as exc:
        return json.dumps(
            {
                "success": False,
                "error": str(exc),
                "task_id": task_id,
                "task": terminal_payload,
            },
            ensure_ascii=False,
        )
    raw_draft = entity.attributes.get("ai_analysis_draft")
    if isinstance(raw_draft, dict):
        draft = AIAnalysisDraftStored.model_validate(raw_draft)
        draft_payload = require_json_object(
            draft.model_dump(mode="json"),
            "crm.note_analyze.draft",
        )

    summary = "Анализ выполнен."
    entities_list = draft_payload.get("entities")
    if isinstance(entities_list, list) and len(entities_list) > 0:
        summary = f"Найдено сущностей: {len(entities_list)}."
    else:
        cnt = terminal.data.get("result_entities_count")
        if isinstance(cnt, int) and cnt > 0:
            summary = f"Найдено сущностей: {cnt}."

    analyze_payload: JsonObject = {"task_id": task_id, **draft_payload}
    if "result_entities_count" not in analyze_payload and "result_entities_count" in terminal.data:
        analyze_payload["result_entities_count"] = terminal.data["result_entities_count"]
    if (
        "result_relationships_count" not in analyze_payload
        and "result_relationships_count" in terminal.data
    ):
        analyze_payload["result_relationships_count"] = terminal.data["result_relationships_count"]

    blocks = [
        {"type": "text", "text": summary},
        {
            "type": "actions",
            "buttons": [
                {
                    "action_id": "crm.entity.open",
                    "action_kind": "open_entity",
                    "label": "Открыть заметку",
                    "arguments": {"entity_id": note_id},
                    "context": {"entity_id": note_id, "entity_type": "note"},
                }
            ],
        },
    ]
    return json.dumps(
        {"success": True, "analyze": analyze_payload, "blocks": blocks},
        ensure_ascii=False,
    )


@tool(
    name="crm_update_entity",
    description=(
        "Updates a CRM entity (PUT /crm/api/v1/entities/{entity_id}). "
        "Pass only fields to change. Never invent entity_id."
    ),
    tags=["crm"],
    parameters_model=CrmUpdateEntityArgs,
)
async def crm_update_entity(
    entity_id: str,
    name: str | None = None,
    description: str | None = None,
    status: str | None = None,
    entity_type: str | None = None,
    entity_subtype: str | None = None,
    tags: list[str] | None = None,
    note_date: str | None = None,
    *,
    state: "ExecutionState",
) -> str:
    _ = state
    eid = entity_id.strip()
    if not eid:
        raise ValueError("entity_id is required")
    update = EntityUpdate(
        name=name.strip() if name and str(name).strip() else None,
        description=description if description is not None else None,
        status=status.strip() if status and str(status).strip() else None,
        entity_type=entity_type.strip() if entity_type and str(entity_type).strip() else None,
        entity_subtype=(
            entity_subtype.strip() if entity_subtype and str(entity_subtype).strip() else None
        ),
        tags=tags,
        note_date=Date.fromisoformat(note_date.strip())
        if note_date and str(note_date).strip()
        else None,
    )
    body = require_json_object(
        update.model_dump(mode="json", exclude_none=True),
        "crm.update_entity.body",
    )
    if not body:
        raise ValueError("crm_update_entity: at least one field to update is required")
    client = ServiceClient()
    try:
        updated = EntityResponse.model_validate(
            await client.put("crm", f"/crm/api/v1/entities/{quote(eid, safe='')}", json=body)
        )
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    payload = require_json_object(updated.model_dump(mode="json"), "crm.update_entity.response")
    return json.dumps({"success": True, "entity": payload}, ensure_ascii=False)


@tool(
    name="crm_delete_entity",
    description=(
        "Cascade-deletes a CRM entity "
        "(DELETE /crm/api/v1/entities/{entity_id}). Confirm with the user first."
    ),
    tags=["crm"],
    parameters_model=CrmDeleteEntityArgs,
)
async def crm_delete_entity(entity_id: str, *, state: "ExecutionState") -> str:
    _ = state
    eid = entity_id.strip()
    if not eid:
        raise ValueError("entity_id is required")
    client = ServiceClient()
    try:
        raw = await client.delete("crm", f"/crm/api/v1/entities/{quote(eid, safe='')}")
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    if isinstance(raw, dict):
        return json.dumps(
            {"success": True, "entity_id": eid, **require_json_object(raw, "crm.delete_entity")},
            ensure_ascii=False,
        )
    return json.dumps({"success": True, "entity_id": eid}, ensure_ascii=False)


@tool(
    name="crm_list_notes",
    description=(
        "Lists CRM notes by note_date range "
        "(POST /crm/api/v1/entities/query, entity_type=note). "
        "date_from required; date_to optional (defaults to date_from)."
    ),
    tags=["crm"],
    parameters_model=CrmListNotesArgs,
)
async def crm_list_notes(
    date_from: str,
    date_to: str | None = None,
    namespace: str | None = None,
    query: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    *,
    state: "ExecutionState",
) -> str:
    _ = state
    start = date_from.strip()
    end = date_to.strip() if date_to and str(date_to).strip() else start
    _ = Date.fromisoformat(start)
    _ = Date.fromisoformat(end)
    ns = namespace if namespace and str(namespace).strip() else _require_context_namespace()
    if start == end:
        filters = EntitySearchFilterNode.model_validate(
            {"field": "note_date", "op": "$eq", "value": start}
        )
    else:
        filters = EntitySearchFilterNode.model_validate(
            {
                "$and": [
                    {"field": "note_date", "op": "$gte", "value": start},
                    {"field": "note_date", "op": "$lte", "value": end},
                ]
            }
        )
    request = EntitySearchQueryRequest(
        query=query.strip() if query and str(query).strip() else None,
        entity_type="note",
        namespace=ns,
        filters=filters,
        cursor=cursor.strip() if cursor and str(cursor).strip() else None,
        limit=limit,
        search_mode="text" if not (query and str(query).strip()) else "hybrid",
    )
    body = require_json_object(
        request.model_dump(mode="json", by_alias=True, exclude_none=True),
        "crm.list_notes.body",
    )
    client = ServiceClient()
    try:
        raw = await client.post("crm", "/crm/api/v1/entities/query", json=body)
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    try:
        page = CursorPage[EntityResponse].model_validate(raw)
    except ValueError:
        return json.dumps(
            {"success": False, "error": "crm_list_notes: invalid response"},
            ensure_ascii=False,
        )
    items = [
        {
            "entity_id": item.entity_id,
            "name": item.name,
            "note_date": item.note_date.isoformat() if item.note_date is not None else None,
            "entity_subtype": item.entity_subtype,
            "namespace": item.namespace,
            "status": item.status,
        }
        for item in page.items
    ]
    return json.dumps(
        {
            "success": True,
            "items": items,
            "next_cursor": page.next_cursor,
            "has_more": page.has_more,
            "count": len(items),
            "date_from": start,
            "date_to": end,
            "namespace": ns,
        },
        ensure_ascii=False,
    )


@tool(
    name="crm_apply_analysis_draft",
    description=(
        "Applies note AI analysis draft to the CRM graph "
        "(POST /crm/api/v1/tasks/note-analyze mode=apply). "
        "Use after crm_analyze_note_text when the user accepts the draft. Analyze ≠ apply."
    ),
    tags=["crm"],
    parameters_model=CrmApplyAnalysisDraftArgs,
)
async def crm_apply_analysis_draft(note_id: str, *, state: "ExecutionState") -> str:
    _ = state
    nid = note_id.strip()
    if not nid:
        raise ValueError("note_id is required")
    request = StartNoteAnalyzeRequest(note_id=nid, mode="apply")
    body = require_json_object(
        request.model_dump(mode="json", exclude_none=True),
        "crm.apply_analysis_draft.request",
    )
    client = ServiceClient()
    try:
        start = TaskResponse.model_validate(
            await client.post(
                "crm",
                "/crm/api/v1/tasks/note-analyze",
                json=body,
                timeout=60.0,
            )
        )
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    return await _poll_note_analyze_task(
        client=client,
        task_id=start.task_id.strip(),
        note_id=nid,
        mode="apply",
    )


@tool(
    name="crm_discard_analysis_draft",
    description=(
        "Discards note AI analysis draft without applying "
        "(DELETE /crm/api/v1/entities/notes/{note_id}/analysis-draft)."
    ),
    tags=["crm"],
    parameters_model=CrmDiscardAnalysisDraftArgs,
)
async def crm_discard_analysis_draft(note_id: str, *, state: "ExecutionState") -> str:
    _ = state
    nid = note_id.strip()
    if not nid:
        raise ValueError("note_id is required")
    client = ServiceClient()
    try:
        _ = await client.delete(
            "crm",
            f"/crm/api/v1/entities/notes/{quote(nid, safe='')}/analysis-draft",
        )
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    return json.dumps(
        {"success": True, "note_id": nid, "status": "draft_discarded"},
        ensure_ascii=False,
    )


@tool(
    name="crm_merge_entities",
    description=(
        "Merges source entity into survivor "
        "(POST /crm/api/v1/entities/merge). Survivor keeps entity_id; source is deleted."
    ),
    tags=["crm"],
    parameters_model=CrmMergeEntitiesArgs,
)
async def crm_merge_entities(
    survivor_entity_id: str,
    source_entity_id: str,
    *,
    state: "ExecutionState",
) -> str:
    _ = state
    survivor = survivor_entity_id.strip()
    source = source_entity_id.strip()
    if not survivor or not source:
        raise ValueError("survivor_entity_id and source_entity_id are required")
    if survivor == source:
        raise ValueError("survivor_entity_id and source_entity_id must differ")
    request = EntityMergeRequest(
        survivor_entity_id=survivor,
        source_entity_id=source,
    )
    body = require_json_object(
        request.model_dump(mode="json"),
        "crm.merge_entities.body",
    )
    client = ServiceClient()
    try:
        merged = EntityMergeResponse.model_validate(
            await client.post("crm", "/crm/api/v1/entities/merge", json=body)
        )
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    payload = require_json_object(merged.model_dump(mode="json"), "crm.merge_entities.response")
    return json.dumps({"success": True, "merge": payload}, ensure_ascii=False)


@tool(
    name="crm_period_summary",
    description=(
        "Period notes summary "
        "(POST /crm/api/v1/entities/period-summary, date_from/date_to YYYY-MM-DD)."
    ),
    tags=["crm"],
    parameters_model=CrmPeriodSummaryArgs,
)
async def crm_period_summary(
    date_from: str,
    date_to: str,
    namespace: str | None = None,
    force_rebuild: bool = False,
    *,
    state: "ExecutionState",
) -> str:
    _ = state
    start = date_from.strip()
    end = date_to.strip()
    if not start or not end:
        raise ValueError("date_from and date_to are required")
    ns_clear = namespace if namespace and str(namespace).strip() else None
    request = PeriodSummaryRequest(
        date_from=start,
        date_to=end,
        namespace=ns_clear,
        force_rebuild=bool(force_rebuild),
    )
    body = require_json_object(
        request.model_dump(mode="json", exclude_none=True),
        "crm.period_summary.request",
    )
    client = ServiceClient()
    try:
        raw = await client.post("crm", "/crm/api/v1/entities/period-summary", json=body)
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    if not isinstance(raw, dict):
        return json.dumps(
            {"success": False, "error": "crm_period_summary: invalid response"},
            ensure_ascii=False,
        )
    response = require_json_object(raw, "crm.period_summary.response")
    summary_text = response.get("summary")
    if isinstance(summary_text, str) and summary_text.strip():
        main = summary_text.strip()
    else:
        main = json.dumps(response, ensure_ascii=False)[:2500]
    blocks: list[JsonObject] = [{"type": "text", "text": main}]
    return json.dumps({"success": True, "response": response, "blocks": blocks}, ensure_ascii=False)


@tool(
    name="crm_create_activity_task",
    description=(
        "Creates CRM activity task pair: CRMEntity(task) + WorkItem(crm_activity) "
        "(POST /crm/api/v1/activity-tasks). Returns entity_id and work_item_id. "
        "Further work mutations — load work-items tools."
    ),
    tags=["crm", "worktracker"],
    parameters_model=CrmCreateActivityTaskArgs,
)
async def crm_create_activity_task(
    title: str,
    description: str | None = None,
    namespace: str | None = None,
    entity_subtype: str | None = None,
    priority: str | None = None,
    due_date: str | None = None,
    assignees: list[str] | None = None,
    tags: list[str] | None = None,
    *,
    state: "ExecutionState",
) -> str:
    _ = state
    ns = namespace if namespace and str(namespace).strip() else _require_context_namespace()
    body: JsonObject = {
        "title": title.strip(),
        "namespace": ns,
    }
    if description is not None and str(description).strip():
        body["description"] = description.strip()
    if entity_subtype is not None and str(entity_subtype).strip():
        body["entity_subtype"] = entity_subtype.strip()
    if priority is not None and str(priority).strip():
        body["priority"] = priority.strip()
    if due_date is not None and str(due_date).strip():
        body["due_date"] = due_date.strip()
    if assignees is not None:
        body["assignees"] = list(assignees)
    if tags is not None:
        body["tags"] = list(tags)
    client = ServiceClient()
    try:
        raw = await client.post("crm", "/crm/api/v1/activity-tasks", json=body)
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    payload = require_json_object(raw, "crm.create_activity_task.response")
    entity_raw = payload.get("entity")
    work_raw = payload.get("work_item")
    if not isinstance(entity_raw, dict) or not isinstance(work_raw, dict):
        return json.dumps(
            {"success": False, "error": "crm_create_activity_task: invalid response shape"},
            ensure_ascii=False,
        )
    entity = EntityResponse.model_validate(entity_raw)
    work_item = WorkItem.model_validate(work_raw)
    return json.dumps(
        {
            "success": True,
            "entity_id": entity.entity_id,
            "work_item_id": work_item.work_item_id,
            "entity": require_json_object(entity.model_dump(mode="json"), "crm.activity.entity"),
            "work_item": require_json_object(
                work_item.model_dump(mode="json"),
                "crm.activity.work_item",
            ),
            "blocks": [
                {
                    "type": "card",
                    "title": entity.name,
                    "subtitle": f"work_item_id={work_item.work_item_id}",
                }
            ],
        },
        ensure_ascii=False,
    )


@tool(
    name="crm_list_activity_tasks",
    description=(
        "Lists CRM activity WorkItems "
        "(GET /crm/api/v1/activity-tasks). For state/board mutations use work_item_* tools."
    ),
    tags=["crm", "worktracker"],
    parameters_model=CrmListActivityTasksArgs,
)
async def crm_list_activity_tasks(
    namespace: str | None = None,
    work_item_state: str | None = None,
    limit: int = 50,
    offset: int = 0,
    *,
    state: "ExecutionState",
) -> str:
    _ = state
    query: dict[str, str] = {"limit": str(limit), "offset": str(offset)}
    if namespace is not None and str(namespace).strip():
        query["namespace"] = namespace.strip()
    if work_item_state is not None and str(work_item_state).strip():
        parsed = WorkItemState(work_item_state.strip())
        query["state"] = parsed.value
    path = f"/crm/api/v1/activity-tasks?{urlencode(query)}"
    client = ServiceClient()
    try:
        raw = await client.get("crm", path)
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    try:
        page = OffsetPage[WorkItem].model_validate(raw)
    except ValueError:
        return json.dumps(
            {"success": False, "error": "crm_list_activity_tasks: invalid response"},
            ensure_ascii=False,
        )
    items = [
        {
            "work_item_id": item.work_item_id,
            "title": item.title,
            "state": item.state.value,
            "kind": item.kind.value,
            "namespace": item.namespace,
        }
        for item in page.items
    ]
    return json.dumps(
        {
            "success": True,
            "items": items,
            "total": page.total,
            "limit": page.limit,
            "offset": page.offset,
            "count": len(items),
        },
        ensure_ascii=False,
    )
