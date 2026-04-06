"""
Проверка, что RAG namespace зарегистрирован для текущей компании (репозиторий namespaces).
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException

from core.context import get_context

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


def validate_rag_user_metadata(metadata: dict[str, Any]) -> None:
    if not isinstance(metadata, dict):
        raise HTTPException(status_code=400, detail="metadata must be an object")

    def walk(obj: Any, depth: int) -> None:
        if depth > _MAX_METADATA_DEPTH:
            raise HTTPException(status_code=400, detail="metadata JSON nesting too deep")
        if isinstance(obj, dict):
            for v in obj.values():
                walk(v, depth + 1)
        elif isinstance(obj, list):
            for v in obj:
                walk(v, depth + 1)

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
