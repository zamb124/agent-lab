"""Контракт RAGResource: поиск через HTTP RAG API (ASGI); add_document через pgvector в той же БД."""

import uuid

import pytest

from apps.flows.src.container import FlowContainer
from core.rag.rag_resource import RAGResource
from core.config import get_settings
from tests.fixtures.auth import service_client_asgi_auth_context



@pytest.fixture
def flow_container_for_rag() -> FlowContainer:
    s = get_settings()
    return FlowContainer(db_url=s.database.flows_url, shared_db_url=s.database.shared_url)


@pytest.mark.asyncio
async def test_search_via_rag_asgi_hybrid_channels(
    monkeypatch: pytest.MonkeyPatch,
    flow_container_for_rag: FlowContainer,
    rag_app,
    auth_headers_system: dict[str, str],
) -> None:
    """
    Поиск идёт в реальный RAG FastAPI через ASGI; эмбеддинги — тестовый контур (PGVECTOR_TEST_MOCK_EMBEDDINGS).
    """

    ns = f"test_rag_res_{uuid.uuid4().hex[:10]}"
    marker = f"uniq_ragres_{uuid.uuid4().hex[:12]}"
    body = f"{marker} Cats are wonderful pets that love to sleep and play."

    r = RAGResource(
        namespace=ns,
        company_id="system",
        search_options={
            "channels": {"semantic": True, "lexical": True},
            "rerank": False,
        },
        container=flow_container_for_rag,
    )
    await r.add_document("d1", body, metadata={"category": "pets"}, name="n.txt")

    prov = flow_container_for_rag.rag_repository.provider
    stored = await prov.get_document(ns, "d1")
    assert stored is not None
    assert stored.metadata["total_chunks"] == 1

    with service_client_asgi_auth_context(auth_headers_system):
        results = await r.search(f"{marker} cats sleep", top_k=3)
    assert len(results) == 1
    joined = " ".join(item["content"].lower() for item in results)
    assert marker.lower() in joined
    assert "cats" in joined


@pytest.mark.asyncio
async def test_add_document_passes_metadata_through(
    flow_container_for_rag: FlowContainer,
) -> None:
    ns = f"test_rag_res_{uuid.uuid4().hex[:10]}"
    r = RAGResource(namespace=ns, container=flow_container_for_rag)
    await r.add_document(
        "fid",
        "hello",
        metadata={"tag": "t"},
        name="n.txt",
    )

    prov = flow_container_for_rag.rag_repository.provider
    stored = await prov.get_document(ns, "fid")
    assert stored is not None
    assert stored.metadata.get("tag") == "t"
    assert stored.metadata.get("document_id") == "fid"


@pytest.mark.asyncio
async def test_add_document_merges_index_profile_config(
    flow_container_for_rag: FlowContainer,
) -> None:
    ns = f"test_rag_res_{uuid.uuid4().hex[:10]}"
    r = RAGResource(
        namespace=ns,
        container=flow_container_for_rag,
        index_profile_config={"split": {"chunk_size": 256}},
    )
    await r.add_document(
        "fid",
        "hello " * 20,
        metadata={"index_profile_config": {"split": {"strategy": "semantic"}}},
        name="n.txt",
        index_profile_config={"parsing": {"engine": "unstructured"}},
    )

    prov = flow_container_for_rag.rag_repository.provider
    stored = await prov.get_document(ns, "fid")
    assert stored is not None
    ir = stored.metadata["indexing_runtime"]
    assert ir["split"]["chunk_size"] == 256
    assert ir["split"]["strategy"] == "semantic"
    assert ir["parsing"]["engine"] == "unstructured"
