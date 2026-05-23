"""
Тулы Lara для CRM через ServiceClient (тот же REST, что у UI). Требуют контекст пользователя в worker.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date as Date
from typing import TYPE_CHECKING, ClassVar, Literal
from urllib.parse import quote

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from apps.crm.models.api import (
    AIAnalysisDraftStored,
    DailySummaryRequest,
    EntityCreate,
    EntityResponse,
    EntitySearchQueryRequest,
    EntityTypeResponse,
    RelationshipCreate,
    RelationshipResponse,
    StartNoteAnalyzeRequest,
    TaskResponse,
)
from apps.flows.src.models.flow_config import FlowConfig
from apps.flows.src.runtime_helpers.state_utils import push_ui_event
from apps.flows.src.services.platform_facades import get_lara_facade
from apps.flows.src.tools.decorator import tool
from core.clients.service_client import ServiceClient, ServiceClientError
from core.context import get_context
from core.pagination import CursorPage, OffsetPage
from core.types import (
    JsonObject,
    JsonValue,
    parse_json_array,
    parse_json_object,
    require_json_array,
    require_json_object,
)

if TYPE_CHECKING:
    from core.state import ExecutionState


def _require_context_namespace() -> str:
    ctx = get_context()
    if ctx is None:
        raise RuntimeError("Context is not set")
    return ctx.active_namespace or "default"


def _analyze_mock(args: JsonObject, state: "ExecutionState | None" = None) -> str:
    _ = args
    _ = state
    return json.dumps(
        {
            "success": True,
            "blocks": [
                {
                    "type": "text",
                    "text": "Mock: анализ завершён.",
                }
            ],
        },
        ensure_ascii=False,
    )


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


class PushEmbedBlocksArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    blocks_json: str = Field(
        ...,
        min_length=2,
        description=(
            "Одна JSON-строка: массив объектов блоков UI. У каждого объекта поле type: "
            "card | table | actions | file_card | text и поля по схеме блока."
        ),
    )


class FlowsReadContextArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    flow_id: str = Field(..., min_length=1, description="ID flow в сервисе flows.")
    branch_id: str | None = Field(
        None,
        description="ID ветки (branch). Для базового графа передай base или оставь пустым.",
    )
    node_id: str | None = Field(
        None,
        description="ID ноды в выбранном графе. Если не передан, вернётся только контекст flow/branch.",
    )


class FlowsPatchNodeArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    flow_id: str | None = Field(None, description="ID flow (обязателен при mode=propose).")
    node_id: str | None = Field(None, description="ID ноды (обязателен при mode=propose).")
    patch_json: str | None = Field(
        None,
        description="JSON-объект изменений ноды при mode=propose.",
    )
    branch_id: str | None = Field(
        None,
        description="ID ветки (branch). Для base можно не передавать.",
    )
    mode: Literal["propose", "apply"] = Field(
        "propose",
        description="propose — подготовить действие и ждать подтверждения; apply — применить по pending_action_id.",
    )
    pending_action_id: str | None = Field(
        None,
        description="ID действия из propose. Обязателен для mode=apply.",
    )
    idempotency_key: str | None = Field(
        None,
        description="Идемпотентный ключ выполнения. Если не передан, используется pending_action_id.",
    )

    @field_validator("pending_action_id", mode="before")
    @classmethod
    def _strip_pending_patch_node(cls, v: JsonValue) -> JsonValue:
        if v is None:
            return None
        if isinstance(v, str):
            return v.strip() or None
        return v

    @model_validator(mode="after")
    def _flows_patch_node_mode(self) -> "FlowsPatchNodeArgs":
        if self.mode == "apply":
            if self.pending_action_id is None:
                raise ValueError("pending_action_id is required when mode='apply'")
            return self
        fid = self.flow_id
        nid = self.node_id
        pj = self.patch_json
        if not fid or not str(fid).strip():
            raise ValueError("flow_id is required when mode='propose'")
        if not nid or not str(nid).strip():
            raise ValueError("node_id is required when mode='propose'")
        if pj is None or not str(pj).strip():
            raise ValueError("patch_json is required when mode='propose'")
        return self


class FlowsPatchFlowArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    flow_id: str | None = Field(None, description="ID flow (обязателен при mode=propose).")
    patch_json: str | None = Field(
        None,
        description=(
            "JSON-объект изменений flow при mode=propose. Разрешённые поля: name, description, tags, variables."
        ),
    )
    mode: Literal["propose", "apply"] = Field(
        "propose",
        description="propose — подготовить действие и ждать подтверждения; apply — применить по pending_action_id.",
    )
    pending_action_id: str | None = Field(
        None,
        description="ID действия из propose. Обязателен для mode=apply.",
    )
    idempotency_key: str | None = Field(
        None,
        description="Идемпотентный ключ выполнения. Если не передан, используется pending_action_id.",
    )

    @field_validator("pending_action_id", mode="before")
    @classmethod
    def _strip_pending_patch_flow(cls, v: JsonValue) -> JsonValue:
        if v is None:
            return None
        if isinstance(v, str):
            return v.strip() or None
        return v

    @model_validator(mode="after")
    def _flows_patch_flow_mode(self) -> "FlowsPatchFlowArgs":
        if self.mode == "apply":
            if self.pending_action_id is None:
                raise ValueError("pending_action_id is required when mode='apply'")
            return self
        if self.flow_id is None or not str(self.flow_id).strip():
            raise ValueError("flow_id is required when mode='propose'")
        if self.patch_json is None or not str(self.patch_json).strip():
            raise ValueError("patch_json is required when mode='propose'")
        return self


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


def _crm_search_entities_mock(args: JsonObject, state: "ExecutionState | None" = None) -> str:
    _ = args
    _ = state
    return json.dumps(
        {
            "success": True,
            "hits": [
                {
                    "entity_id": "ent_mock_1",
                    "name": "Mock hit",
                    "entity_type": "contact",
                    "entity_subtype": None,
                    "description": None,
                    "namespace": "default",
                }
            ],
            "blocks": [{"type": "text", "text": "Mock: найдено 1 сущность."}],
        },
        ensure_ascii=False,
    )


def _crm_create_note_mock(args: JsonObject, state: "ExecutionState | None" = None) -> str:
    _ = state
    raw_name = args.get("name")
    name = raw_name if isinstance(raw_name, str) else ""
    return json.dumps(
        {
            "success": True,
            "entity_id": "note_mock_1",
            "entity": {"entity_id": "note_mock_1", "name": name, "entity_type": "note"},
            "blocks": [{"type": "card", "title": name or "Note", "subtitle": "created (mock)"}],
        },
        ensure_ascii=False,
    )


def _crm_create_note_and_analyze_mock(
    args: JsonObject,
    state: "ExecutionState | None" = None,
) -> str:
    _ = args
    _ = state
    return json.dumps(
        {
            "success": True,
            "entity_id": "note_mock_combo",
            "analyze": {"entities": []},
            "blocks": [{"type": "text", "text": "Mock: заметка создана и анализ выполнен."}],
        },
        ensure_ascii=False,
    )


def _push_embed_blocks_mock(args: JsonObject, state: "ExecutionState | None" = None) -> str:
    _ = state
    blocks_json = args.get("blocks_json")
    return blocks_json if isinstance(blocks_json, str) else "[]"


def _flows_read_context_mock(args: JsonObject, state: "ExecutionState | None" = None) -> str:
    _ = state
    flow_id = args.get("flow_id")
    branch_id = args.get("branch_id")
    node_id = args.get("node_id")
    return json.dumps(
        {
            "success": True,
            "flow_id": flow_id if isinstance(flow_id, str) else "flow_mock",
            "branch_id": branch_id if isinstance(branch_id, str) else "base",
            "node_id": node_id if isinstance(node_id, str) else None,
            "blocks": [{"type": "text", "text": "Mock: контекст flow получен."}],
        },
        ensure_ascii=False,
    )


def _flows_patch_node_mock(args: JsonObject, state: "ExecutionState | None" = None) -> str:
    _ = state
    flow_id = args.get("flow_id")
    branch_id = args.get("branch_id")
    node_id = args.get("node_id")
    mode = args.get("mode")
    return json.dumps(
        {
            "success": True,
            "flow_id": flow_id if isinstance(flow_id, str) else "flow_mock",
            "branch_id": branch_id if isinstance(branch_id, str) else "base",
            "node_id": node_id if isinstance(node_id, str) else "main",
            "mode": mode if isinstance(mode, str) else "apply",
            "blocks": [{"type": "text", "text": "Mock: patch ноды обработан."}],
        },
        ensure_ascii=False,
    )


def _flows_patch_flow_mock(args: JsonObject, state: "ExecutionState | None" = None) -> str:
    _ = state
    flow_id = args.get("flow_id")
    mode = args.get("mode")
    return json.dumps(
        {
            "success": True,
            "flow_id": flow_id if isinstance(flow_id, str) else "flow_mock",
            "mode": mode if isinstance(mode, str) else "apply",
            "blocks": [{"type": "text", "text": "Mock: patch flow обработан."}],
        },
        ensure_ascii=False,
    )


@tool(
    name="crm_search_entities",
    description=(
        "Гибридный поиск по сущностям CRM (полнотекст + семантика, как строка «Поиск» в списке сущностей). "
        "Не добавляй фильтры по типу или пространству, если пользователь об этом не просил. "
        "Ответ — JSON: успех, список совпадений и блоки для чата."
    ),
    tags=["crm", "lara", "search"],
    args_schema=CrmSearchEntitiesArgs,
    mock_response=_crm_search_entities_mock,
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
    tags=["crm", "lara", "notes"],
    args_schema=CrmCreateNoteArgs,
    mock_response=_crm_create_note_mock,
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
    tags=["crm", "lara", "notes", "ai"],
    args_schema=CrmCreateNoteAndAnalyzeArgs,
    mock_response=_crm_create_note_and_analyze_mock,
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
        "Запускает AI-анализ заметки в CRM (извлечение сущностей). "
        "Обязательно: note_id. Текст берётся из заметки автоматически. "
        "Возвращает JSON с кратким summary и blocks для чата."
    ),
    tags=["crm", "lara", "ai"],
    args_schema=CrmAnalyzeNoteTextArgs,
    mock_response=_analyze_mock,
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

    task_id = start.task_id.strip()

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
            else {}
        )
        return json.dumps(
            {
                "success": False,
                "error": "analyze task timeout",
                "task_id": task_id,
                "last_task": last_task,
            },
            ensure_ascii=False,
        )

    terminal_payload = require_json_object(
        terminal.model_dump(mode="json"),
        "crm.note_analyze.task",
    )
    analyze_task_state = terminal.status
    if analyze_task_state == "failed":
        msg = terminal.error_message
        if not isinstance(msg, str) or not msg.strip():
            msg = "analyze failed"
        return json.dumps(
            {
                "success": False,
                "error": msg,
                "task_id": task_id,
                "task": terminal_payload,
            },
            ensure_ascii=False,
        )
    if analyze_task_state == "cancelled":
        return json.dumps(
            {
                "success": False,
                "error": "analyze cancelled",
                "task_id": task_id,
                "task": terminal_payload,
            },
            ensure_ascii=False,
        )
    if analyze_task_state != "completed":
        return json.dumps(
            {
                "success": False,
                "error": f"unexpected analyze task status: {analyze_task_state}",
                "task_id": task_id,
                "task": terminal_payload,
            },
            ensure_ascii=False,
        )

    draft_payload: JsonObject = {}
    try:
        entity = EntityResponse.model_validate(
            await client.get(
                "crm",
                f"/crm/api/v1/entities/{quote(nid, safe='')}",
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
    if "result_relationships_count" not in analyze_payload and "result_relationships_count" in terminal.data:
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
                    "arguments": {"entity_id": nid},
                    "context": {"entity_id": nid, "entity_type": "note"},
                }
            ],
        },
    ]
    return json.dumps(
        {"success": True, "analyze": analyze_payload, "blocks": blocks},
        ensure_ascii=False,
    )


@tool(
    name="push_embed_blocks",
    description=(
        "Отображает блоки UI в чате Lara. Передай blocks_json — JSON-массив объектов "
        "с полем type: card | table | actions | file_card | text и полями схемы."
    ),
    tags=["lara", "ui"],
    args_schema=PushEmbedBlocksArgs,
    mock_response=_push_embed_blocks_mock,
)
async def push_embed_blocks(blocks_json: str, *, state: "ExecutionState") -> str:
    _ = state
    parsed = parse_json_array(blocks_json, "blocks_json")
    return json.dumps({"blocks": parsed}, ensure_ascii=False)


@tool(
    name="flows_read_context",
    description=(
        "Возвращает контекст flow/branch/node для Lara в сервисе flows: текущий граф, "
        "конфиг ноды и метаданные для принятия решения."
    ),
    tags=["flows", "lara", "query"],
    args_schema=FlowsReadContextArgs,
    mock_response=_flows_read_context_mock,
)
async def flows_read_context(
    flow_id: str,
    branch_id: str | None = None,
    node_id: str | None = None,
    *,
    state: "ExecutionState",
) -> str:
    def normalize_branch_id(raw_branch_id: str | None) -> str:
        if raw_branch_id is None:
            return "base"
        cleaned = raw_branch_id.strip()
        if not cleaned or cleaned == "default":
            return "base"
        return cleaned

    def resolve_node_scope(flow_data: FlowConfig, resolved_branch: str) -> dict[str, JsonObject]:
        if resolved_branch == "base":
            nodes = flow_data.nodes
            if nodes is None:
                raise ValueError("Flow base nodes are invalid")
            return nodes
        branch_payload = flow_data.branches.get(resolved_branch)
        if branch_payload is None:
            raise ValueError(f"Ветка '{resolved_branch}' не найдена во flow '{flow_data.flow_id}'")
        nodes = branch_payload.nodes
        if nodes is None:
            raise ValueError(f"У ветки '{resolved_branch}' нет объекта nodes")
        return nodes

    def require_node(
        flow_data: FlowConfig, resolved_branch: str, required_node_id: str
    ) -> JsonObject:
        nodes = resolve_node_scope(flow_data, resolved_branch)
        node = nodes.get(required_node_id)
        if node is None:
            raise ValueError(
                f"Node '{required_node_id}' not found in branch '{resolved_branch}'"
            )
        return node

    _ = state
    client = ServiceClient()
    flow_config = FlowConfig.model_validate(
        await client.get("flows", f"/flows/api/v1/flows/{quote(flow_id, safe='')}")
    )
    flow_payload = require_json_object(flow_config.model_dump(mode="json"), "flows.read_context.flow")

    resolved_branch_id = normalize_branch_id(branch_id)
    selected_node: JsonObject | None = None
    if node_id:
        selected_node = require_node(flow_config, resolved_branch_id, node_id)

    payload: JsonObject = {
        "success": True,
        "flow_id": flow_id,
        "branch_id": resolved_branch_id,
        "node_id": node_id or None,
        "flow": flow_payload,
        "node": selected_node,
        "blocks": [
            {
                "type": "card",
                "title": flow_config.name or flow_id,
                "subtitle": f"Flow: {flow_id} | Branch: {resolved_branch_id}",
            }
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


@tool(
    name="flows_patch_node",
    description=(
        "Готовит patch ноды flow для применения во внешнем UI. "
        "Возвращает node_before/node_after и ui_events; сам tool не сохраняет flow."
    ),
    tags=["flows", "lara", "mutation"],
    args_schema=FlowsPatchNodeArgs,
    mock_response=_flows_patch_node_mock,
)
async def flows_patch_node(
    flow_id: str | None = None,
    node_id: str | None = None,
    patch_json: str | None = None,
    branch_id: str | None = None,
    mode: Literal["propose", "apply"] = "propose",
    pending_action_id: str | None = None,
    idempotency_key: str | None = None,
    *,
    state: "ExecutionState",
) -> str:
    def normalize_branch_id(raw_branch_id: str | None) -> str:
        if raw_branch_id is None:
            return "base"
        cleaned = raw_branch_id.strip()
        if not cleaned or cleaned == "default":
            return "base"
        return cleaned

    facade = get_lara_facade()

    if mode == "propose":
        if flow_id is None or node_id is None or patch_json is None:
            raise ValueError("flow_id, node_id and patch_json are required for mode=propose")
        patch = parse_json_object(patch_json, "flows_patch_node.patch_json")

        resolved_branch_id = normalize_branch_id(branch_id)
        action = await facade.preview_node_patch(
            flow_id=flow_id,
            node_id=node_id,
            patch=patch,
            branch_id=resolved_branch_id,
            state=state,
            idempotency_key=idempotency_key,
        )
        action_payload = require_json_object(
            action.model_dump(mode="json"),
            "flows.node.preview.action",
        )
        preview_data = action.preview
        node_before = preview_data.get("node_before")
        node_after = preview_data.get("node_after")
        preview_payload: JsonObject = {
            "action": action_payload,
            "patch_kind": "node",
            "flow_id": flow_id,
            "branch_id": resolved_branch_id,
            "node_id": node_id,
            "changes": patch,
            "open_editor": True,
        }
        apply_button = require_json_object(
            {
                "action_id": "flows.node.patch.apply",
                "action_kind": "apply",
                "label": "Применить изменение",
                "pending_action_id": action.pending_action_id,
                "arguments": {
                    "pending_action_id": action.pending_action_id,
                    "flow_id": flow_id,
                    "branch_id": resolved_branch_id,
                    "node_id": node_id,
                },
                "context": {
                    "flow_id": flow_id,
                    "branch_id": resolved_branch_id,
                    "node_id": node_id,
                    "patch_kind": "node",
                },
            },
            "flows.node.preview.apply_button",
        )
        preview_blocks = require_json_array(
            [
                {"type": "text", "text": f"Черновик готов. Подтвердите применение для ноды {node_id}."},
                {"type": "actions", "buttons": [apply_button]},
            ],
            "flows.node.preview.blocks",
        )
        preview_payload["blocks"] = preview_blocks
        _ = push_ui_event(
            state,
            event_type="action_previewed",
            payload=preview_payload,
            event_id=f"flows-node-preview-{action.pending_action_id}",
            version="1.0.0",
        )
        return json.dumps(
            {
                "success": True,
                "mode": mode,
                "flow_id": flow_id,
                "branch_id": resolved_branch_id,
                "node_id": node_id,
                "pending_action_id": action.pending_action_id,
                "action": action_payload,
                "node_before": node_before,
                "node_after": node_after,
                "blocks": preview_blocks,
            },
            ensure_ascii=False,
        )

    if not pending_action_id:
        raise ValueError("pending_action_id is required for mode=apply")
    action = await facade.apply_node_patch(
        pending_action_id=pending_action_id,
        state=state,
        idempotency_key=idempotency_key,
    )
    action_payload = require_json_object(
        action.model_dump(mode="json"),
        "flows.node.apply.action",
    )
    target = action.target
    flow_resolved = target.get("flow_id")
    node_resolved = target.get("node_id")
    if not isinstance(flow_resolved, str) or not flow_resolved.strip():
        raise ValueError("Pending action target.flow_id is missing")
    if not isinstance(node_resolved, str) or not node_resolved.strip():
        raise ValueError("Pending action target.node_id is missing")
    branch_resolved = target.get("branch_id")
    if branch_resolved is not None and not isinstance(branch_resolved, str):
        raise ValueError("Pending action target.branch_id must be a string")
    resolved_branch_id = normalize_branch_id(branch_resolved)

    preview_data = action.preview
    node_before = preview_data.get("node_before")
    node_after = preview_data.get("node_after")
    patch_raw = action.payload.get("patch")
    if not isinstance(patch_raw, dict):
        raise ValueError("Pending action payload.patch is missing")
    patch_restored = require_json_object(patch_raw, "flows.node.apply.patch")
    event_payload: JsonObject = {
        "action": action_payload,
        "patch_kind": "node",
        "flow_id": flow_resolved,
        "branch_id": resolved_branch_id,
        "node_id": node_resolved,
        "changes": patch_restored,
        "open_editor": True,
    }
    _ = push_ui_event(
        state,
        event_type="action_applied",
        payload=event_payload,
        event_id=f"flows-node-apply-{pending_action_id}",
        version="1.0.0",
    )
    result = {
        "success": True,
        "mode": mode,
        "flow_id": flow_resolved,
        "branch_id": resolved_branch_id,
        "node_id": node_resolved,
        "pending_action_id": pending_action_id,
        "node_before": node_before,
        "node_after": node_after,
        "blocks": [{"type": "text", "text": f"Изменение для ноды {node_resolved} применено."}],
    }
    return json.dumps(result, ensure_ascii=False)


@tool(
    name="flows_patch_flow",
    description=(
        "Готовит patch к самому flow (name/description/tags/variables) для применения во внешнем UI. "
        "Возвращает flow_before/flow_after и ui_events; сам tool не сохраняет flow."
    ),
    tags=["flows", "lara", "mutation"],
    args_schema=FlowsPatchFlowArgs,
    mock_response=_flows_patch_flow_mock,
)
async def flows_patch_flow(
    flow_id: str | None = None,
    patch_json: str | None = None,
    mode: Literal["propose", "apply"] = "propose",
    pending_action_id: str | None = None,
    idempotency_key: str | None = None,
    *,
    state: "ExecutionState",
) -> str:
    facade = get_lara_facade()

    if mode == "propose":
        if flow_id is None or patch_json is None:
            raise ValueError("flow_id and patch_json are required for mode=propose")
        patch = parse_json_object(patch_json, "flows_patch_flow.patch_json")

        allowed_fields = {"name", "description", "tags", "variables"}
        unsupported = sorted(set(patch.keys()) - allowed_fields)
        if unsupported:
            allowed = "Allowed: name, description, tags, variables."
            raise ValueError(f"Unsupported flow patch fields: {', '.join(unsupported)}. {allowed}")

        action = await facade.preview_flow_patch(
            flow_id=flow_id,
            patch=patch,
            state=state,
            idempotency_key=idempotency_key,
        )
        action_payload = require_json_object(
            action.model_dump(mode="json"),
            "flows.flow.preview.action",
        )
        preview_data = action.preview
        flow_before = preview_data.get("flow_before")
        flow_after = preview_data.get("flow_after")
        preview_payload: JsonObject = {
            "action": action_payload,
            "patch_kind": "flow",
            "flow_id": flow_id,
            "flow_changes": patch,
            "open_editor": True,
        }
        apply_button = require_json_object(
            {
                "action_id": "flows.flow.patch.apply",
                "action_kind": "apply",
                "label": "Применить изменение",
                "pending_action_id": action.pending_action_id,
                "arguments": {"pending_action_id": action.pending_action_id, "flow_id": flow_id},
                "context": {"flow_id": flow_id, "patch_kind": "flow"},
            },
            "flows.flow.preview.apply_button",
        )
        preview_blocks = require_json_array(
            [
                {"type": "text", "text": f"Черновик готов. Подтвердите применение для flow {flow_id}."},
                {"type": "actions", "buttons": [apply_button]},
            ],
            "flows.flow.preview.blocks",
        )
        preview_payload["blocks"] = preview_blocks
        _ = push_ui_event(
            state,
            event_type="action_previewed",
            payload=preview_payload,
            event_id=f"flows-flow-preview-{action.pending_action_id}",
            version="1.0.0",
        )
        return json.dumps(
            {
                "success": True,
                "mode": mode,
                "flow_id": flow_id,
                "pending_action_id": action.pending_action_id,
                "action": action_payload,
                "flow_before": flow_before,
                "flow_after": flow_after,
                "blocks": preview_blocks,
            },
            ensure_ascii=False,
        )

    if not pending_action_id:
        raise ValueError("pending_action_id is required for mode=apply")
    action = await facade.apply_flow_patch(
        pending_action_id=pending_action_id,
        state=state,
        idempotency_key=idempotency_key,
    )
    action_payload = require_json_object(
        action.model_dump(mode="json"),
        "flows.flow.apply.action",
    )
    target = action.target
    flow_resolved = target.get("flow_id")
    if not isinstance(flow_resolved, str) or not flow_resolved.strip():
        raise ValueError("Pending action target.flow_id is missing")

    preview_data = action.preview
    flow_before = preview_data.get("flow_before")
    flow_after = preview_data.get("flow_after")

    patch_raw = action.payload.get("patch")
    if not isinstance(patch_raw, dict):
        raise ValueError("Pending action payload.patch is missing")
    patch_restored = require_json_object(patch_raw, "flows.flow.apply.patch")

    apply_payload: JsonObject = {
        "action": action_payload,
        "patch_kind": "flow",
        "flow_id": flow_resolved,
        "flow_changes": patch_restored,
        "open_editor": True,
    }
    _ = push_ui_event(
        state,
        event_type="action_applied",
        payload=apply_payload,
        event_id=f"flows-flow-apply-{pending_action_id}",
        version="1.0.0",
    )
    result = {
        "success": True,
        "mode": mode,
        "flow_id": flow_resolved,
        "pending_action_id": pending_action_id,
        "flow_before": flow_before,
        "flow_after": flow_after,
        "blocks": [{"type": "text", "text": f"Изменение для flow {flow_resolved} применено."}],
    }
    return json.dumps(result, ensure_ascii=False)


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


def _crm_get_entity_mock(args: JsonObject, state: "ExecutionState | None" = None) -> str:
    _ = state
    entity_id = args.get("entity_id")
    return json.dumps(
        {
            "success": True,
            "entity": {"entity_id": entity_id, "name": "Mock", "entity_type": "note"},
        },
        ensure_ascii=False,
    )


def _crm_create_entity_mock(args: JsonObject, state: "ExecutionState | None" = None) -> str:
    _ = state
    return json.dumps(
        {"success": True, "entity": {"entity_id": "mock-e1", "name": args.get("name")}},
        ensure_ascii=False,
    )


def _crm_create_relationship_mock(args: JsonObject, state: "ExecutionState | None" = None) -> str:
    _ = args
    _ = state
    return json.dumps({"success": True, "relationship_id": "rel-mock"}, ensure_ascii=False)


def _crm_list_entity_types_mock(args: JsonObject, state: "ExecutionState | None" = None) -> str:
    _ = args
    _ = state
    return json.dumps(
        {"success": True, "items": [{"type_id": "note"}], "blocks": [{"type": "text", "text": "mock"}]},
        ensure_ascii=False,
    )


def _crm_daily_summary_mock(args: JsonObject, state: "ExecutionState | None" = None) -> str:
    _ = args
    _ = state
    return json.dumps(
        {"success": True, "summary": "mock", "blocks": [{"type": "text", "text": "mock"}]},
        ensure_ascii=False,
    )


@tool(
    name="crm_get_entity",
    description=(
        "Загружает сущность CRM по entity_id (GET /crm/api/v1/entities/{id}). "
        "Возвращает JSON и card-блок для чата."
    ),
    tags=["crm", "lara"],
    args_schema=CrmGetEntityArgs,
    mock_response=_crm_get_entity_mock,
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
    tags=["crm", "lara", "mutation"],
    args_schema=CrmCreateEntityArgs,
    mock_response=_crm_create_entity_mock,
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
    tags=["crm", "lara", "mutation", "graph"],
    args_schema=CrmCreateRelationshipArgs,
    mock_response=_crm_create_relationship_mock,
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
    tags=["crm", "lara"],
    args_schema=CrmListEntityTypesArgs,
    mock_response=_crm_list_entity_types_mock,
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
        "Сводка заметок за день (POST /crm/api/v1/entities/daily-summary, date YYYY-MM-DD)."
    ),
    tags=["crm", "lara", "summaries"],
    args_schema=CrmDailySummaryArgs,
    mock_response=_crm_daily_summary_mock,
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
