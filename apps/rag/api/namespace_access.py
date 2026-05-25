"""
Проверка, что RAG namespace зарегистрирован для текущей компании (репозиторий namespaces).
"""

from __future__ import annotations

import json

from fastapi import HTTPException

from core.context import get_context
from core.types import JsonObject, JsonValue

from ..container import RAGContainer

_MAX_METADATA_JSON_BYTES = 32 * 1024
_MAX_METADATA_DEPTH = 12
_MAX_INGEST_TEXT_CHARS = 512_000


async def require_registered_rag_namespace(namespace_id: str, container: RAGContainer) -> None:
    context = get_context()
    if context is None or context.active_company is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    company_id = context.active_company.company_id
    ns = await container.namespace_repository.get(namespace_id)
    if ns is None:
        raise HTTPException(status_code=404, detail=f"Namespace '{namespace_id}' not found")
    if ns.company_id != company_id:
        raise HTTPException(status_code=403, detail="Namespace does not belong to current company")


def validate_rag_user_metadata(metadata: JsonObject) -> None:
    def walk(value: JsonValue, depth: int) -> None:
        if depth > _MAX_METADATA_DEPTH:
            raise HTTPException(status_code=400, detail="metadata JSON nesting too deep")
        if isinstance(value, dict):
            for item in value.values():
                walk(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                walk(item, depth + 1)

    walk(metadata, 0)
    raw = json.dumps(metadata, ensure_ascii=False)
    if len(raw.encode("utf-8")) > _MAX_METADATA_JSON_BYTES:
        raise HTTPException(status_code=400, detail="metadata JSON exceeds size limit")


def validate_ingest_text_body(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        raise HTTPException(status_code=400, detail="text must not be empty")
    if len(stripped) > _MAX_INGEST_TEXT_CHARS:
        raise HTTPException(status_code=400, detail="text exceeds maximum length")
    return stripped
