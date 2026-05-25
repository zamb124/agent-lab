"""Episodic memory source for the platform LLM context layer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from pydantic import Field, field_validator, model_validator

from core.llm_context.models import LLMContextBlock, LLMContextMemoryScope
from core.llm_context.sources import LLMContextSourceRequest
from core.models import StrictBaseModel
from core.rag.models import RAGSearchOptions
from core.rag_indexing_schema import SearchChannelsDefaults
from core.types import JsonObject


class LLMContextMemoryEpisode(StrictBaseModel):
    """Closed memory episode ready for persistence and later retrieval."""

    memory_id: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    scope: LLMContextMemoryScope = "session"
    session_id: str | None = None
    flow_id: str | None = None
    branch_id: str | None = None
    node_id: str | None = None
    user_id: str | None = None
    title: str | None = None
    source: str = Field(default="conversation", min_length=1)
    metadata: JsonObject = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("scope")
    @classmethod
    def scope_must_be_memory_scope(cls, value: LLMContextMemoryScope) -> LLMContextMemoryScope:
        if value == "off":
            raise ValueError("memory episode scope cannot be 'off'")
        return value

    @model_validator(mode="after")
    def required_scope_keys_must_be_present(self) -> "LLMContextMemoryEpisode":
        if self.scope == "session" and not self.session_id:
            raise ValueError("session memory requires session_id")
        if self.scope == "node" and (not self.flow_id or not self.node_id):
            raise ValueError("node memory requires flow_id and node_id")
        if self.scope == "flow" and not self.flow_id:
            raise ValueError("flow memory requires flow_id")
        return self


class LLMContextMemoryRecallRequest(StrictBaseModel):
    """Query passed to a memory store for one LLM context compilation."""

    query: str = Field(..., min_length=1)
    scope: LLMContextMemoryScope
    top_k: int = Field(default=8, ge=1, le=128)
    session_id: str | None = None
    flow_id: str | None = None
    branch_id: str | None = None
    node_id: str | None = None
    user_id: str | None = None
    search_options: RAGSearchOptions | None = None
    metadata: JsonObject = Field(default_factory=dict)

    @field_validator("scope")
    @classmethod
    def scope_must_be_enabled(cls, value: LLMContextMemoryScope) -> LLMContextMemoryScope:
        if value == "off":
            raise ValueError("memory recall scope cannot be 'off'")
        return value


class LLMContextMemoryRecord(StrictBaseModel):
    """Memory record returned by a store before compiler packing."""

    memory_id: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    scope: LLMContextMemoryScope
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    session_id: str | None = None
    flow_id: str | None = None
    branch_id: str | None = None
    node_id: str | None = None
    user_id: str | None = None
    title: str | None = None
    source: str | None = None
    metadata: JsonObject = Field(default_factory=dict)
    created_at: datetime | None = None


class LLMContextMemoryStore(Protocol):
    """Persistence boundary used by ``LLMContextMemorySource``."""

    async def write_episode(self, episode: LLMContextMemoryEpisode) -> str:
        ...  # pragma: no cover

    async def recall(self, request: LLMContextMemoryRecallRequest) -> list[LLMContextMemoryRecord]:
        ...  # pragma: no cover


class LLMContextMemorySource:
    """Collect persisted episodic memory as compiler candidate blocks."""

    def __init__(
        self,
        *,
        store: LLMContextMemoryStore,
        name: str = "memory",
        session_id: str | None = None,
        flow_id: str | None = None,
        branch_id: str | None = None,
        node_id: str | None = None,
        user_id: str | None = None,
        top_k: int | None = None,
    ) -> None:
        self.store: LLMContextMemoryStore = store
        self.name: str = name
        self.session_id: str | None = session_id
        self.flow_id: str | None = flow_id
        self.branch_id: str | None = branch_id
        self.node_id: str | None = node_id
        self.user_id: str | None = user_id
        self.top_k: int | None = top_k

    async def collect(self, request: LLMContextSourceRequest) -> list[LLMContextBlock]:
        query = str(request.query or "").strip()
        if request.policy.memory == "off" or request.policy.retrieval.mode == "off" or not query:
            return []

        top_k = self.top_k or request.policy.retrieval.top_k
        records = await self.store.recall(
            LLMContextMemoryRecallRequest(
                query=query,
                scope=request.policy.memory,
                top_k=top_k,
                session_id=self.session_id,
                flow_id=self.flow_id,
                branch_id=self.branch_id,
                node_id=self.node_id,
                user_id=self.user_id,
                search_options=_search_options_from_request(request),
                metadata=request.metadata,
            )
        )
        selected_records = _select_relevant_records(
            records,
            top_k=top_k,
            min_score=request.policy.retrieval.min_score,
        )
        return [
            _record_to_block(record, rank=index + 1)
            for index, record in enumerate(_chronological(selected_records))
        ]


def _select_relevant_records(
    records: list[LLMContextMemoryRecord],
    *,
    top_k: int,
    min_score: float | None,
) -> list[LLMContextMemoryRecord]:
    selected: list[LLMContextMemoryRecord] = []
    for record in records:
        if min_score is not None and record.score is not None and record.score < min_score:
            continue
        selected.append(record)
        if len(selected) >= top_k:
            break
    return selected


def _chronological(records: list[LLMContextMemoryRecord]) -> list[LLMContextMemoryRecord]:
    return sorted(
        records,
        key=lambda record: (
            record.created_at or datetime.min.replace(tzinfo=timezone.utc),
            record.memory_id,
        ),
    )


def _search_options_from_request(request: LLMContextSourceRequest) -> RAGSearchOptions:
    mode = request.policy.retrieval.mode
    if mode == "hybrid":
        channels = SearchChannelsDefaults(semantic=True, lexical=True)
    elif mode == "lexical":
        channels = SearchChannelsDefaults(semantic=False, lexical=True)
    else:
        channels = SearchChannelsDefaults(semantic=True, lexical=False)
    return RAGSearchOptions(channels=channels, rerank=request.policy.retrieval.rerank)


def _record_to_block(record: LLMContextMemoryRecord, *, rank: int) -> LLMContextBlock:
    created = record.created_at.isoformat() if record.created_at is not None else "unknown"
    score_text = "n/a" if record.score is None else f"{record.score:.4f}"
    provenance = {
        **record.metadata,
        "memory_id": record.memory_id,
        "memory_scope": record.scope,
        "session_id": record.session_id,
        "flow_id": record.flow_id,
        "branch_id": record.branch_id,
        "node_id": record.node_id,
        "user_id": record.user_id,
        "source": record.source or "memory",
        "rank": rank,
        "score": record.score,
        "created_at": created,
    }
    return LLMContextBlock(
        kind="memory",
        budget_scope="memory",
        role="system",
        content=(
            f"[Memory #{rank} scope={record.scope} created_at={created} "
            f"score={score_text}]\n{record.content}"
        ),
        stable_key=f"memory:{record.scope}:{created}:{record.memory_id}",
        priority=80,
        score=record.score,
        provenance={key: value for key, value in provenance.items() if value is not None},
    )


__all__ = [
    "LLMContextMemoryEpisode",
    "LLMContextMemoryRecallRequest",
    "LLMContextMemoryRecord",
    "LLMContextMemorySource",
    "LLMContextMemoryStore",
]
