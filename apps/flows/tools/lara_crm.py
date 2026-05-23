"""
Тулы Lara для CRM через ServiceClient (тот же REST, что у UI). Требуют контекст пользователя в worker.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import quote

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from apps.flows.src.runtime_helpers.state_utils import push_ui_event
from apps.flows.src.services.platform_facades import get_lara_facade
from apps.flows.src.tools.decorator import tool
from core.clients.service_client import ServiceClient, ServiceClientError
from core.context import get_context

if TYPE_CHECKING:
    from core.state import ExecutionState

JsonDict = dict[str, Any]


def _require_context_namespace() -> str:
    ctx = get_context()
    if ctx is None:
        raise RuntimeError("Context is not set")
    return ctx.active_namespace or "default"


def _analyze_mock(args: JsonDict, state: Any = None) -> str:
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

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

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
    def _optional_str(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v


class CrmCreateNoteArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    def _strip_name(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str):
            return v.strip() or None
        return v

    @field_validator("description", mode="before")
    @classmethod
    def _strip_description(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s if s else None
        return v

    @model_validator(mode="after")
    def _mode_requirements(self):  # noqa: ANN201
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
    def _optional_str_note(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v


class CrmAnalyzeNoteTextArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    def _strip_note_id(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip() or None
        return v


class CrmCreateNoteAndAnalyzeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    def _optional_str_combo(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v


class PushEmbedBlocksArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    blocks_json: str = Field(
        ...,
        min_length=2,
        description=(
            "Одна JSON-строка: массив объектов блоков UI. У каждого объекта поле type: "
            "card | table | actions | file_card | text и поля по схеме блока."
        ),
    )


class FlowsReadContextArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

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
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

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
    def _strip_pending_patch_node(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str):
            return v.strip() or None
        return v

    @model_validator(mode="after")
    def _flows_patch_node_mode(self):  # noqa: ANN201
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
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

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
    def _strip_pending_patch_flow(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str):
            return v.strip() or None
        return v

    @model_validator(mode="after")
    def _flows_patch_flow_mode(self):  # noqa: ANN201
        if self.mode == "apply":
            if self.pending_action_id is None:
                raise ValueError("pending_action_id is required when mode='apply'")
            return self
        if self.flow_id is None or not str(self.flow_id).strip():
            raise ValueError("flow_id is required when mode='propose'")
        if self.patch_json is None or not str(self.patch_json).strip():
            raise ValueError("patch_json is required when mode='propose'")
        return self


def _compact_entity_hit(raw: dict[str, Any]) -> dict[str, Any]:
    desc = raw.get("description")
    if isinstance(desc, str) and len(desc) > 400:
        desc = desc[:400] + "…"
    return {
        "entity_id": raw.get("entity_id"),
        "name": raw.get("name"),
        "entity_type": raw.get("entity_type"),
        "entity_subtype": raw.get("entity_subtype"),
        "description": desc,
        "namespace": raw.get("namespace"),
    }


@tool(
    name="crm_search_entities",
    description=(
        "Гибридный поиск по сущностям CRM (полнотекст + семантика, как строка «Поиск» в списке сущностей). "
        "Не добавляй фильтры по типу или пространству, если пользователь об этом не просил. "
        "Ответ — JSON: успех, список совпадений и блоки для чата."
    ),
    tags=["crm", "lara", "search"],
    args_schema=CrmSearchEntitiesArgs,
    mock_response=lambda args, state=None: json.dumps(
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
    ),
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
    q = (query or "").strip() if query else ""
    if not q and search:
        q = str(search).strip()
    if not q:
        raise ValueError(
            "Нужен непустой параметр query — короткая строка семантического поиска (ключевые слова из запроса пользователя)."
        )
    ns = namespace if namespace else _require_context_namespace()
    payload: dict[str, Any] = {
        "query": q,
        "namespace": ns,
        "search_mode": "hybrid",
        "limit": max(1, min(1000, int(limit))),
    }
    if entity_type:
        payload["entity_type"] = entity_type
    if entity_subtype:
        payload["entity_subtype"] = entity_subtype

    client = ServiceClient()
    try:
        raw_response = await client.post("crm", "/crm/api/v1/entities/query", json=payload)
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)

    if not isinstance(raw_response, dict) or "items" not in raw_response:
        return json.dumps({"success": False, "error": "CRM search: invalid response"}, ensure_ascii=False)

    hits = [_compact_entity_hit(x) for x in raw_response["items"] if isinstance(x, dict)]
    summary = f"Найдено сущностей: {len(hits)}."
    blocks: list[dict[str, Any]] = [{"type": "text", "text": summary}]
    if hits:
        rows = [
            {
                "entity_id": h.get("entity_id"),
                "name": h.get("name"),
                "type": h.get("entity_type"),
                "subtype": h.get("entity_subtype"),
            }
            for h in hits[:20]
        ]
        blocks.append(
            {
                "type": "table",
                "title": "Результаты поиска",
                "columns": [
                    {"key": "name", "label": "Имя"},
                    {"key": "type", "label": "Тип"},
                    {"key": "entity_id", "label": "ID"},
                ],
                "rows": rows,
            }
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
    mock_response=lambda args, state=None: json.dumps(
        {
            "success": True,
            "entity_id": "note_mock_1",
            "entity": {"entity_id": "note_mock_1", "name": args.get("name", ""), "entity_type": "note"},
            "blocks": [{"type": "card", "title": args.get("name", "Note"), "subtitle": "created (mock)"}],
        },
        ensure_ascii=False,
    ),
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
        action_button = {
            "action_id": "crm.note.create.apply",
            "action_kind": "apply",
            "label": "Создать заметку",
            "pending_action_id": action["pending_action_id"],
            "arguments": {"pending_action_id": action["pending_action_id"]},
            "context": {"capability": "crm.note", "operation": "create"},
        }
        preview_blocks = [
            {"type": "text", "text": "Черновик создания заметки готов. Подтвердите применение."},
            {"type": "actions", "buttons": [action_button]},
        ]
        push_ui_event(
            state,
            event_type="action_previewed",
            payload={
                "action": action,
                "capability": "crm.note",
                "operation": "create",
                "blocks": preview_blocks,
            },
            event_id=f"crm-note-preview-{action['pending_action_id']}",
            version="1.0.0",
        )
        return json.dumps(
            {
                "success": True,
                "mode": "propose",
                "pending_action_id": action["pending_action_id"],
                "action": action,
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
    result_payload = action.get("result")
    if not isinstance(result_payload, dict):
        raise ValueError("Invalid apply result payload")
    entity = result_payload.get("entity")
    if not isinstance(entity, dict) or not entity.get("entity_id"):
        raise ValueError("CRM create note: invalid response")
    eid = entity["entity_id"]
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
        "entity": entity,
        "blocks": [
            {
                "type": "card",
                "title": entity.get("name") or (action.get("payload") or {}).get("name") or "Note",
                "subtitle": eid,
            },
            {"type": "actions", "buttons": [open_entity_button]},
        ],
    }
    push_ui_event(
        state,
        event_type="action_applied",
        payload={
            "action": action,
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
    mock_response=lambda args, state=None: json.dumps(
        {
            "success": True,
            "entity_id": "note_mock_combo",
            "analyze": {"entities": []},
            "blocks": [{"type": "text", "text": "Mock: заметка создана и анализ выполнен."}],
        },
        ensure_ascii=False,
    ),
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
    create_payload: dict[str, Any] = {
        "entity_type": "note",
        "namespace": ns,
        "name": name.strip(),
        "description": description,
    }
    if note_date and str(note_date).strip():
        create_payload["note_date"] = str(note_date).strip()
    client = ServiceClient()
    created = await client.post("crm", "/crm/api/v1/entities", json=create_payload)
    if not isinstance(created, dict) or not created.get("entity_id"):
        raise ValueError("create_note: missing entity_id")
    eid = created["entity_id"]

    analyze_args: dict[str, Any] = {"note_id": eid}
    if extract_entity_types:
        analyze_args["extract_entity_types"] = extract_entity_types
    if mentioned_entity_ids:
        analyze_args["mentioned_entity_ids"] = mentioned_entity_ids

    analyzed_raw = await crm_analyze_note_text._run_impl(analyze_args, state)
    analyzed = json.loads(analyzed_raw)
    if not analyzed.get("success"):
        return json.dumps(
            {
                "success": False,
                "error": analyzed.get("error", "analyze failed"),
                "entity_id": eid,
                "create": created,
                "analyze": analyzed,
            },
            ensure_ascii=False,
        )

    blocks_out: list[dict[str, Any]] = []
    for b in created.get("blocks") or []:
        if isinstance(b, dict):
            blocks_out.append(b)
    for b in analyzed.get("blocks") or []:
        if isinstance(b, dict):
            blocks_out.append(b)

    return json.dumps(
        {
            "success": True,
            "entity_id": eid,
            "entity": created.get("entity"),
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
    nid = str(note_id).strip()
    body: dict[str, Any] = {
        "note_id": nid,
        "mode": "analyze",
        "include_attachments": True,
        "check_duplicates": True,
    }
    if extract_entity_types:
        body["extract_entity_types"] = extract_entity_types
    if mentioned_entity_ids:
        body["mentioned_entity_ids"] = mentioned_entity_ids

    client = ServiceClient()
    try:
        start = await client.post(
            "crm",
            "/crm/api/v1/tasks/note-analyze",
            json=body,
            timeout=60.0,
        )
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)

    if not isinstance(start, dict):
        return json.dumps(
            {"success": False, "error": "Invalid note-analyze response"},
            ensure_ascii=False,
        )
    tid_raw = start.get("task_id")
    if not isinstance(tid_raw, str) or not tid_raw.strip():
        return json.dumps(
            {"success": False, "error": "Missing task_id in note-analyze response"},
            ensure_ascii=False,
        )
    task_id = tid_raw.strip()

    loop = asyncio.get_running_loop()
    deadline = loop.time() + 120.0
    terminal: dict[str, Any] = {}
    while loop.time() < deadline:
        try:
            row = await client.get(
                "crm",
                f"/crm/api/v1/tasks/{quote(task_id, safe='')}",
                timeout=30.0,
            )
        except ServiceClientError as exc:
            return json.dumps(
                {"success": False, "error": str(exc), "task_id": task_id},
                ensure_ascii=False,
            )
        if isinstance(row, dict):
            terminal = row
            status = row.get("status")
            if status in ("completed", "failed", "cancelled"):
                break
        await asyncio.sleep(0.35)
    else:
        return json.dumps(
            {
                "success": False,
                "error": "analyze task timeout",
                "task_id": task_id,
                "last_task": terminal,
            },
            ensure_ascii=False,
        )

    analyze_task_state = terminal.get("status")
    if analyze_task_state == "failed":
        msg = terminal.get("error_message")
        if not isinstance(msg, str) or not msg.strip():
            msg = "analyze failed"
        return json.dumps(
            {
                "success": False,
                "error": msg,
                "task_id": task_id,
                "task": terminal,
            },
            ensure_ascii=False,
        )
    if analyze_task_state == "cancelled":
        return json.dumps(
            {
                "success": False,
                "error": "analyze cancelled",
                "task_id": task_id,
                "task": terminal,
            },
            ensure_ascii=False,
        )
    if analyze_task_state != "completed":
        return json.dumps(
            {
                "success": False,
                "error": f"unexpected analyze task status: {analyze_task_state}",
                "task_id": task_id,
                "task": terminal,
            },
            ensure_ascii=False,
        )

    draft: dict[str, Any] = {}
    try:
        entity = await client.get(
            "crm",
            f"/crm/api/v1/entities/{quote(nid, safe='')}",
            timeout=60.0,
        )
    except ServiceClientError as exc:
        return json.dumps(
            {
                "success": False,
                "error": str(exc),
                "task_id": task_id,
                "task": terminal,
            },
            ensure_ascii=False,
        )
    if isinstance(entity, dict):
        attrs = entity.get("attributes")
        if isinstance(attrs, dict):
            raw_draft = attrs.get("ai_analysis_draft")
            if isinstance(raw_draft, dict):
                draft = raw_draft

    summary = "Анализ выполнен."
    entities_list = draft.get("entities")
    if isinstance(entities_list, list) and len(entities_list) > 0:
        summary = f"Найдено сущностей: {len(entities_list)}."
    else:
        td = terminal.get("data")
        if isinstance(td, dict):
            cnt = td.get("result_entities_count")
            if isinstance(cnt, int) and cnt > 0:
                summary = f"Найдено сущностей: {cnt}."

    analyze_payload: dict[str, Any] = {"task_id": task_id}
    analyze_payload.update(draft)
    terminal_data = terminal.get("data")
    if isinstance(terminal_data, dict):
        if "result_entities_count" not in analyze_payload:
            if "result_entities_count" in terminal_data:
                analyze_payload["result_entities_count"] = terminal_data["result_entities_count"]
        if "result_relationships_count" not in analyze_payload:
            if "result_relationships_count" in terminal_data:
                analyze_payload["result_relationships_count"] = terminal_data[
                    "result_relationships_count"
                ]

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
    mock_response=lambda args, state=None: args.get("blocks_json", "[]"),
)
async def push_embed_blocks(blocks_json: str, *, state: "ExecutionState") -> str:
    parsed = json.loads(blocks_json)
    if not isinstance(parsed, list):
        raise ValueError("blocks_json must be a JSON array")
    return json.dumps({"blocks": parsed}, ensure_ascii=False)


@tool(
    name="flows_read_context",
    description=(
        "Возвращает контекст flow/branch/node для Lara в сервисе flows: текущий граф, "
        "конфиг ноды и метаданные для принятия решения."
    ),
    tags=["flows", "lara", "query"],
    args_schema=FlowsReadContextArgs,
    mock_response=lambda args, state=None: json.dumps(
        {
            "success": True,
            "flow_id": args.get("flow_id", "flow_mock"),
            "branch_id": args.get("branch_id", "base"),
            "node_id": args.get("node_id"),
            "blocks": [{"type": "text", "text": "Mock: контекст flow получен."}],
        },
        ensure_ascii=False,
    ),
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

    def resolve_node_scope(flow_data: dict[str, Any], resolved_branch: str) -> dict[str, Any]:
        if resolved_branch == "base":
            nodes = flow_data.get("nodes", {})
            if not isinstance(nodes, dict):
                raise ValueError("Flow base nodes are invalid")
            return nodes
        branch_map = flow_data.get("branches")
        if not isinstance(branch_map, dict):
            branch_map = {}
        branch_payload = branch_map.get(resolved_branch)
        if not isinstance(branch_payload, dict):
            raise ValueError(
                f"Ветка '{resolved_branch}' не найдена во flow '{flow_data.get('flow_id')}'"
            )
        nodes = branch_payload.get("nodes")
        if not isinstance(nodes, dict):
            raise ValueError(f"У ветки '{resolved_branch}' нет объекта nodes")
        return nodes

    def require_node(
        flow_data: dict[str, Any], resolved_branch: str, required_node_id: str
    ) -> dict[str, Any]:
        nodes = resolve_node_scope(flow_data, resolved_branch)
        node = nodes.get(required_node_id)
        if not isinstance(node, dict):
            raise ValueError(
                f"Node '{required_node_id}' not found in branch '{resolved_branch}'"
            )
        return node

    client = ServiceClient()
    flow_config = await client.get("flows", f"/flows/api/v1/flows/{quote(flow_id, safe='')}")
    if not isinstance(flow_config, dict):
        raise ValueError("Invalid flow response")

    resolved_branch_id = normalize_branch_id(branch_id)
    selected_node = None
    if node_id:
        selected_node = require_node(flow_config, resolved_branch_id, node_id)

    payload = {
        "success": True,
        "flow_id": flow_id,
        "branch_id": resolved_branch_id,
        "node_id": node_id or None,
        "flow": flow_config,
        "node": selected_node,
        "blocks": [
            {
                "type": "card",
                "title": flow_config.get("name") or flow_id,
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
    mock_response=lambda args, state=None: json.dumps(
        {
            "success": True,
            "flow_id": args.get("flow_id", "flow_mock"),
            "branch_id": args.get("branch_id", "base"),
            "node_id": args.get("node_id", "main"),
            "mode": args.get("mode", "apply"),
            "blocks": [{"type": "text", "text": "Mock: patch ноды обработан."}],
        },
        ensure_ascii=False,
    ),
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
        patch = json.loads(patch_json)
        if not isinstance(patch, dict):
            raise ValueError("patch_json must be a JSON object")

        resolved_branch_id = normalize_branch_id(branch_id)
        action = await facade.preview_node_patch(
            flow_id=flow_id,
            node_id=node_id,
            patch=patch,
            branch_id=resolved_branch_id,
            state=state,
            idempotency_key=idempotency_key,
        )
        preview_data = action.get("preview")
        if not isinstance(preview_data, dict):
            raise ValueError("Invalid action preview payload")
        node_before = preview_data.get("node_before")
        node_after = preview_data.get("node_after")
        preview_payload: JsonDict = {
            "action": action,
            "patch_kind": "node",
            "flow_id": flow_id,
            "branch_id": resolved_branch_id,
            "node_id": node_id,
            "changes": patch,
            "open_editor": True,
        }
        apply_button = {
            "action_id": "flows.node.patch.apply",
            "action_kind": "apply",
            "label": "Применить изменение",
            "pending_action_id": action["pending_action_id"],
            "arguments": {
                "pending_action_id": action["pending_action_id"],
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
        }
        preview_blocks = [
            {"type": "text", "text": f"Черновик готов. Подтвердите применение для ноды {node_id}."},
            {"type": "actions", "buttons": [apply_button]},
        ]
        preview_payload["blocks"] = preview_blocks
        push_ui_event(
            state,
            event_type="action_previewed",
            payload=preview_payload,
            event_id=f"flows-node-preview-{action['pending_action_id']}",
            version="1.0.0",
        )
        return json.dumps(
            {
                "success": True,
                "mode": mode,
                "flow_id": flow_id,
                "branch_id": resolved_branch_id,
                "node_id": node_id,
                "pending_action_id": action["pending_action_id"],
                "action": action,
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
    target = action.get("target")
    if not isinstance(target, dict):
        raise ValueError("Invalid pending node patch target payload")
    flow_resolved = target.get("flow_id")
    node_resolved = target.get("node_id")
    if not isinstance(flow_resolved, str) or not flow_resolved.strip():
        raise ValueError("Pending action target.flow_id is missing")
    if not isinstance(node_resolved, str) or not node_resolved.strip():
        raise ValueError("Pending action target.node_id is missing")
    resolved_branch_id = normalize_branch_id(target.get("branch_id"))

    preview_data = action.get("preview")
    if not isinstance(preview_data, dict):
        raise ValueError("Invalid action preview payload")
    node_before = preview_data.get("node_before")
    node_after = preview_data.get("node_after")
    action_payload = action.get("payload")
    patch_restored: dict[str, Any]
    if isinstance(action_payload, dict) and isinstance(action_payload.get("patch"), dict):
        patch_restored = action_payload["patch"]
    else:
        patch_restored = {}
    event_payload: JsonDict = {
        "action": action,
        "patch_kind": "node",
        "flow_id": flow_resolved,
        "branch_id": resolved_branch_id,
        "node_id": node_resolved,
        "changes": patch_restored,
        "open_editor": True,
    }
    push_ui_event(
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
    mock_response=lambda args, state=None: json.dumps(
        {
            "success": True,
            "flow_id": args.get("flow_id", "flow_mock"),
            "mode": args.get("mode", "apply"),
            "blocks": [{"type": "text", "text": "Mock: patch flow обработан."}],
        },
        ensure_ascii=False,
    ),
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
        patch = json.loads(patch_json)
        if not isinstance(patch, dict):
            raise ValueError("patch_json must be a JSON object")

        allowed_fields = {"name", "description", "tags", "variables"}
        unsupported = sorted(set(patch.keys()) - allowed_fields)
        if unsupported:
            raise ValueError(
                f"Unsupported flow patch fields: {', '.join(unsupported)}. "
                "Allowed: name, description, tags, variables."
            )

        action = await facade.preview_flow_patch(
            flow_id=flow_id,
            patch=patch,
            state=state,
            idempotency_key=idempotency_key,
        )
        preview_data = action.get("preview")
        if not isinstance(preview_data, dict):
            raise ValueError("Invalid action preview payload")
        flow_before = preview_data.get("flow_before")
        flow_after = preview_data.get("flow_after")
        preview_payload: JsonDict = {
            "action": action,
            "patch_kind": "flow",
            "flow_id": flow_id,
            "flow_changes": patch,
            "open_editor": True,
        }
        apply_button = {
            "action_id": "flows.flow.patch.apply",
            "action_kind": "apply",
            "label": "Применить изменение",
            "pending_action_id": action["pending_action_id"],
            "arguments": {"pending_action_id": action["pending_action_id"], "flow_id": flow_id},
            "context": {"flow_id": flow_id, "patch_kind": "flow"},
        }
        preview_blocks = [
            {"type": "text", "text": f"Черновик готов. Подтвердите применение для flow {flow_id}."},
            {"type": "actions", "buttons": [apply_button]},
        ]
        preview_payload["blocks"] = preview_blocks
        push_ui_event(
            state,
            event_type="action_previewed",
            payload=preview_payload,
            event_id=f"flows-flow-preview-{action['pending_action_id']}",
            version="1.0.0",
        )
        return json.dumps(
            {
                "success": True,
                "mode": mode,
                "flow_id": flow_id,
                "pending_action_id": action["pending_action_id"],
                "action": action,
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
    target = action.get("target")
    if not isinstance(target, dict):
        raise ValueError("Invalid pending flow patch target payload")
    flow_resolved = target.get("flow_id")
    if not isinstance(flow_resolved, str) or not flow_resolved.strip():
        raise ValueError("Pending action target.flow_id is missing")

    preview_data = action.get("preview")
    if not isinstance(preview_data, dict):
        raise ValueError("Invalid action preview payload")
    flow_before = preview_data.get("flow_before")
    flow_after = preview_data.get("flow_after")

    payload = action.get("payload")
    patch_restored: dict[str, Any]
    if isinstance(payload, dict) and isinstance(payload.get("patch"), dict):
        patch_restored = payload["patch"]
    else:
        patch_restored = {}

    apply_payload: JsonDict = {
        "action": action,
        "patch_kind": "flow",
        "flow_id": flow_resolved,
        "flow_changes": patch_restored,
        "open_editor": True,
    }
    push_ui_event(
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
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    entity_id: str = Field(..., min_length=1, description="entity_id CRM.")


class CrmCreateEntityArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    entity_type: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    entity_subtype: str | None = None
    namespace: str | None = None
    description: str | None = None
    attributes: dict[str, Any] | None = None
    tags: list[str] | None = None


class CrmCreateRelationshipArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_entity_id: str = Field(..., min_length=1)
    target_entity_id: str = Field(..., min_length=1)
    relationship_type: str = Field(..., min_length=1)
    namespace: str | None = None
    weight: float = Field(default=1.0, ge=0.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class CrmListEntityTypesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    namespace: str | None = None


class CrmDailySummaryArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    date: str = Field(..., min_length=10, max_length=10, description="YYYY-MM-DD.")
    namespace: str | None = None
    force_rebuild: bool = False


@tool(
    name="crm_get_entity",
    description=(
        "Загружает сущность CRM по entity_id (GET /crm/api/v1/entities/{id}). "
        "Возвращает JSON и card-блок для чата."
    ),
    tags=["crm", "lara"],
    args_schema=CrmGetEntityArgs,
    mock_response=lambda args, state=None: json.dumps(
        {
            "success": True,
            "entity": {"entity_id": args.get("entity_id"), "name": "Mock", "entity_type": "note"},
        },
        ensure_ascii=False,
    ),
)
async def crm_get_entity(entity_id: str, *, state: "ExecutionState") -> str:
    cid = entity_id.strip()
    if not cid:
        raise ValueError("entity_id is required")
    client = ServiceClient()
    try:
        raw = await client.get("crm", f"/crm/api/v1/entities/{quote(cid, safe='')}")
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    if not isinstance(raw, dict):
        return json.dumps({"success": False, "error": "crm_get_entity: invalid response"}, ensure_ascii=False)
    blocks: list[dict[str, Any]] = [
        {
            "type": "card",
            "title": raw.get("name") or cid,
            "subtitle": str(raw.get("entity_type") or ""),
        },
    ]
    return json.dumps({"success": True, "entity": raw, "blocks": blocks}, ensure_ascii=False)


@tool(
    name="crm_create_entity",
    description=(
        "Создаёт сущность CRM (POST /crm/api/v1/entities): entity_type и name обязательны. "
        "namespace берётся из active_namespace если не указан. Для confirm-first заметок используй crm_create_note."
    ),
    tags=["crm", "lara", "mutation"],
    args_schema=CrmCreateEntityArgs,
    mock_response=lambda args, state=None: json.dumps(
        {"success": True, "entity": {"entity_id": "mock-e1", "name": args.get("name")}},
        ensure_ascii=False,
    ),
)
async def crm_create_entity(
    entity_type: str,
    name: str,
    entity_subtype: str | None = None,
    namespace: str | None = None,
    description: str | None = None,
    attributes: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    *,
    state: "ExecutionState",
) -> str:
    ns = namespace if namespace and str(namespace).strip() else _require_context_namespace()
    body: dict[str, Any] = {
        "entity_type": entity_type.strip(),
        "name": name.strip(),
        "namespace": ns,
    }
    if entity_subtype and str(entity_subtype).strip():
        body["entity_subtype"] = entity_subtype.strip()
    if description and str(description).strip():
        body["description"] = description.strip()
    if attributes:
        body["attributes"] = attributes
    if tags:
        body["tags"] = tags
    client = ServiceClient()
    try:
        created = await client.post("crm", "/crm/api/v1/entities", json=body)
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    if not isinstance(created, dict) or not created.get("entity_id"):
        return json.dumps({"success": False, "error": "crm_create_entity: invalid response"}, ensure_ascii=False)
    blocks = [{"type": "card", "title": created.get("name") or "Entity", "subtitle": created["entity_id"]}]
    return json.dumps({"success": True, "entity": created, "blocks": blocks}, ensure_ascii=False)


@tool(
    name="crm_create_relationship",
    description=(
        "Создаёт связь (POST /crm/api/v1/relationships между source и target)."
    ),
    tags=["crm", "lara", "mutation", "graph"],
    args_schema=CrmCreateRelationshipArgs,
    mock_response=lambda args, state=None: json.dumps(
        {"success": True, "relationship_id": "rel-mock"},
        ensure_ascii=False,
    ),
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
    ns = namespace if namespace and str(namespace).strip() else _require_context_namespace()
    payload_obj = {
        "source_entity_id": source_entity_id.strip(),
        "target_entity_id": target_entity_id.strip(),
        "relationship_type": relationship_type.strip(),
        "namespace": ns,
        "weight": weight,
        "confidence": confidence,
    }
    client = ServiceClient()
    try:
        raw = await client.post("crm", "/crm/api/v1/relationships", json=payload_obj)
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    if not isinstance(raw, dict) or not raw.get("relationship_id"):
        return json.dumps({"success": False, "error": "crm_create_relationship: invalid response"}, ensure_ascii=False)
    bid = raw["relationship_id"]
    txt = (
        f"Связь {relationship_type.strip()} создана ({bid}): "
        f"{payload_obj['source_entity_id']} → {payload_obj['target_entity_id']}."
    )
    blocks: list[dict[str, Any]] = [{"type": "text", "text": txt}]
    return json.dumps({"success": True, "relationship": raw, "blocks": blocks}, ensure_ascii=False)


@tool(
    name="crm_list_entity_types",
    description=("Каталог типов для namespace (GET /crm/api/v1/entity-types?namespace=)."),
    tags=["crm", "lara"],
    args_schema=CrmListEntityTypesArgs,
    mock_response=lambda args, state=None: json.dumps(
        {"success": True, "items": [{"type_id": "note"}], "blocks": [{"type": "text", "text": "mock"}]},
        ensure_ascii=False,
    ),
)
async def crm_list_entity_types(
    namespace: str | None = None,
    *,
    state: "ExecutionState",
) -> str:
    ns = namespace if namespace and str(namespace).strip() else _require_context_namespace()
    client = ServiceClient()
    qp = quote(ns, safe="")
    path = f"/crm/api/v1/entity-types?namespace={qp}"
    try:
        raw = await client.get("crm", path)
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    if not isinstance(raw, dict):
        return json.dumps({"success": False, "error": "crm_list_entity_types: invalid response envelope"}, ensure_ascii=False)
    rows_payload = raw.get("items")
    if not isinstance(rows_payload, list):
        return json.dumps({"success": False, "error": "crm_list_entity_types: invalid items"}, ensure_ascii=False)
    compact = [
        {"type_id": x.get("type_id"), "name": x.get("name"), "parent_type_id": x.get("parent_type_id")}
        for x in rows_payload
        if isinstance(x, dict)
    ]
    lines = compact[:80]
    blocks: list[dict[str, Any]] = [
        {
            "type": "table",
            "title": "Типы сущностей",
            "columns": [
                {"key": "type_id", "label": "type_id"},
                {"key": "name", "label": "Имя"},
                {"key": "parent_type_id", "label": "Родитель"},
            ],
            "rows": lines,
        }
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
    mock_response=lambda args, state=None: json.dumps(
        {"success": True, "summary": "mock", "blocks": [{"type": "text", "text": "mock"}]},
        ensure_ascii=False,
    ),
)
async def crm_daily_summary(
    date: str,
    namespace: str | None = None,
    force_rebuild: bool = False,
    *,
    state: "ExecutionState",
) -> str:
    d_raw = date.strip()
    if not d_raw:
        raise ValueError("date is required")
    body: dict[str, Any] = {"date": d_raw, "force_rebuild": bool(force_rebuild)}
    ns_clear = namespace if namespace and str(namespace).strip() else None
    if ns_clear:
        body["namespace"] = ns_clear
    client = ServiceClient()
    try:
        raw = await client.post("crm", "/crm/api/v1/entities/daily-summary", json=body)
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)
    if not isinstance(raw, dict):
        return json.dumps({"success": False, "error": "crm_daily_summary: invalid response"}, ensure_ascii=False)
    summary_text = raw.get("summary")
    if isinstance(summary_text, str) and summary_text.strip():
        main = summary_text.strip()
    else:
        main = json.dumps(raw, ensure_ascii=False)[:2500]
    blocks: list[dict[str, Any]] = [{"type": "text", "text": main}]
    return json.dumps({"success": True, "response": raw, "blocks": blocks}, ensure_ascii=False)
