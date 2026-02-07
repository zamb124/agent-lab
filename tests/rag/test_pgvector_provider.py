"""
Unit-тесты PgVectorProvider.

Тестируют провайдер напрямую (без HTTP),
используя реальный PostgreSQL + pgvector.
"""

import pytest
import uuid


@pytest.fixture
def ns_name():
    """Уникальное имя namespace для каждого теста."""
    return f"test_ns_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def ns_name_2():
    return f"test_ns_{uuid.uuid4().hex[:8]}"


# -- Namespace CRUD --


@pytest.mark.asyncio
async def test_create_namespace(rag_provider_pgvector, ns_name):
    """create_namespace возвращает RAGNamespace с правильными полями."""
    ns = await rag_provider_pgvector.create_namespace(ns_name, description="desc")

    assert ns.namespace_id == ns_name
    assert ns.name == ns_name
    assert ns.description == "desc"
    assert ns.document_count == 0


@pytest.mark.asyncio
async def test_get_namespace_empty(rag_provider_pgvector):
    """get_namespace для несуществующего namespace возвращает None."""
    result = await rag_provider_pgvector.get_namespace("nonexistent_ns_123")
    assert result is None


@pytest.mark.asyncio
async def test_list_namespaces(rag_provider_pgvector, ns_name):
    """list_namespaces содержит namespace после загрузки документа."""
    await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name,
        text="some test content",
        document_name="doc.txt",
    )

    namespaces = await rag_provider_pgvector.list_namespaces()
    ns_ids = [n.namespace_id for n in namespaces]
    assert ns_name in ns_ids


@pytest.mark.asyncio
async def test_delete_namespace(rag_provider_pgvector, ns_name):
    """delete_namespace удаляет все документы namespace."""
    await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name,
        text="content to delete",
        document_name="temp.txt",
    )
    deleted = await rag_provider_pgvector.delete_namespace(ns_name)
    assert deleted is True

    ns = await rag_provider_pgvector.get_namespace(ns_name)
    assert ns is None


@pytest.mark.asyncio
async def test_delete_namespace_nonexistent(rag_provider_pgvector):
    """delete_namespace для пустого namespace возвращает False."""
    deleted = await rag_provider_pgvector.delete_namespace("no_such_ns_99")
    assert deleted is False


# -- Document CRUD --


@pytest.mark.asyncio
async def test_upload_and_get_document(rag_provider_pgvector, ns_name):
    """upload_document_from_text сохраняет документ, get_document его находит."""
    doc = await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name,
        text="Python is a programming language.",
        document_name="python.txt",
        metadata={"lang": "en"},
    )
    assert doc.document_id
    assert doc.name == "python.txt"
    assert doc.namespace == ns_name
    assert doc.status == "completed"

    fetched = await rag_provider_pgvector.get_document(ns_name, doc.document_id)
    assert fetched is not None
    assert fetched.document_id == doc.document_id
    assert fetched.name == "python.txt"


@pytest.mark.asyncio
async def test_get_document_nonexistent(rag_provider_pgvector, ns_name):
    """get_document для несуществующего документа возвращает None."""
    result = await rag_provider_pgvector.get_document(ns_name, "no_such_doc")
    assert result is None


@pytest.mark.asyncio
async def test_list_documents(rag_provider_pgvector, ns_name):
    """list_documents возвращает все загруженные документы."""
    await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name,
        text="First document content",
        document_name="first.txt",
    )
    await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name,
        text="Second document content",
        document_name="second.txt",
    )

    docs = await rag_provider_pgvector.list_documents(ns_name)
    names = [d.name for d in docs]
    assert "first.txt" in names
    assert "second.txt" in names


@pytest.mark.asyncio
async def test_delete_document(rag_provider_pgvector, ns_name):
    """delete_document удаляет документ и все его чанки."""
    doc = await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name,
        text="Document to be deleted",
        document_name="bye.txt",
    )
    deleted = await rag_provider_pgvector.delete_document(ns_name, doc.document_id)
    assert deleted is True

    fetched = await rag_provider_pgvector.get_document(ns_name, doc.document_id)
    assert fetched is None


@pytest.mark.asyncio
async def test_delete_document_nonexistent(rag_provider_pgvector, ns_name):
    """delete_document для несуществующего документа возвращает False."""
    deleted = await rag_provider_pgvector.delete_document(ns_name, "no_doc_here")
    assert deleted is False


# -- Upload + Search --


@pytest.mark.asyncio
async def test_upload_text_and_search(rag_provider_pgvector, ns_name):
    """Загрузка текста и последующий семантический поиск возвращает результаты."""
    await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name,
        text="Machine learning is a subset of artificial intelligence.",
        document_name="ml.txt",
    )

    results = await rag_provider_pgvector.search(ns_name, "artificial intelligence")
    assert len(results) > 0
    assert results[0].content
    assert results[0].document_name == "ml.txt"
    assert results[0].namespace == ns_name
    assert isinstance(results[0].score, float)


@pytest.mark.asyncio
async def test_search_empty_namespace(rag_provider_pgvector, ns_name):
    """Поиск в пустом namespace возвращает пустой список."""
    results = await rag_provider_pgvector.search(ns_name, "anything")
    assert results == []


# -- Chunking --


@pytest.mark.asyncio
async def test_chunking(rag_provider_pgvector, ns_name):
    """Длинный текст разбивается на несколько чанков."""
    long_text = "This is a sentence about testing. " * 500

    doc = await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name,
        text=long_text,
        document_name="long.txt",
    )

    results = await rag_provider_pgvector.search(ns_name, "testing", limit=20)
    assert len(results) > 1, "Длинный текст должен разбиться на несколько чанков"

    for r in results:
        assert r.document_id == doc.document_id


# -- Search with filters --


@pytest.mark.asyncio
async def test_search_with_filters(rag_provider_pgvector, ns_name):
    """Поиск с metadata фильтрами сужает результаты."""
    await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name,
        text="Python web development with Django framework.",
        document_name="django.txt",
        metadata={"category": "web"},
    )
    await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name,
        text="Python machine learning with scikit-learn library.",
        document_name="ml.txt",
        metadata={"category": "ml"},
    )

    results = await rag_provider_pgvector.search(
        ns_name, "Python", limit=10, filters={"category": "web"}
    )
    for r in results:
        assert r.metadata.get("category") == "web"


@pytest.mark.asyncio
async def test_list_documents_with_filters(rag_provider_pgvector, ns_name):
    """list_documents_with_filters фильтрует по metadata."""
    await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name,
        text="Alpha content",
        document_name="alpha.txt",
        metadata={"priority": "high"},
    )
    await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name,
        text="Beta content",
        document_name="beta.txt",
        metadata={"priority": "low"},
    )

    docs = await rag_provider_pgvector.list_documents_with_filters(
        ns_name, where={"priority": "high"}
    )
    names = [d.name for d in docs]
    assert "alpha.txt" in names
    assert "beta.txt" not in names


# -- Namespace isolation --


@pytest.mark.asyncio
async def test_namespace_isolation(rag_provider_pgvector, ns_name, ns_name_2):
    """Документы из разных namespace не смешиваются при поиске."""
    await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name,
        text="Kubernetes container orchestration platform.",
        document_name="k8s.txt",
    )
    await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name_2,
        text="Cooking recipes for Italian pasta.",
        document_name="pasta.txt",
    )

    results_ns1 = await rag_provider_pgvector.search(ns_name, "container", limit=10)
    for r in results_ns1:
        assert r.namespace == ns_name

    results_ns2 = await rag_provider_pgvector.search(ns_name_2, "Italian", limit=10)
    for r in results_ns2:
        assert r.namespace == ns_name_2

    docs_ns1 = await rag_provider_pgvector.list_documents(ns_name)
    docs_ns2 = await rag_provider_pgvector.list_documents(ns_name_2)
    assert all(d.name != "pasta.txt" for d in docs_ns1)
    assert all(d.name != "k8s.txt" for d in docs_ns2)


# -- Document overwrite --


@pytest.mark.asyncio
async def test_document_overwrite(rag_provider_pgvector, ns_name):
    """Повторная загрузка документа с тем же ID удаляет старые чанки."""
    doc_id = str(uuid.uuid4())

    await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name,
        text="Old content that should be replaced.",
        document_name="overwrite.txt",
        metadata={"document_id": doc_id},
    )
    results_old = await rag_provider_pgvector.search(ns_name, "Old content")
    assert len(results_old) > 0

    await rag_provider_pgvector.upload_document_from_text(
        namespace_id=ns_name,
        text="Brand new content after overwrite.",
        document_name="overwrite.txt",
        metadata={"document_id": doc_id},
    )

    results_new = await rag_provider_pgvector.search(ns_name, "Brand new content")
    assert len(results_new) > 0

    # Старый контент не должен находиться (чанки перезаписаны)
    results_check = await rag_provider_pgvector.search(ns_name, "Old content", limit=20)
    for r in results_check:
        assert "Old content" not in r.content


# -- provider_name --


@pytest.mark.asyncio
async def test_provider_name(rag_provider_pgvector):
    """provider_name возвращает 'pgvector'."""
    assert rag_provider_pgvector.provider_name == "pgvector"
