"""
Статус семантического индекса сущности (агрегат по vector_documents).
"""

from __future__ import annotations

import uuid as uuid_std
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete

from apps.crm.db.models import CRMEntity
from apps.crm.services.entity_response_enrichment import build_entity_responses_with_semantic_index
from core.db.models import VectorDocument
from core.rag.providers.pgvector_provider import PgVectorProvider


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
    return uuid_std.uuid5(uuid_std.NAMESPACE_URL, f"rag://{namespace}/{document_id}/{chunk_index}").hex


@pytest.fixture
def _sem_idx_namespace(unique_id: str) -> str:
    return f"sem_idx_{unique_id}"


@pytest.fixture
def _sem_idx_company(unique_id: str) -> str:
    return f"co_sem_{unique_id}"


@pytest.mark.asyncio
async def test_batch_semantic_text_index_status_three_states(
    crm_container,
    unique_id,
    _sem_idx_namespace,
    _sem_idx_company,
):
    repo = crm_container.entity_repository
    provider = repo._rag.provider
    assert isinstance(provider, PgVectorProvider)

    ns = _sem_idx_namespace
    cid = _sem_idx_company
    doc_absent = f"{unique_id}_absent"
    doc_pending = f"{unique_id}_pending"
    doc_ready = f"{unique_id}_ready"

    emb = [0.02] * 1024

    async with provider._session_factory() as session:
        await session.execute(delete(VectorDocument).where(VectorDocument.namespace_id == ns))
        await session.commit()

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
        async with provider._session_factory() as session:
            session.add_all([pending_row, ready_row])
            await session.commit()

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
        async with provider._session_factory() as session:
            await session.execute(delete(VectorDocument).where(VectorDocument.namespace_id == ns))
            await session.commit()


@pytest.mark.asyncio
async def test_build_entity_responses_single_batch_provider_call(
    crm_container,
    unique_id,
    _sem_idx_namespace,
    _sem_idx_company,
):
    repo = crm_container.entity_repository
    provider = repo._rag.provider
    assert isinstance(provider, PgVectorProvider)
    ns = _sem_idx_namespace
    cid = _sem_idx_company

    entities = [_bare_entity(f"{unique_id}_e{i}", cid, ns) for i in range(4)]

    calls: list[int] = []
    original = provider.batch_document_semantic_index_status

    async def wrapped(keys: list[tuple[str, str, str]]):
        calls.append(len(keys))
        return await original(keys)

    provider.batch_document_semantic_index_status = wrapped  # type: ignore[method-assign]

    try:
        responses = await build_entity_responses_with_semantic_index(repo, entities)
        assert len(responses) == 4
        assert calls == [4]
        for resp in responses:
            assert resp.semantic_text_index_status == "absent"
    finally:
        provider.batch_document_semantic_index_status = original  # type: ignore[method-assign]


@pytest.mark.asyncio
async def test_pgvector_provider_pending_with_mixed_chunks(
    crm_container,
    unique_id,
    _sem_idx_namespace,
    _sem_idx_company,
):
    """Если один chunk без embedding и один с embedding — статус pending_embedding."""
    repo = crm_container.entity_repository
    provider = repo._rag.provider
    assert isinstance(provider, PgVectorProvider)
    ns = _sem_idx_namespace
    cid = _sem_idx_company
    doc_id = f"{unique_id}_mixed"
    emb = [0.03] * 1024

    async with provider._session_factory() as session:
        await session.execute(delete(VectorDocument).where(VectorDocument.namespace_id == ns))
        await session.commit()

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
        async with provider._session_factory() as session:
            session.add_all(rows)
            await session.commit()

        stats = await repo.batch_semantic_text_index_status([_bare_entity(doc_id, cid, ns)])
        assert stats[doc_id] == "pending_embedding"
    finally:
        async with provider._session_factory() as session:
            await session.execute(delete(VectorDocument).where(VectorDocument.namespace_id == ns))
            await session.commit()
