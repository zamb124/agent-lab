"""Контракт RAGResource: search через HTTP RAG API; add_document через pgvector."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.flows.src.container import FlowContainer
from core.clients.service_client import ServiceClient
from core.rag.providers.pgvector_provider import PgVectorProvider
from core.rag.rag_resource import RAGResource


@pytest.fixture
def flow_container_for_rag_unit() -> FlowContainer:
    return FlowContainer(
        db_url="postgresql://unused:unused@127.0.0.1:5432/unused_flows",
        shared_db_url="postgresql://unused:unused@127.0.0.1:5432/unused_shared",
    )


@pytest.mark.asyncio
async def test_search_posts_to_rag_api_with_search_options(
    monkeypatch,
    flow_container_for_rag_unit: FlowContainer,
) -> None:
    captured: dict = {}

    async def fake_post(self, service: str, path: str, **kwargs) -> dict:
        captured["service"] = service
        captured["path"] = path
        captured["json"] = kwargs.get("json")
        return {
            "results": [
                {
                    "content": "c",
                    "score": 0.9,
                    "document_id": "d1",
                    "metadata": {"k": "v"},
                    "document_name": "n",
                    "namespace": "ns-a",
                }
            ],
            "query": kwargs["json"]["query"],
            "namespace_id": "ns-a",
            "provider": "pgvector",
        }

    monkeypatch.setattr(ServiceClient, "post", fake_post)

    r = RAGResource(
        namespace="ns-a",
        company_id="system",
        search_options={"channels": {"semantic": True, "lexical": True}},
        container=flow_container_for_rag_unit,
    )
    await r.search("q", top_k=3)

    assert {
        "service": captured["service"],
        "path_has_namespaces_prefix": "/rag/api/v1/namespaces/" in captured["path"],
        "path_has_ns": "ns-a" in captured["path"],
        "path_is_search": captured["path"].endswith("/search") or "/search?" in captured["path"],
        "json_query": captured["json"]["query"],
        "json_limit": captured["json"]["limit"],
        "json_channels": captured["json"]["channels"],
    } == {
        "service": "rag",
        "path_has_namespaces_prefix": True,
        "path_has_ns": True,
        "path_is_search": True,
        "json_query": "q",
        "json_limit": 3,
        "json_channels": {"semantic": True, "lexical": True},
    }


@pytest.mark.asyncio
async def test_add_document_passes_metadata_through(
    flow_container_for_rag_unit: FlowContainer,
) -> None:
    doc = MagicMock()
    doc.document_id = "fid"
    mock_upload = AsyncMock(return_value=doc)
    mock_namespace_get = AsyncMock(return_value=object())

    with (
        patch.object(
            flow_container_for_rag_unit.namespace_repository,
            "get",
            mock_namespace_get,
        ),
        patch.object(PgVectorProvider, "upload_document_from_text", mock_upload),
    ):
        r = RAGResource(namespace="ns-a", container=flow_container_for_rag_unit)
        await r.add_document(
            "fid",
            "hello",
            metadata={"tag": "t"},
            name="n.txt",
        )

    mock_upload.assert_awaited_once()
    kw = mock_upload.await_args.kwargs
    meta = kw["metadata"]
    assert {k: meta[k] for k in ("document_id", "tag")} == {"document_id": "fid", "tag": "t"}


@pytest.mark.asyncio
async def test_add_document_merges_index_profile_config(
    flow_container_for_rag_unit: FlowContainer,
) -> None:
    doc = MagicMock()
    doc.document_id = "fid"
    mock_upload = AsyncMock(return_value=doc)
    mock_namespace_get = AsyncMock(return_value=object())

    with (
        patch.object(
            flow_container_for_rag_unit.namespace_repository,
            "get",
            mock_namespace_get,
        ),
        patch.object(PgVectorProvider, "upload_document_from_text", mock_upload),
    ):
        r = RAGResource(
            namespace="ns-a",
            container=flow_container_for_rag_unit,
            index_profile_config={"split": {"chunk_size": 256}},
        )
        await r.add_document(
            "fid",
            "hello",
            metadata={"index_profile_config": {"split": {"strategy": "semantic"}}},
            name="n.txt",
            index_profile_config={"parsing": {"engine": "unstructured"}},
        )

    mock_upload.assert_awaited_once()
    kw = mock_upload.await_args.kwargs
    meta = kw["metadata"]
    ipc = meta["index_profile_config"]
    assert {k: meta[k] for k in ("document_id",)} == {"document_id": "fid"}
    assert {
        "split": ipc["split"],
        "parsing": ipc["parsing"],
    } == {
        "split": {"chunk_size": 256, "strategy": "semantic"},
        "parsing": {"engine": "unstructured"},
    }
