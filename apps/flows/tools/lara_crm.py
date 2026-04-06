"""
Тулы Lara для CRM через ServiceClient (тот же REST, что у UI). Требуют контекст пользователя в worker.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

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
        "Семантический поиск по сущностям CRM (как строка «Поиск» в списке сущностей: по смыслу имени и описания). "
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
        raw_list = await client.get("crm", "/crm/api/v1/entities/search", params=params)
    except ServiceClientError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)

    if not isinstance(raw_list, list):
        return json.dumps({"success": False, "error": "CRM search: invalid response"}, ensure_ascii=False)

    hits = [_compact_entity_hit(x) for x in raw_list if isinstance(x, dict)]
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

    analyze_args: Dict[str, Any] = {"text": description, "note_id": eid}
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
        "Запускает AI-анализ текста заметки в CRM (извлечение сущностей). "
        "Обязательно: text и note_id. Параметр namespace обычно не передавай — берётся из сессии CRM; "
        "если всё же передан непустой, используется он. Возвращает JSON с кратким summary и blocks для чата."
    ),
    tags=["crm", "lara", "ai"],
    mock_response=_analyze_mock,
)
async def crm_analyze_note_text(
    text: str,
    note_id: str,
    extract_entity_types: Optional[List[str]] = None,
    mentioned_entity_ids: Optional[List[str]] = None,
    namespace: Optional[str] = None,
    state: Optional[dict] = None,
) -> str:
    ns = namespace if namespace and str(namespace).strip() else _require_context_namespace()
    body: Dict[str, Any] = {
        "text": text,
        "namespace": ns,
    }
    if extract_entity_types:
        body["extract_entity_types"] = extract_entity_types
    if mentioned_entity_ids:
        body["mentioned_entity_ids"] = mentioned_entity_ids

    client = ServiceClient()
    path = f"/crm/api/v1/entities/analyze?note_id={quote(str(note_id), safe='')}"
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
    mock_response=lambda args, state=None: args.get("blocks_json", "[]"),
)
async def push_embed_blocks(blocks_json: str, state: Optional[dict] = None) -> str:
    parsed = json.loads(blocks_json)
    if not isinstance(parsed, list):
        raise ValueError("blocks_json must be a JSON array")
    return json.dumps({"blocks": parsed}, ensure_ascii=False)
