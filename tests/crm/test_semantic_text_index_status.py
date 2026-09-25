"""
Статус семантического индекса сущности (агрегат по vector_documents).
"""

from __future__ import annotations

import uuid as uuid_std
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

import pytest
from oxyde import execute_raw

from apps.crm.models.api import EntityResponse, SemanticTextIndexStatus
from apps.crm.models.crm_entity import CRMEntity
from apps.crm.services.entity_response_enrichment import (
    build_entity_responses_with_semantic_index,
    semantic_text_index_status_by_entity,
)
from core.db.models import VectorDocument
from core.rag import BaseRAGProvider
from core.rag.constants import RAG_IN_PROCESS_PROVIDER_ID
from core.rag.factory import get_rag_provider
from core.rag.providers.pgvector_provider import PgVectorProvider

DocumentSemanticKey = tuple[str, str, str]
BatchDocumentSemanticIndexStatusFn = Callable[
    [list[DocumentSemanticKey]],
    Awaitable[dict[DocumentSemanticKey, SemanticTextIndexStatus]],
]


def _bare_entity(entity_id: str, company_id: str, namespace: str = "default") -> CRMEntity:
    now = datetime.now(timezone.utc)
    return CRMEntity(
        entity_id=entity_id,
        company_id=company_id,
        namespace=namespace,
        entity_type="note",
        name="n",
        description=None,
        status="active",
        tags=[],
        attributes={},
        attachment_ids=[],
        user_id="user_test_semantic_index",
        relevance=1.0,
        created_at=now,
        updated_at=now,
    )


def _chunk_pk(namespace: str, document_id: str, chunk_index: int) -> str:
    return uuid_std.uuid5(
        uuid_std.NAMESPACE_URL,
        f"rag://{namespace}/{document_id}/{chunk_index}",
    ).hex


def _pgvector_provider(rag: BaseRAGProvider) -> PgVectorProvider:
    if not isinstance(rag, PgVectorProvider):
        raise AssertionError("expected PgVectorProvider")
    return rag


async def _delete_vector_documents_in_namespace(
    provider: PgVectorProvider,
    namespace_id: str,
) -> None:
    _ = provider
    _ = await VectorDocument.objects.filter(namespace_id=namespace_id).delete(using="rag")


async def _insert_vector_documents(
    provider: PgVectorProvider,
    rows: list[VectorDocument],
) -> None:
    _ = provider
    now = datetime.now(timezone.utc)
    for row in rows:
        _ = await execute_raw(
            """
            INSERT INTO vector_documents (
                id, namespace_id, company_id, document_id, document_name, content,
                embedding, embedding_model, chunk_index, total_chunks, metadata,
                created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7::vector, $8, $9, $10, $11::jsonb, $12, $12
            )
            """,
            [
                row.id,
                row.namespace_id,
                row.company_id,
                row.document_id,
                row.document_name,
                row.content,
                None if row.embedding is None else "[" + ",".join(str(item) for item in row.embedding) + "]",
                row.embedding_model,
                row.chunk_index,
                row.total_chunks,
                "{}",
                now,
            ],
            using="rag",
        )


@pytest.fixture
def sem_idx_namespace(unique_id: str) -> str:
    return f"sem_idx_{unique_id}"


@pytest.fixture
def sem_idx_company(unique_id: str) -> str:
    return f"co_sem_{unique_id}"


@pytest.mark.asyncio
async def test_batch_semantic_text_index_status_three_states(
    crm_di,
    unique_id: str,
    sem_idx_namespace: str,
    sem_idx_company: str,
) -> None:
    rag = get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID)
    provider = _pgvector_provider(rag)

    ns = sem_idx_namespace
    cid = sem_idx_company
    doc_absent = f"{unique_id}_absent"
    doc_pending = f"{unique_id}_pending"
    doc_ready = f"{unique_id}_ready"

    emb: list[float] = [0.02] * 1024

    await _delete_vector_documents_in_namespace(provider, ns)

    try:
        pending_row = VectorDocument(
            id=_chunk_pk(ns, doc_pending, 0),
            namespace_id=ns,
            company_id=cid,
            document_id=doc_pending,
            document_name=doc_pending,
            content="pending body",
            embedding=None,
            embedding_model=None,
            chunk_index=0,
            total_chunks=1,
            metadata={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        ready_row = VectorDocument(
            id=_chunk_pk(ns, doc_ready, 0),
            namespace_id=ns,
            company_id=cid,
            document_id=doc_ready,
            document_name=doc_ready,
            content="ready body",
            embedding=emb,
            embedding_model="qwen/qwen3-embedding-0.6b",
            chunk_index=0,
            total_chunks=1,
            metadata={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await _insert_vector_documents(provider, [pending_row, ready_row])

        entities = [
            _bare_entity(doc_absent, cid, ns),
            _bare_entity(doc_pending, cid, ns),
            _bare_entity(doc_ready, cid, ns),
        ]
        stats = await semantic_text_index_status_by_entity(rag, entities)
        assert stats[doc_absent] == "absent"
        assert stats[doc_pending] == "pending_embedding"
        assert stats[doc_ready] == "ready"
    finally:
        await _delete_vector_documents_in_namespace(provider, ns)


@pytest.mark.asyncio
async def test_build_entity_responses_single_batch_provider_call(
    crm_di,
    unique_id: str,
    sem_idx_namespace: str,
    sem_idx_company: str,
) -> None:
    rag = get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID)
    provider = _pgvector_provider(rag)
    ns = sem_idx_namespace
    cid = sem_idx_company

    entities = [_bare_entity(f"{unique_id}_e{i}", cid, ns) for i in range(4)]

    calls: list[int] = []
    original = provider.batch_document_semantic_index_status

    async def wrapped(
        keys: list[DocumentSemanticKey],
    ) -> dict[DocumentSemanticKey, SemanticTextIndexStatus]:
        calls.append(len(keys))
        return await original(keys)

    provider.batch_document_semantic_index_status = wrapped

    try:
        responses: list[EntityResponse] = await build_entity_responses_with_semantic_index(
            rag, entities
        )
        assert len(responses) == 4
        assert calls == [4]
        for response in responses:
            assert response.semantic_text_index_status == "absent"
    finally:
        provider.batch_document_semantic_index_status = original


@pytest.mark.asyncio
async def test_pgvector_provider_pending_with_mixed_chunks(
    crm_di,
    unique_id: str,
    sem_idx_namespace: str,
    sem_idx_company: str,
) -> None:
    """Если один chunk без embedding и один с embedding — статус pending_embedding."""
    rag = get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID)
    provider = _pgvector_provider(rag)
    ns = sem_idx_namespace
    cid = sem_idx_company
    doc_id = f"{unique_id}_mixed"
    emb: list[float] = [0.03] * 1024

    await _delete_vector_documents_in_namespace(provider, ns)

    try:
        rows = [
            VectorDocument(
                id=_chunk_pk(ns, doc_id, 0),
                namespace_id=ns,
                company_id=cid,
                document_id=doc_id,
                document_name=doc_id,
                content="a",
                embedding=None,
                embedding_model=None,
                chunk_index=0,
                total_chunks=2,
                metadata={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            ),
            VectorDocument(
                id=_chunk_pk(ns, doc_id, 1),
                namespace_id=ns,
                company_id=cid,
                document_id=doc_id,
                document_name=doc_id,
                content="b",
                embedding=emb,
                embedding_model="qwen/qwen3-embedding-0.6b",
                chunk_index=1,
                total_chunks=2,
                metadata={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            ),
        ]
        await _insert_vector_documents(provider, rows)

        stats = await semantic_text_index_status_by_entity(
            rag,
            [_bare_entity(doc_id, cid, ns)],
        )
        assert stats[doc_id] == "pending_embedding"
    finally:
        await _delete_vector_documents_in_namespace(provider, ns)
