"""Контракт RAGResource: поиск через HTTP RAG API (ASGI); add_document через pgvector в той же БД."""

from tests.fixtures.billing import make_test_billing_service
import uuid

import pytest

from apps.flows.di import FlowsDi
from apps.flows.src.resources.rag_resource import RAGResource
from core.rag.constants import RAG_IN_PROCESS_PROVIDER_ID
from core.rag.factory import get_rag_provider
from tests.fixtures.auth import service_client_asgi_auth_context


@pytest.mark.asyncio
async def test_search_via_rag_asgi_hybrid_channels(
    monkeypatch: pytest.MonkeyPatch,
    di: FlowsDi,
    rag_app,
    auth_headers_system: dict[str, str],
) -> None:
    """
    Поиск идёт в реальный RAG FastAPI через ASGI; эмбеддинги — детерминированный клиент тестового контура.
    """

    ns = f"test_rag_res_{uuid.uuid4().hex[:10]}"
    marker = f"uniq_ragres_{uuid.uuid4().hex[:12]}"
    body = f"{marker} Cats are wonderful pets that love to sleep and play."

    r = RAGResource(
        billing_service=di.billing_service,
        namespace=ns,
        company_id="system",
        search_options={
            "channels": {"semantic": True, "lexical": True},
            "rerank": False,
        },
        namespace_service=di.namespace_service,
    )
    await r.add_document("d1", body, metadata={"category": "pets"}, name="n.txt")

    prov = get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID, billing_service=make_test_billing_service())
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
    di: FlowsDi,
) -> None:
    ns = f"test_rag_res_{uuid.uuid4().hex[:10]}"
    r = RAGResource(
        namespace=ns,
        namespace_service=di.namespace_service,
        billing_service=di.billing_service,
    )
    await r.add_document(
        "fid",
        "hello",
        metadata={"tag": "t"},
        name="n.txt",
    )

    prov = get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID, billing_service=make_test_billing_service())
    stored = await prov.get_document(ns, "fid")
    assert stored is not None
    assert stored.metadata.get("tag") == "t"
    assert stored.metadata.get("document_id") == "fid"


@pytest.mark.asyncio
async def test_add_document_merges_index_profile_config(
    di: FlowsDi,
) -> None:
    ns = f"test_rag_res_{uuid.uuid4().hex[:10]}"
    r = RAGResource(
        billing_service=di.billing_service,
        namespace=ns,
        namespace_service=di.namespace_service,
        index_profile_config={"split": {"chunk_size": 256}},
    )
    await r.add_document(
        "fid",
        "hello " * 20,
        metadata={"index_profile_config": {"split": {"strategy": "recursive"}}},
        name="n.txt",
        index_profile_config={"lexical": {"enabled": True}},
    )

    prov = get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID, billing_service=make_test_billing_service())
    stored = await prov.get_document(ns, "fid")
    assert stored is not None
    ir = stored.metadata["indexing_runtime"]
    assert ir["split"]["chunk_size"] == 256
    assert ir["split"]["strategy"] == "recursive"
    assert ir["lexical"]["enabled"] is True
