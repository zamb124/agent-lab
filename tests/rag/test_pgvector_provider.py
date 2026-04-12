"""
Unit-тесты PgVectorProvider.

Тестируют провайдер напрямую (без HTTP),
используя реальный PostgreSQL + pgvector.

Синхронная загрузка через провайдер пишет только ``vector_documents``.
Очередь TaskIQ и строки ``document_processing_status`` здесь не создаются
(это путь HTTP + воркер).

Проверки БД изолированы по паре ``(namespace_id, company_id)`` (метаданные загрузки
``company_id`` + фикстура ``rag_company_id``).
"""

import uuid
from typing import Any

import pytest
from sqlalchemy import func, select

from core.db.models import VectorDocument


def _upload_metadata(company_id: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = dict(extra or {})
    merged["company_id"] = company_id
    return merged


async def _vector_chunk_count(
    session_factory, namespace_id: str, company_id: str
) -> int:
    async with session_factory() as session:
        stmt = (
            select(func.count())
            .select_from(VectorDocument)
            .where(
                VectorDocument.namespace_id == namespace_id,
                VectorDocument.company_id == company_id,
            )
        )
        result = await session.execute(stmt)
        return int(result.scalar() or 0)


async def _vector_document_rows_ordered(
    session_factory, namespace_id: str, document_id: str, company_id: str
) -> list[VectorDocument]:
    async with session_factory() as session:
        stmt = (
            select(VectorDocument)
            .where(
                VectorDocument.namespace_id == namespace_id,
                VectorDocument.document_id == document_id,
                VectorDocument.company_id == company_id,
            )
            .order_by(VectorDocument.chunk_index)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


@pytest.fixture
def rag_company_id() -> str:
    """Изоляция строк vector_documents по company_id в рамках теста."""
    return f"test_co_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def ns_name():
    """Уникальное имя namespace для каждого теста."""
    return f"test_ns_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def ns_name_2():
    return f"test_ns_{uuid.uuid4().hex[:8]}"


# -- Namespace CRUD --


@pytest.mark.asyncio
async def test_create_namespace(rag_provider_pgvector, ns_name, rag_company_id):
    """create_namespace возвращает RAGNamespace с правильными полями."""
    ns = await rag_provider_pgvector.create_namespace(ns_name, description="desc")

    assert ns.model_dump() == {
        "namespace_id": ns_name,
        "name": ns_name,
        "description": "desc",
        "document_count": 0,
        "created_at": None,
        "metadata": {},
    }
    sf = rag_provider_pgvector._session_factory
    assert await _vector_chunk_count(sf, ns_name, rag_company_id) == 0


@pytest.mark.asyncio
async def test_get_namespace_empty(rag_provider_pgvector, rag_company_id):
    """get_namespace для несуществующего namespace возвращает None."""
    result = await rag_provider_pgvector.get_namespace("nonexistent_ns_123")
    assert result is None
    sf = rag_provider_pgvector._session_factory
    assert await _vector_chunk_count(sf, "nonexistent_ns_123", rag_company_id) == 0


@pytest.mark.asyncio
async def test_list_namespaces(rag_provider_pgvector, ns_name, rag_company_id):
    """list_namespaces содержит namespace после загрузки документа."""
    doc = await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name,
        text="some test content",
        document_name="doc.txt",
        metadata=_upload_metadata(rag_company_id),
    )

    namespaces = await rag_provider_pgvector.list_namespaces()
    matching = [n.model_dump() for n in namespaces if n.namespace_id == ns_name]
    assert len(matching) == 1
    assert {k: matching[0][k] for k in ("namespace_id", "name", "description", "created_at", "metadata")} == {
        "namespace_id": ns_name,
        "name": ns_name,
        "description": None,
        "created_at": None,
        "metadata": {},
    }
    assert matching[0]["document_count"] == 1

    sf = rag_provider_pgvector._session_factory
    rows = await _vector_document_rows_ordered(sf, ns_name, doc.document_id, rag_company_id)
    assert len(rows) == doc.metadata["total_chunks"]
    assert all(r.namespace_id == ns_name for r in rows)
    assert all(r.company_id == rag_company_id for r in rows)
    assert all(r.document_id == doc.document_id for r in rows)
    assert all(r.document_name == "doc.txt" for r in rows)
    joined = "".join(r.content for r in rows)
    assert "some test content" in joined
    assert all(r.embedding is not None for r in rows)


@pytest.mark.asyncio
async def test_delete_namespace(rag_provider_pgvector, ns_name, rag_company_id):
    """delete_namespace удаляет все документы namespace."""
    namespace_id = ns_name
    company_id = rag_company_id
    doc = await rag_provider_pgvector.upload_document_from_text(
        namespace_id=namespace_id,
        text="content to delete",
        document_name="temp.txt",
        metadata=_upload_metadata(company_id),
    )
    sf = rag_provider_pgvector._session_factory
    assert await _vector_chunk_count(sf, namespace_id, company_id) == doc.metadata["total_chunks"]
    chunks_in_db = await _vector_document_rows_ordered(sf, namespace_id, doc.document_id, company_id)
    assert len(chunks_in_db) == doc.metadata["total_chunks"]
    assert all(r.namespace_id == namespace_id and r.company_id == company_id for r in chunks_in_db)
    assert all(r.document_name == "temp.txt" for r in chunks_in_db)
    assert "content to delete" in "".join(r.content for r in chunks_in_db)

    deleted = await rag_provider_pgvector.delete_namespace(namespace_id)
    assert deleted is True

    ns = await rag_provider_pgvector.get_namespace(namespace_id)
    assert ns is None
    assert await _vector_chunk_count(sf, namespace_id, company_id) == 0
    assert await _vector_document_rows_ordered(sf, namespace_id, doc.document_id, company_id) == []


@pytest.mark.asyncio
async def test_delete_namespace_nonexistent(rag_provider_pgvector, rag_company_id):
    """delete_namespace для пустого namespace возвращает False."""
    sf = rag_provider_pgvector._session_factory
    assert await _vector_chunk_count(sf, "no_such_ns_99", rag_company_id) == 0
    deleted = await rag_provider_pgvector.delete_namespace("no_such_ns_99")
    assert deleted is False
    assert await _vector_chunk_count(sf, "no_such_ns_99", rag_company_id) == 0


# -- Document CRUD --


@pytest.mark.asyncio
async def test_upload_and_get_document(rag_provider_pgvector, ns_name, rag_company_id):
    """upload_document_from_text сохраняет документ, get_document его находит."""
    doc = await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name,
        text="Python is a programming language.",
        document_name="python.txt",
        metadata=_upload_metadata(rag_company_id, {"lang": "en"}),
    )
    assert doc.model_dump(
        include={"document_id", "name", "namespace", "status", "content"}
    ) == {
        "document_id": doc.document_id,
        "name": "python.txt",
        "namespace": ns_name,
        "status": "completed",
        "content": None,
    }
    assert doc.metadata["lang"] == "en"

    sf = rag_provider_pgvector._session_factory
    rows = await _vector_document_rows_ordered(sf, ns_name, doc.document_id, rag_company_id)
    assert len(rows) == doc.metadata["total_chunks"]
    assert all(r.metadata_.get("lang") == "en" for r in rows)
    assert all(r.company_id == rag_company_id for r in rows)
    assert all(r.document_name == "python.txt" for r in rows)
    assert "programming language" in "".join(r.content for r in rows).lower()
    assert all(r.embedding is not None for r in rows)
    assert [r.chunk_index for r in rows] == list(range(len(rows)))
    assert all(r.total_chunks == rows[0].total_chunks for r in rows)

    fetched = await rag_provider_pgvector.get_document(ns_name, doc.document_id)
    assert fetched is not None
    assert fetched.model_dump(
        include={"document_id", "name", "namespace", "status", "content"}
    ) == {
        "document_id": doc.document_id,
        "name": "python.txt",
        "namespace": ns_name,
        "status": "completed",
        "content": None,
    }


@pytest.mark.asyncio
async def test_get_document_nonexistent(rag_provider_pgvector, ns_name, rag_company_id):
    """get_document для несуществующего документа возвращает None."""
    result = await rag_provider_pgvector.get_document(ns_name, "no_such_doc")
    assert result is None
    sf = rag_provider_pgvector._session_factory
    assert await _vector_document_rows_ordered(sf, ns_name, "no_such_doc", rag_company_id) == []


@pytest.mark.asyncio
async def test_list_documents(rag_provider_pgvector, ns_name, rag_company_id):
    """list_documents возвращает все загруженные документы."""
    first = await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name,
        text="First document content",
        document_name="first.txt",
        metadata=_upload_metadata(rag_company_id),
    )
    second = await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name,
        text="Second document content",
        document_name="second.txt",
        metadata=_upload_metadata(rag_company_id),
    )

    docs = await rag_provider_pgvector.list_documents(ns_name)
    by_name = {d.name: d for d in docs}
    assert sorted(by_name) == ["first.txt", "second.txt"]
    assert [
        by_name[n].model_dump(include={"name", "namespace", "status", "content"})
        for n in ("first.txt", "second.txt")
    ] == [
        {"name": "first.txt", "namespace": ns_name, "status": "completed", "content": None},
        {"name": "second.txt", "namespace": ns_name, "status": "completed", "content": None},
    ]

    sf = rag_provider_pgvector._session_factory
    r1 = await _vector_document_rows_ordered(sf, ns_name, first.document_id, rag_company_id)
    r2 = await _vector_document_rows_ordered(sf, ns_name, second.document_id, rag_company_id)
    assert len(r1) == first.metadata["total_chunks"]
    assert len(r2) == second.metadata["total_chunks"]
    assert await _vector_chunk_count(sf, ns_name, rag_company_id) == (
        first.metadata["total_chunks"] + second.metadata["total_chunks"]
    )
    assert first.document_id != second.document_id
    assert all(r.company_id == rag_company_id for r in r1 + r2)
    assert "First document content" in "".join(x.content for x in r1)
    assert "Second document content" in "".join(x.content for x in r2)


@pytest.mark.asyncio
async def test_delete_document(rag_provider_pgvector, ns_name, rag_company_id):
    """delete_document удаляет документ и все его чанки."""
    namespace_id = ns_name
    company_id = rag_company_id
    doc = await rag_provider_pgvector.upload_document_from_text(
        namespace_id=namespace_id,
        text="Document to be deleted",
        document_name="bye.txt",
        metadata=_upload_metadata(company_id),
    )
    sf = rag_provider_pgvector._session_factory
    chunks_before_delete = await _vector_document_rows_ordered(
        sf, namespace_id, doc.document_id, company_id
    )
    assert len(chunks_before_delete) == doc.metadata["total_chunks"]
    assert await _vector_chunk_count(sf, namespace_id, company_id) == doc.metadata["total_chunks"]
    assert all(r.namespace_id == namespace_id and r.company_id == company_id for r in chunks_before_delete)

    deleted = await rag_provider_pgvector.delete_document(namespace_id, doc.document_id)
    assert deleted is True

    fetched = await rag_provider_pgvector.get_document(namespace_id, doc.document_id)
    assert fetched is None
    assert await _vector_document_rows_ordered(sf, namespace_id, doc.document_id, company_id) == []


@pytest.mark.asyncio
async def test_delete_document_nonexistent(rag_provider_pgvector, ns_name, rag_company_id):
    """delete_document для несуществующего документа возвращает False."""
    sf = rag_provider_pgvector._session_factory
    assert await _vector_document_rows_ordered(sf, ns_name, "no_doc_here", rag_company_id) == []
    deleted = await rag_provider_pgvector.delete_document(ns_name, "no_doc_here")
    assert deleted is False
    assert await _vector_document_rows_ordered(sf, ns_name, "no_doc_here", rag_company_id) == []


# -- Upload + Search --


@pytest.mark.asyncio
async def test_upload_text_and_search(rag_provider_pgvector, ns_name, rag_company_id):
    """Загрузка текста и последующий семантический поиск возвращает результаты."""
    doc = await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name,
        text="Machine learning is a subset of artificial intelligence.",
        document_name="ml.txt",
        metadata=_upload_metadata(rag_company_id),
    )

    sf = rag_provider_pgvector._session_factory
    namespace_id = ns_name
    company_id = rag_company_id
    rows = await _vector_document_rows_ordered(sf, namespace_id, doc.document_id, company_id)
    assert len(rows) == doc.metadata["total_chunks"]
    assert all(r.namespace_id == namespace_id and r.company_id == company_id for r in rows)
    blob = " ".join(r.content.lower() for r in rows)
    assert "machine learning" in blob
    assert "artificial intelligence" in blob

    results = await rag_provider_pgvector.search(namespace_id, "artificial intelligence")
    assert len(results) == doc.metadata["total_chunks"]
    r0 = results[0]
    assert {
        **r0.model_dump(include={"document_name", "namespace", "document_id", "metadata", "chunk_id", "provenance"}),
        "score_type": type(r0.score).__name__,
        "has_content": bool(r0.content),
    } == {
        "document_name": "ml.txt",
        "namespace": namespace_id,
        "document_id": r0.document_id,
        "metadata": r0.metadata,
        "chunk_id": r0.chunk_id,
        "provenance": r0.provenance,
        "score_type": "float",
        "has_content": True,
    }


@pytest.mark.asyncio
async def test_search_empty_namespace(rag_provider_pgvector, ns_name, rag_company_id):
    """Поиск в пустом namespace возвращает пустой список."""
    sf = rag_provider_pgvector._session_factory
    assert await _vector_chunk_count(sf, ns_name, rag_company_id) == 0
    results = await rag_provider_pgvector.search(ns_name, "anything")
    assert [r.model_dump() for r in results] == []


# -- Chunking --


@pytest.mark.asyncio
async def test_chunking(rag_provider_pgvector, ns_name, rag_company_id):
    """Длинный текст разбивается на несколько чанков."""
    long_text = "This is a sentence about testing. " * 500

    doc = await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name,
        text=long_text,
        document_name="long.txt",
        metadata=_upload_metadata(rag_company_id),
    )

    total_chunks = doc.metadata["total_chunks"]
    assert total_chunks > 1

    results = await rag_provider_pgvector.search(ns_name, "testing", limit=20)
    assert len(results) == min(20, total_chunks)

    assert [r.model_dump(include={"document_id"}) for r in results] == [
        {"document_id": doc.document_id} for _ in results
    ]

    sf = rag_provider_pgvector._session_factory
    rows = await _vector_document_rows_ordered(sf, ns_name, doc.document_id, rag_company_id)
    assert len(rows) == total_chunks
    assert [r.chunk_index for r in rows] == list(range(len(rows)))
    assert all(r.total_chunks == len(rows) for r in rows)
    assert all(r.company_id == rag_company_id for r in rows)


# -- Search with filters --


@pytest.mark.asyncio
async def test_search_with_filters(rag_provider_pgvector, ns_name, rag_company_id):
    """Поиск с metadata фильтрами сужает результаты."""
    web_doc = await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name,
        text="Python web development with Django framework.",
        document_name="django.txt",
        metadata=_upload_metadata(rag_company_id, {"category": "web"}),
    )
    ml_doc = await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name,
        text="Python machine learning with scikit-learn library.",
        document_name="ml.txt",
        metadata=_upload_metadata(rag_company_id, {"category": "ml"}),
    )

    sf = rag_provider_pgvector._session_factory
    web_rows = await _vector_document_rows_ordered(sf, ns_name, web_doc.document_id, rag_company_id)
    ml_rows = await _vector_document_rows_ordered(sf, ns_name, ml_doc.document_id, rag_company_id)
    assert len(web_rows) == web_doc.metadata["total_chunks"]
    assert len(ml_rows) == ml_doc.metadata["total_chunks"]
    assert await _vector_chunk_count(sf, ns_name, rag_company_id) == (
        web_doc.metadata["total_chunks"] + ml_doc.metadata["total_chunks"]
    )
    for row in web_rows:
        assert row.metadata_.get("category") == "web"
        assert row.company_id == rag_company_id
    for row in ml_rows:
        assert row.metadata_.get("category") == "ml"
        assert row.company_id == rag_company_id

    results = await rag_provider_pgvector.search(
        ns_name, "Python", limit=10, filters={"category": "web"}
    )
    assert len(results) == web_doc.metadata["total_chunks"]
    assert [r.model_dump(include={"metadata"})["metadata"].get("category") for r in results] == ["web"] * len(
        results
    )


@pytest.mark.asyncio
async def test_list_documents_with_filters(rag_provider_pgvector, ns_name, rag_company_id):
    """list_documents_with_filters фильтрует по metadata."""
    alpha = await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name,
        text="Alpha content",
        document_name="alpha.txt",
        metadata=_upload_metadata(rag_company_id, {"priority": "high"}),
    )
    beta = await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name,
        text="Beta content",
        document_name="beta.txt",
        metadata=_upload_metadata(rag_company_id, {"priority": "low"}),
    )

    sf = rag_provider_pgvector._session_factory
    alpha_rows = await _vector_document_rows_ordered(sf, ns_name, alpha.document_id, rag_company_id)
    beta_rows = await _vector_document_rows_ordered(sf, ns_name, beta.document_id, rag_company_id)
    assert len(alpha_rows) == alpha.metadata["total_chunks"]
    assert len(beta_rows) == beta.metadata["total_chunks"]
    assert await _vector_chunk_count(sf, ns_name, rag_company_id) == (
        alpha.metadata["total_chunks"] + beta.metadata["total_chunks"]
    )
    for row in alpha_rows:
        assert row.metadata_.get("priority") == "high"
        assert row.company_id == rag_company_id
    for row in beta_rows:
        assert row.metadata_.get("priority") == "low"
        assert row.company_id == rag_company_id

    docs = await rag_provider_pgvector.list_documents_with_filters(
        ns_name, where={"priority": "high"}
    )
    assert sorted(
        (d.model_dump(include={"name", "namespace", "status"}) for d in docs),
        key=lambda x: x["name"],
    ) == [
        {"name": "alpha.txt", "namespace": ns_name, "status": "completed"},
    ]


# -- Namespace isolation --


@pytest.mark.asyncio
async def test_namespace_isolation(rag_provider_pgvector, ns_name, ns_name_2, rag_company_id):
    """Документы из разных namespace не смешиваются при поиске."""
    company_id = rag_company_id
    d1 = await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name,
        text="Kubernetes container orchestration platform.",
        document_name="k8s.txt",
        metadata=_upload_metadata(company_id),
    )
    d2 = await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name_2,
        text="Cooking recipes for Italian pasta.",
        document_name="pasta.txt",
        metadata=_upload_metadata(company_id),
    )

    sf = rag_provider_pgvector._session_factory
    for row in await _vector_document_rows_ordered(sf, ns_name, d1.document_id, company_id):
        assert row.namespace_id == ns_name
        assert row.company_id == company_id
    for row in await _vector_document_rows_ordered(sf, ns_name_2, d2.document_id, company_id):
        assert row.namespace_id == ns_name_2
        assert row.company_id == company_id
    assert await _vector_chunk_count(sf, ns_name, company_id) == d1.metadata["total_chunks"]
    assert await _vector_chunk_count(sf, ns_name_2, company_id) == d2.metadata["total_chunks"]

    results_ns1 = await rag_provider_pgvector.search(ns_name, "container", limit=10)
    results_ns2 = await rag_provider_pgvector.search(ns_name_2, "Italian", limit=10)
    assert [r.model_dump(include={"namespace"}) for r in results_ns1] == [{"namespace": ns_name}] * len(results_ns1)
    assert [r.model_dump(include={"namespace"}) for r in results_ns2] == [{"namespace": ns_name_2}] * len(
        results_ns2
    )

    docs_ns1 = await rag_provider_pgvector.list_documents(ns_name)
    docs_ns2 = await rag_provider_pgvector.list_documents(ns_name_2)
    assert sorted(d.name for d in docs_ns1) == ["k8s.txt"]
    assert sorted(d.name for d in docs_ns2) == ["pasta.txt"]


# -- Document overwrite --


@pytest.mark.asyncio
async def test_document_overwrite(rag_provider_pgvector, ns_name, rag_company_id):
    """Повторная загрузка документа с тем же ID удаляет старые чанки."""
    doc_id = str(uuid.uuid4())
    company_id = rag_company_id
    namespace_id = ns_name

    doc_old = await rag_provider_pgvector.upload_document_from_text(
        namespace_id=namespace_id,
        text="Old content that should be replaced.",
        document_name="overwrite.txt",
        metadata=_upload_metadata(company_id, {"document_id": doc_id}),
    )
    results_old = await rag_provider_pgvector.search(namespace_id, "Old content")
    assert len(results_old) == doc_old.metadata["total_chunks"]

    doc_new = await rag_provider_pgvector.upload_document_from_text(
        namespace_id=namespace_id,
        text="Brand new content after overwrite.",
        document_name="overwrite.txt",
        metadata=_upload_metadata(company_id, {"document_id": doc_id}),
    )

    results_new = await rag_provider_pgvector.search(namespace_id, "Brand new content")
    assert len(results_new) == doc_new.metadata["total_chunks"]

    # Старый контент не должен находиться (чанки перезаписаны)
    results_check = await rag_provider_pgvector.search(namespace_id, "Old content", limit=20)
    assert [("Old content" in r.content) for r in results_check] == [False] * len(results_check)

    sf = rag_provider_pgvector._session_factory
    rows = await _vector_document_rows_ordered(sf, namespace_id, doc_id, company_id)
    assert len(rows) == doc_new.metadata["total_chunks"]
    assert await _vector_chunk_count(sf, namespace_id, company_id) == doc_new.metadata["total_chunks"]
    assert all(r.namespace_id == namespace_id and r.company_id == company_id for r in rows)
    joined = "".join(r.content for r in rows)
    assert "Brand new content after overwrite" in joined
    assert "Old content that should be replaced" not in joined


@pytest.mark.asyncio
async def test_search_hybrid_rrf_returns_provenance(rag_provider_pgvector, ns_name, rag_company_id):
    """Гибрид semantic+lexical: RRF и provenance channel hybrid_rrf."""
    doc = await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name,
        text="unique_hybrid_token_zeta bravo delta gamma physics",
        document_name="hybrid.txt",
        metadata=_upload_metadata(rag_company_id),
    )
    sf = rag_provider_pgvector._session_factory
    namespace_id = ns_name
    company_id = rag_company_id
    rows = await _vector_document_rows_ordered(sf, namespace_id, doc.document_id, company_id)
    assert len(rows) == doc.metadata["total_chunks"]
    assert all(r.namespace_id == namespace_id and r.company_id == company_id for r in rows)
    assert "unique_hybrid_token_zeta" in "".join(r.content for r in rows)

    results = await rag_provider_pgvector.search(
        namespace_id,
        "unique_hybrid_token_zeta bravo",
        limit=5,
        channels={"semantic": True, "lexical": True},
    )
    assert len(results) == doc.metadata["total_chunks"]
    r0 = results[0]
    assert {"channel": r0.provenance.get("channel"), "chunk_id_present": r0.chunk_id is not None} == {
        "channel": "hybrid_rrf",
        "chunk_id_present": True,
    }


@pytest.mark.asyncio
async def test_search_multiple_namespaces_hybrid_rrf_per_namespace(
    rag_provider_pgvector, ns_name, ns_name_2, rag_company_id
):
    """Глобальный поиск с semantic+lexical: отдельный RRF в каждом namespace (свои документы)."""
    company_id = rag_company_id
    da = await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name,
        text="global_hybrid_alpha_one two three",
        document_name="a.txt",
        metadata=_upload_metadata(company_id),
    )
    db = await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name_2,
        text="global_hybrid_beta_four five six",
        document_name="b.txt",
        metadata=_upload_metadata(company_id),
    )
    sf = rag_provider_pgvector._session_factory
    rows_a = await _vector_document_rows_ordered(sf, ns_name, da.document_id, company_id)
    rows_b = await _vector_document_rows_ordered(sf, ns_name_2, db.document_id, company_id)
    assert len(rows_a) == da.metadata["total_chunks"]
    assert len(rows_b) == db.metadata["total_chunks"]
    for r in await _vector_document_rows_ordered(sf, ns_name, da.document_id, company_id):
        assert r.namespace_id == ns_name and r.company_id == company_id
    for r in await _vector_document_rows_ordered(sf, ns_name_2, db.document_id, company_id):
        assert r.namespace_id == ns_name_2 and r.company_id == company_id

    out = await rag_provider_pgvector.search_multiple_namespaces(
        [ns_name, ns_name_2],
        "global_hybrid_alpha_one",
        limit=5,
        channels={"semantic": True, "lexical": True},
    )
    assert {
        "ns1_docs": sorted({r.document_name for r in out[ns_name]}),
        "ns2_docs": sorted({r.document_name for r in out[ns_name_2]}),
        "ns1_namespaces": sorted({r.namespace for r in out[ns_name]}),
        "ns2_namespaces": sorted({r.namespace for r in out[ns_name_2]}),
        "cross_leak_ns1_has_b": any(r.document_name == "b.txt" for r in out[ns_name]),
        "cross_leak_ns2_has_a": any(r.document_name == "a.txt" for r in out[ns_name_2]),
    } == {
        "ns1_docs": ["a.txt"],
        "ns2_docs": ["b.txt"],
        "ns1_namespaces": [ns_name],
        "ns2_namespaces": [ns_name_2],
        "cross_leak_ns1_has_b": False,
        "cross_leak_ns2_has_a": False,
    }


@pytest.mark.asyncio
async def test_search_multiple_namespaces_filters_plus_lexical_no_duplicate_kwargs(
    rag_provider_pgvector, ns_name, rag_company_id
):
    """Регрессия: filters не должен оставаться в **kwargs при делегировании в Base (иначе duplicate keyword)."""
    await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name,
        text="filters_lexical_token_xyz abc",
        document_name="fl.txt",
        metadata=_upload_metadata(rag_company_id),
    )
    out = await rag_provider_pgvector.search_multiple_namespaces(
        [ns_name],
        "filters_lexical_token_xyz",
        limit=5,
        filters=None,
        channels={"semantic": True, "lexical": True},
    )
    assert ns_name in out
    assert len(out[ns_name]) >= 1


# -- provider_name --


@pytest.mark.asyncio
async def test_provider_name(rag_provider_pgvector):
    """provider_name возвращает 'pgvector'."""
    assert rag_provider_pgvector.provider_name == "pgvector"
