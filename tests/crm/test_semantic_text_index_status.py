"""
Статус семантического индекса сущности (агрегат по vector_documents).
"""

from __future__ import annotations

import uuid as uuid_std
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete

from apps.crm.container import CRMContainer
from apps.crm.db.models import CRMEntity
from apps.crm.db.repositories.entity_repository import EntityRepository
from apps.crm.models.api import EntityResponse, SemanticTextIndexStatus
from apps.crm.services.entity_response_enrichment import build_entity_responses_with_semantic_index
from core.db.models import VectorDocument
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
        assignees=[],
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


def _pgvector_provider(repo: EntityRepository) -> PgVectorProvider:
    provider = repo._rag.provider  # pyright: ignore[reportPrivateUsage]
    if not isinstance(provider, PgVectorProvider):
        raise AssertionError("expected PgVectorProvider")
    return provider


async def _delete_vector_documents_in_namespace(
    provider: PgVectorProvider,
    namespace_id: str,
) -> None:
    async with provider._session_factory() as session:  # pyright: ignore[reportPrivateUsage]
        _ = await session.execute(
            delete(VectorDocument).where(VectorDocument.namespace_id == namespace_id)
        )
        await session.commit()


async def _insert_vector_documents(
    provider: PgVectorProvider,
    rows: list[VectorDocument],
) -> None:
    async with provider._session_factory() as session:  # pyright: ignore[reportPrivateUsage]
        session.add_all(rows)
        await session.commit()


@pytest.fixture
def sem_idx_namespace(unique_id: str) -> str:
    return f"sem_idx_{unique_id}"


@pytest.fixture
def sem_idx_company(unique_id: str) -> str:
    return f"co_sem_{unique_id}"


@pytest.mark.asyncio
async def test_batch_semantic_text_index_status_three_states(
    crm_container: CRMContainer,
    unique_id: str,
    sem_idx_namespace: str,
    sem_idx_company: str,
) -> None:
    repo = crm_container.entity_repository
    provider = _pgvector_provider(repo)

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
            metadata_={},
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
            metadata_={},
        )
        await _insert_vector_documents(provider, [pending_row, ready_row])

        entities = [
            _bare_entity(doc_absent, cid, ns),
            _bare_entity(doc_pending, cid, ns),
            _bare_entity(doc_ready, cid, ns),
        ]
        stats = await repo.batch_semantic_text_index_status(entities)
        assert stats[doc_absent] == "absent"
        assert stats[doc_pending] == "pending_embedding"
        assert stats[doc_ready] == "ready"
    finally:
        await _delete_vector_documents_in_namespace(provider, ns)


@pytest.mark.asyncio
async def test_build_entity_responses_single_batch_provider_call(
    crm_container: CRMContainer,
    unique_id: str,
    sem_idx_namespace: str,
    sem_idx_company: str,
) -> None:
    repo = crm_container.entity_repository
    provider = _pgvector_provider(repo)
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
            repo, entities
        )
        assert len(responses) == 4
        assert calls == [4]
        for response in responses:
            assert response.semantic_text_index_status == "absent"
    finally:
        provider.batch_document_semantic_index_status = original


@pytest.mark.asyncio
async def test_pgvector_provider_pending_with_mixed_chunks(
    crm_container: CRMContainer,
    unique_id: str,
    sem_idx_namespace: str,
    sem_idx_company: str,
) -> None:
    """Если один chunk без embedding и один с embedding — статус pending_embedding."""
    repo = crm_container.entity_repository
    provider = _pgvector_provider(repo)
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
                metadata_={},
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
                metadata_={},
            ),
        ]
        await _insert_vector_documents(provider, rows)

        stats = await repo.batch_semantic_text_index_status(
            [_bare_entity(doc_id, cid, ns)]
        )
        assert stats[doc_id] == "pending_embedding"
    finally:
        await _delete_vector_documents_in_namespace(provider, ns)
