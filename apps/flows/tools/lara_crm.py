"""
Тулы Lara для CRM через ServiceClient (тот же REST, что у UI). Требуют контекст пользователя в worker.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import quote

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from apps.flows.src.eval.state_utils import push_ui_event
from apps.flows.src.tools import tool
from core.clients.service_client import ServiceClient, ServiceClientError
from core.context import get_context


def _require_context_namespace() -> str:
    ctx = get_context()
    if ctx is None:
        raise RuntimeError("Context is not set")
    return ctx.active_namespace or "default"


def _analyze_mock(args: dict, state: Any = None) -> str:
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
    """Аргументы GET /crm/api/v1/entities/search — та же семантика, что поле «Поиск» в UI."""

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
    entity_type: Optional[str] = Field(
        None,
        description="Только если пользователь явно ограничил тип сущности; иначе не передавай (null).",
    )
    entity_subtype: Optional[str] = Field(
        None,
        description="Только при явном запросе подтипа; иначе null.",
    )
    namespace: Optional[str] = Field(
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

    name: str = Field(..., min_length=1, description="Заголовок заметки.")
    description: str = Field(..., min_length=1, description="Текст заметки (тело).")
    note_date: Optional[str] = Field(
        None,
        description="Дата заметки YYYY-MM-DD; только если уместно по смыслу.",
    )
    namespace: Optional[str] = Field(
        None,
        description="Пространство имён CRM; null — из контекста сессии.",
    )

    @field_validator("note_date", "namespace", mode="before")
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
    extract_entity_types: Optional[List[str]] = Field(
        None,
        description="Ограничить извлечение указанными типами сущностей; иначе не передавай.",
    )
    mentioned_entity_ids: Optional[List[str]] = Field(
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
    note_date: Optional[str] = Field(None, description="Дата YYYY-MM-DD; опционально.")
    extract_entity_types: Optional[List[str]] = Field(
        None,
        description="Типы сущностей для извлечения при анализе; опционально.",
    )
    mentioned_entity_ids: Optional[List[str]] = Field(
        None,
        description="Упомянутые id для контекста анализа; опционально.",
    )
    namespace: Optional[str] = Field(None, description="Пространство имён; null — из контекста.")

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
    skill_id: Optional[str] = Field(
        None,
        description="ID skill. Для базового графа передай base или оставь пустым.",
    )
    node_id: Optional[str] = Field(
        None,
        description="ID ноды в выбранном графе. Если не передан, вернётся только контекст flow/skill.",
    )


class FlowsPatchNodeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    flow_id: str = Field(..., min_length=1, description="ID flow.")
    node_id: str = Field(..., min_length=1, description="ID ноды для изменения.")
    patch_json: str = Field(
        ...,
        min_length=2,
        description="JSON-объект изменений ноды. Пример: {\"prompt\": \"...\"}.",
    )
    skill_id: Optional[str] = Field(
        None,
        description="ID skill. Для base можно не передавать.",
    )
    mode: Literal["propose", "apply"] = Field(
        "apply",
        description="propose — показать патч без сохранения; apply — сохранить в flow.",
    )


class FlowsPatchFlowArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    flow_id: str = Field(..., min_length=1, description="ID flow.")
    patch_json: str = Field(
        ...,
        min_length=2,
        description=(
            "JSON-объект изменений flow. Разрешённые поля: name, description, tags, variables."
        ),
    )
    mode: Literal["propose", "apply"] = Field(
        "apply",
        description="propose — показать патч без сохранения; apply — сохранить в flow.",
    )


def _compact_entity_hit(raw: Dict[str, Any]) -> Dict[str, Any]:
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
    query: Optional[str] = None,
    search: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_subtype: Optional[str] = None,
    namespace: Optional[str] = None,
    limit: int = 100,
    state: Optional[dict] = None,
) -> str:
    q = (query or "").strip() if query else ""
    if not q and search:
        q = str(search).strip()
    if not q:
        raise ValueError(
            "Нужен непустой параметр query — короткая строка семантического поиска (ключевые слова из запроса пользователя)."
        )
    ns = namespace if namespace else _require_context_namespace()
    params: Dict[str, Any] = {
        "query": q,
        "namespace": ns,
        "limit": max(1, min(1000, int(limit))),
    }
    if entity_type:
        params["entity_type"] = entity_type
    if entity_subtype:
        params["entity_subtype"] = entity_subtype

    client = ServiceClient()
    try:
        raw_response = await client.get("crm", "/crm/api/v1/entities/search", params=params)
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)

    if not isinstance(raw_response, dict) or "items" not in raw_response:
        return json.dumps({"success": False, "error": "CRM search: invalid response"}, ensure_ascii=False)

    hits = [_compact_entity_hit(x) for x in raw_response["items"] if isinstance(x, dict)]
    summary = f"Найдено сущностей: {len(hits)}."
    blocks: List[Dict[str, Any]] = [{"type": "text", "text": summary}]
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
    name: str,
    description: str,
    note_date: Optional[str] = None,
    namespace: Optional[str] = None,
    state: Optional[dict] = None,
) -> str:
    ns = namespace if namespace and str(namespace).strip() else _require_context_namespace()
    payload: Dict[str, Any] = {
        "entity_type": "note",
        "namespace": ns,
        "name": name.strip(),
        "description": description,
    }
    if note_date and str(note_date).strip():
        payload["note_date"] = str(note_date).strip()

    client = ServiceClient()
    try:
        entity = await client.post("crm", "/crm/api/v1/entities", json=payload)
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)

    if not isinstance(entity, dict) or not entity.get("entity_id"):
        return json.dumps({"success": False, "error": "CRM create note: invalid response"}, ensure_ascii=False)

    eid = entity["entity_id"]
    blocks = [
        {
            "type": "card",
            "title": entity.get("name") or name,
            "subtitle": eid,
        },
        {
            "type": "actions",
            "buttons": [
                {
                    "action_id": "open_entity",
                    "label": "Открыть сущность",
                    "payload": {"entity_id": eid},
                }
            ],
        },
    ]
    return json.dumps(
        {"success": True, "entity_id": eid, "entity": entity, "blocks": blocks},
        ensure_ascii=False,
    )


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
    note_date: Optional[str] = None,
    extract_entity_types: Optional[List[str]] = None,
    mentioned_entity_ids: Optional[List[str]] = None,
    namespace: Optional[str] = None,
    state: Optional[dict] = None,
) -> str:
    create_args: Dict[str, Any] = {"name": name, "description": description}
    if note_date and str(note_date).strip():
        create_args["note_date"] = str(note_date).strip()
    if namespace and str(namespace).strip():
        create_args["namespace"] = str(namespace).strip()

    created_raw = await crm_create_note._run_impl(create_args, state)
    created = json.loads(created_raw)
    if not created.get("success"):
        return created_raw

    eid = created.get("entity_id")
    if not eid or not isinstance(eid, str):
        return json.dumps({"success": False, "error": "create_note: missing entity_id"}, ensure_ascii=False)

    analyze_args: Dict[str, Any] = {"note_id": eid}
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

    blocks_out: List[Dict[str, Any]] = []
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
    extract_entity_types: Optional[List[str]] = None,
    mentioned_entity_ids: Optional[List[str]] = None,
    state: Optional[dict] = None,
) -> str:
    body: Dict[str, Any] = {}
    if extract_entity_types:
        body["extract_entity_types"] = extract_entity_types
    if mentioned_entity_ids:
        body["mentioned_entity_ids"] = mentioned_entity_ids

    client = ServiceClient()
    path = f"/crm/api/v1/entities/notes/{quote(str(note_id), safe='')}/analyze"
    try:
        result = await client.post("crm", path, json=body)
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)

    summary = "Анализ выполнен."
    if isinstance(result, dict):
        ents = result.get("entities") or []
        if isinstance(ents, list) and len(ents) > 0:
            summary = f"Найдено сущностей: {len(ents)}."

    blocks = [
        {"type": "text", "text": summary},
        {
            "type": "actions",
            "buttons": [
                {
                    "action_id": "open_entity",
                    "label": "Открыть заметку",
                    "payload": {"entity_id": note_id},
                }
            ],
        },
    ]
    return json.dumps(
        {"success": True, "analyze": result, "blocks": blocks},
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
async def push_embed_blocks(blocks_json: str, state: Optional[dict] = None) -> str:
    parsed = json.loads(blocks_json)
    if not isinstance(parsed, list):
        raise ValueError("blocks_json must be a JSON array")
    return json.dumps({"blocks": parsed}, ensure_ascii=False)


@tool(
    name="flows_read_context",
    description=(
        "Возвращает контекст flow/skill/node для Lara в сервисе flows: текущий граф, "
        "конфиг ноды и метаданные для принятия решения."
    ),
    tags=["flows", "lara", "query"],
    args_schema=FlowsReadContextArgs,
    mock_response=lambda args, state=None: json.dumps(
        {
            "success": True,
            "flow_id": args.get("flow_id", "flow_mock"),
            "skill_id": args.get("skill_id", "base"),
            "node_id": args.get("node_id"),
            "blocks": [{"type": "text", "text": "Mock: контекст flow получен."}],
        },
        ensure_ascii=False,
    ),
)
async def flows_read_context(
    flow_id: str,
    skill_id: Optional[str] = None,
    node_id: Optional[str] = None,
    state: Optional[dict] = None,
) -> str:
    def normalize_skill_id(raw_skill_id: Optional[str]) -> str:
        if raw_skill_id is None:
            return "base"
        cleaned_skill_id = raw_skill_id.strip()
        if not cleaned_skill_id or cleaned_skill_id == "default":
            return "base"
        return cleaned_skill_id

    def resolve_node_scope(flow_data: Dict[str, Any], resolved_skill: str) -> Dict[str, Any]:
        if resolved_skill == "base":
            nodes = flow_data.get("nodes", {})
            if not isinstance(nodes, dict):
                raise ValueError("Flow base nodes are invalid")
            return nodes
        skills = flow_data.get("skills") or {}
        skill = skills.get(resolved_skill)
        if not isinstance(skill, dict):
            raise ValueError(f"Skill '{resolved_skill}' not found in flow '{flow_data.get('flow_id')}'")
        nodes = skill.get("nodes")
        if not isinstance(nodes, dict):
            raise ValueError(f"Skill '{resolved_skill}' has no nodes")
        return nodes

    def require_node(flow_data: Dict[str, Any], resolved_skill: str, required_node_id: str) -> Dict[str, Any]:
        nodes = resolve_node_scope(flow_data, resolved_skill)
        node = nodes.get(required_node_id)
        if not isinstance(node, dict):
            raise ValueError(f"Node '{required_node_id}' not found in skill '{resolved_skill}'")
        return node

    client = ServiceClient()
    flow_config = await client.get("flows", f"/flows/api/v1/flows/{quote(flow_id, safe='')}")
    if not isinstance(flow_config, dict):
        raise ValueError("Invalid flow response")

    resolved_skill_id = normalize_skill_id(skill_id)
    selected_node = None
    if node_id:
        selected_node = require_node(flow_config, resolved_skill_id, node_id)

    payload = {
        "success": True,
        "flow_id": flow_id,
        "skill_id": resolved_skill_id,
        "node_id": node_id or None,
        "flow": flow_config,
        "node": selected_node,
        "blocks": [
            {
                "type": "card",
                "title": flow_config.get("name") or flow_id,
                "subtitle": f"Flow: {flow_id} | Skill: {resolved_skill_id}",
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
            "skill_id": args.get("skill_id", "base"),
            "node_id": args.get("node_id", "main"),
            "mode": args.get("mode", "apply"),
            "blocks": [{"type": "text", "text": "Mock: patch ноды обработан."}],
        },
        ensure_ascii=False,
    ),
)
async def flows_patch_node(
    flow_id: str,
    node_id: str,
    patch_json: str,
    skill_id: Optional[str] = None,
    mode: Literal["propose", "apply"] = "apply",
    state: Optional[dict] = None,
) -> str:
    def normalize_skill_id(raw_skill_id: Optional[str]) -> str:
        if raw_skill_id is None:
            return "base"
        cleaned_skill_id = raw_skill_id.strip()
        if not cleaned_skill_id or cleaned_skill_id == "default":
            return "base"
        return cleaned_skill_id

    def resolve_node_scope(flow_data: Dict[str, Any], resolved_skill: str) -> Dict[str, Any]:
        if resolved_skill == "base":
            nodes = flow_data.get("nodes", {})
            if not isinstance(nodes, dict):
                raise ValueError("Flow base nodes are invalid")
            return nodes
        skills = flow_data.get("skills") or {}
        skill = skills.get(resolved_skill)
        if not isinstance(skill, dict):
            raise ValueError(f"Skill '{resolved_skill}' not found in flow '{flow_data.get('flow_id')}'")
        nodes = skill.get("nodes")
        if not isinstance(nodes, dict):
            raise ValueError(f"Skill '{resolved_skill}' has no nodes")
        return nodes

    def require_node(flow_data: Dict[str, Any], resolved_skill: str, required_node_id: str) -> Dict[str, Any]:
        nodes = resolve_node_scope(flow_data, resolved_skill)
        node = nodes.get(required_node_id)
        if not isinstance(node, dict):
            raise ValueError(f"Node '{required_node_id}' not found in skill '{resolved_skill}'")
        return node

    patch = json.loads(patch_json)
    if not isinstance(patch, dict):
        raise ValueError("patch_json must be a JSON object")

    resolved_skill_id = normalize_skill_id(skill_id)
    client = ServiceClient()
    flow_config = await client.get("flows", f"/flows/api/v1/flows/{quote(flow_id, safe='')}")
    if not isinstance(flow_config, dict):
        raise ValueError("Invalid flow response")

    node_before = require_node(flow_config, resolved_skill_id, node_id)
    node_after = {**node_before, **patch}
    event_type = "patch_applied" if mode == "apply" else "patch_proposed"
    event_payload = {
        "patch_kind": "node",
        "flow_id": flow_id,
        "skill_id": resolved_skill_id,
        "node_id": node_id,
        "changes": patch,
        "open_editor": True,
    }
    summary = (
        f"Patch для ноды {node_id} отправлен в UI."
        if mode == "apply"
        else f"Patch подготовлен для ноды {node_id}."
    )
    push_ui_event(
        state,
        event_type=event_type,
        payload=event_payload,
        event_id=f"flows-node-{flow_id}-{resolved_skill_id}-{node_id}-{mode}",
        version="1.0",
    )

    return json.dumps(
        {
            "success": True,
            "mode": mode,
            "flow_id": flow_id,
            "skill_id": resolved_skill_id,
            "node_id": node_id,
            "node_before": node_before,
            "node_after": node_after,
            "blocks": [
                {"type": "text", "text": summary},
                {
                    "type": "actions",
                    "buttons": [
                        {
                            "action_id": f"lara:{event_type}",
                            "label": "Открыть результат в редакторе",
                            "payload": event_payload,
                        }
                    ],
                },
            ],
        },
        ensure_ascii=False,
    )


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
    flow_id: str,
    patch_json: str,
    mode: Literal["propose", "apply"] = "apply",
    state: Optional[dict] = None,
) -> str:
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

    client = ServiceClient()
    flow_config = await client.get("flows", f"/flows/api/v1/flows/{quote(flow_id, safe='')}")
    if not isinstance(flow_config, dict):
        raise ValueError("Invalid flow response")

    flow_after = dict(flow_config)
    flow_after.update(patch)
    event_type = "patch_applied" if mode == "apply" else "patch_proposed"
    summary = (
        f"Patch для flow {flow_id} отправлен в UI."
        if mode == "apply"
        else f"Patch подготовлен для flow {flow_id}."
    )
    event_payload = {
        "patch_kind": "flow",
        "flow_id": flow_id,
        "flow_changes": patch,
        "open_editor": True,
    }
    push_ui_event(
        state,
        event_type=event_type,
        payload=event_payload,
        event_id=f"flows-flow-{flow_id}-{mode}",
        version="1.0",
    )
    return json.dumps(
        {
            "success": True,
            "mode": mode,
            "flow_id": flow_id,
            "flow_before": flow_config,
            "flow_after": flow_after,
            "blocks": [
                {"type": "text", "text": summary},
                {
                    "type": "actions",
                    "buttons": [
                        {
                            "action_id": f"lara:{event_type}",
                            "label": "Открыть результат в редакторе",
                            "payload": event_payload,
                        }
                    ],
                },
            ],
        },
        ensure_ascii=False,
    )
