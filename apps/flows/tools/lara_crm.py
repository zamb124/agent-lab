"""
Тулы Lara для CRM через ServiceClient (тот же REST, что у UI). Требуют контекст пользователя в worker.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

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
        entity = await client.post("crm", "/api/v1/entities", json=payload)
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
    name="crm_analyze_note_text",
    description=(
        "Запускает AI-анализ текста заметки в CRM (извлечение сущностей). "
        "Передай text и note_id (id заметки). Возвращает JSON с кратким summary и blocks для чата."
    ),
    tags=["crm", "lara", "ai"],
    mock_response=_analyze_mock,
)
async def crm_analyze_note_text(
    text: str,
    note_id: str,
    extract_entity_types: Optional[List[str]] = None,
    mentioned_entity_ids: Optional[List[str]] = None,
    state: Optional[dict] = None,
) -> str:
    ns = _require_context_namespace()
    body: Dict[str, Any] = {
        "text": text,
        "namespace": ns,
    }
    if extract_entity_types:
        body["extract_entity_types"] = extract_entity_types
    if mentioned_entity_ids:
        body["mentioned_entity_ids"] = mentioned_entity_ids

    client = ServiceClient()
    path = f"/api/v1/entities/analyze?note_id={note_id}"
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
