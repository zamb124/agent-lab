"""Проверка RAG namespace и входных метаданных — без HTTPException."""

from __future__ import annotations

import json

from apps.rag.container import RAGContainer
from apps.rag.errors import RagAccessDeniedError, RagNotFoundError
from core.authz.errors import AuthzDenied
from core.authz.models import AuthzObject
from core.context import get_context
from core.types import JsonObject, JsonValue

_MAX_METADATA_JSON_BYTES = 32 * 1024
_MAX_METADATA_DEPTH = 12
_MAX_INGEST_TEXT_CHARS = 512_000


async def require_registered_rag_namespace(namespace_id: str, container: RAGContainer) -> None:
    context = get_context()
    if context is None or context.active_company is None:
        raise RagAccessDeniedError("Компания не выбрана")
    company_id = context.active_company.company_id
    try:
        await container.authz_service.require_can_view(
            AuthzObject.platform_namespace(company_id, namespace_id)
        )
    except AuthzDenied as exc:
        raise RagAccessDeniedError("Forbidden") from exc
    ns = await container.namespace_repository.get(namespace_id)
    if ns is None:
        raise RagNotFoundError(f"Namespace '{namespace_id}' not found")


def validate_rag_user_metadata(metadata: JsonObject) -> None:
    def walk(value: JsonValue, depth: int) -> None:
        if depth > _MAX_METADATA_DEPTH:
            raise ValueError("metadata JSON nesting too deep")
        if isinstance(value, dict):
            for item in value.values():
                walk(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                walk(item, depth + 1)

    walk(metadata, 0)
    raw = json.dumps(metadata, ensure_ascii=False)
    if len(raw.encode("utf-8")) > _MAX_METADATA_JSON_BYTES:
        raise ValueError("metadata JSON exceeds size limit")


def validate_ingest_text_body(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        raise ValueError("text must not be empty")
    if len(stripped) > _MAX_INGEST_TEXT_CHARS:
        raise ValueError("text exceeds maximum length")
    return stripped
