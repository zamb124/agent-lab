"""Контракт RAGResource: search через HTTP RAG API; add_document через pgvector."""

import pytest

from apps.flows.di import FlowsDi
from apps.flows.src.resources.rag_resource import RAGResource
from core.clients.service_client import ServiceClient


@pytest.mark.asyncio
async def test_search_posts_to_rag_api_with_search_options(
    monkeypatch,
    di: FlowsDi,
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
        billing_service=di.billing_service,
        namespace="ns-a",
        company_id="system",
        search_options={"channels": {"semantic": True, "lexical": True}},
        namespace_service=di.namespace_service,
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


