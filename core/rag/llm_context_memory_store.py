"""RAG-backed episodic memory store for the platform LLM context layer."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from core.context import get_context
from core.db.repositories.namespace_repository import NamespaceRepository
from core.llm_context import (
    LLM_CONTEXT_MEMORY_RECALL_CONTENT_METADATA_KEY,
    LLMContextMemoryEpisode,
    LLMContextMemoryRecallRequest,
    LLMContextMemoryRecord,
)
from core.models.identity_models import Namespace
from core.rag.models import RAGSearchResult
from core.rag.rag_resource_bind import RagResourceBindParams
from core.rag.repository import RAGRepository

_DEFAULT_NAMESPACE_PREFIX = "llm-memory"


class RAGLLMContextMemoryStore:
    """Persist and recall LLM context memory episodes through the platform RAG index."""

    def __init__(
        self,
        *,
        repository: RAGRepository,
        namespace_repository: NamespaceRepository | None = None,
        namespace_id: str | None = None,
        provider: str = "pgvector",
    ) -> None:
        self.repository = repository
        self.namespace_repository = namespace_repository
        self.namespace_id = namespace_id
        self.provider = provider

    async def write_episode(self, episode: LLMContextMemoryEpisode) -> str:
        company_id = _active_company_id()
        namespace_id = self._namespace_id(company_id)
        await self._ensure_namespace(namespace_id, company_id)
        metadata = _episode_metadata(episode, company_id)
        await self.repository.upload_text(
            namespace_id=namespace_id,
            text=episode.content,
            document_name=episode.title or episode.memory_id,
            metadata=metadata,
        )
        return episode.memory_id

    async def recall(self, request: LLMContextMemoryRecallRequest) -> list[LLMContextMemoryRecord]:
        company_id = _active_company_id()
        namespace_id = self._namespace_id(company_id)
        if not await self._namespace_exists(namespace_id):
            return []

        bind = RagResourceBindParams(
            namespace=namespace_id,
            provider=self.provider,
            company_id=company_id,
            filters=_recall_filters(request, company_id),
            search_options=request.search_options,
        )
        response = await self.repository.search_namespace(
            query=request.query,
            limit=request.top_k,
            bind=bind,
        )
        return [_result_to_record(result) for result in _coerce_results(response)]

    def _namespace_id(self, company_id: str) -> str:
        return self.namespace_id or llm_context_memory_namespace_id(company_id)

    async def _ensure_namespace(self, namespace_id: str, company_id: str) -> None:
        if self.namespace_repository is None:
            return
        existing = await self.namespace_repository.get(namespace_id)
        if existing is None:
            await self.namespace_repository.set(
                Namespace(
                    name=namespace_id,
                    company_id=company_id,
                    description="LLM context episodic memory",
                )
            )

    async def _namespace_exists(self, namespace_id: str) -> bool:
        if self.namespace_repository is None:
            return True
        return await self.namespace_repository.get(namespace_id) is not None


def llm_context_memory_namespace_id(company_id: str) -> str:
    """Stable RAG namespace for one company's LLM context memory."""
    raw = company_id.strip()
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in raw).strip("-")
    safe = safe[:48].strip("-") or "company"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    return f"{_DEFAULT_NAMESPACE_PREFIX}-{safe}-{digest}"


def _active_company_id() -> str:
    context = get_context()
    if context is None or context.active_company is None:
        raise ValueError("LLM context memory requires active company context")
    return context.active_company.company_id


def _episode_metadata(episode: LLMContextMemoryEpisode, company_id: str) -> dict[str, Any]:
    return {
        **episode.metadata,
        "company_id": company_id,
        "document_id": episode.memory_id,
        "memory_id": episode.memory_id,
        "memory_scope": episode.scope,
        "session_id": episode.session_id,
        "flow_id": episode.flow_id,
        "branch_id": episode.branch_id,
        "node_id": episode.node_id,
        "user_id": episode.user_id,
        "title": episode.title,
        "source": episode.source,
        "created_at": episode.created_at.isoformat(),
    }


def _recall_filters(
    request: LLMContextMemoryRecallRequest,
    company_id: str,
) -> dict[str, Any]:
    filters: dict[str, Any] = {
        "company_id": company_id,
        "memory_scope": request.scope,
    }
    if request.scope == "session":
        if not request.session_id:
            return {"company_id": company_id, "memory_scope": "__missing_session__"}
        filters["session_id"] = request.session_id
    elif request.scope == "node":
        if not request.flow_id or not request.node_id:
            return {"company_id": company_id, "memory_scope": "__missing_node__"}
        filters["flow_id"] = request.flow_id
        filters["node_id"] = request.node_id
    elif request.scope == "flow":
        if not request.flow_id:
            return {"company_id": company_id, "memory_scope": "__missing_flow__"}
        filters["flow_id"] = request.flow_id
    return filters


def _coerce_results(response: dict[str, Any]) -> list[RAGSearchResult]:
    raw_results = response.get("results")
    if not isinstance(raw_results, list):
        raise ValueError("LLM context memory expected response.results list")
    return [
        item if isinstance(item, RAGSearchResult) else RAGSearchResult.model_validate(item)
        for item in raw_results
    ]


def _result_to_record(result: RAGSearchResult) -> LLMContextMemoryRecord:
    metadata = dict(result.metadata)
    return LLMContextMemoryRecord(
        memory_id=str(metadata.get("memory_id") or result.document_id),
        content=_record_content(metadata, result.content),
        scope=metadata.get("memory_scope", "session"),
        score=_clamp_score(result.score),
        session_id=_optional_str(metadata.get("session_id")),
        flow_id=_optional_str(metadata.get("flow_id")),
        branch_id=_optional_str(metadata.get("branch_id")),
        node_id=_optional_str(metadata.get("node_id")),
        user_id=_optional_str(metadata.get("user_id")),
        title=_optional_str(metadata.get("title")),
        source=_optional_str(metadata.get("source")),
        metadata=metadata,
        created_at=_parse_datetime(metadata.get("created_at")),
    )


def _record_content(metadata: dict[str, Any], fallback: str) -> str:
    recall_content = metadata.get(LLM_CONTEXT_MEMORY_RECALL_CONTENT_METADATA_KEY)
    if isinstance(recall_content, str) and recall_content.strip():
        return recall_content.strip()
    return fallback


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _clamp_score(value: Any) -> float | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return min(1.0, max(0.0, score))


__all__ = ["RAGLLMContextMemoryStore", "llm_context_memory_namespace_id"]
