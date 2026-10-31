from __future__ import annotations

import uuid

import pytest

from apps.flows.di import FlowsDi
from apps.flows.src.runtime.llm_context_memory_store import (
    RAGLLMContextMemoryStore,
    _clamp_score,
    _parse_datetime,
    llm_context_memory_namespace_id,
)
from core.context import clear_context, get_context, set_context
from core.llm_context.memory import (
    LLMContextMemoryEpisode,
    LLMContextMemoryRecallRequest,
)
from core.llm_context.memory_compaction import LLM_CONTEXT_MEMORY_RECALL_CONTENT_METADATA_KEY
from core.models.identity_models import Namespace, NamespaceKind
from core.rag.constants import RAG_IN_PROCESS_PROVIDER_ID
from core.rag.factory import get_rag_provider
from tests.fixtures.auth import service_client_asgi_auth_context


class FakeRagProvider:
    def __init__(self) -> None:
        self.uploads: list[dict] = []

    async def upload_document_from_text(self, **kwargs):
        self.uploads.append(kwargs)
        return {"document_id": kwargs["metadata"]["document_id"]}


class FakeRagClient:
    def __init__(self, response: dict | None = None) -> None:
        self.response = response or {"results": []}
        self.searches: list[dict] = []

    async def search(self, namespace_id: str, query: str, **kwargs):
        self.searches.append({"namespace_id": namespace_id, "query": query, **kwargs})
        return self.response


class FakeNamespaceService:
    def __init__(self, exists: bool) -> None:
        self.exists = exists
        self.created: list[Namespace] = []

    async def get(self, namespace_id: str) -> Namespace | None:
        if not self.exists:
            return None
        return Namespace(
            name=namespace_id,
            company_id="system",
            kind=NamespaceKind.TECHNICAL,
        )

    async def get_or_create(
        self,
        namespace_id: str,
        *,
        description: str | None = None,
        kind: NamespaceKind | None = None,
    ) -> Namespace:
        _ = description
        resolved_kind = kind if kind is not None else NamespaceKind.TECHNICAL
        namespace = Namespace(
            name=namespace_id,
            company_id="system",
            kind=resolved_kind,
        )
        self.exists = True
        self.created.append(namespace)
        return namespace


@pytest.mark.asyncio
async def test_rag_memory_store_writes_and_recalls_scoped_episode(
    di: FlowsDi,
    rag_app,
    auth_headers_system: dict[str, str],
) -> None:
    _ = rag_app
    namespace_id = f"ctx-memory-{uuid.uuid4().hex[:10]}"
    marker = f"MEMORY_STORE_MARKER_{uuid.uuid4().hex[:10]}"
    store = RAGLLMContextMemoryStore(
        rag_provider=get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID),

        namespace_service=di.namespace_service,
        namespace_id=namespace_id,
    )

    try:
        await store.write_episode(
            LLMContextMemoryEpisode(
                memory_id=f"memory-{marker}",
                scope="session",
                session_id="flow:session-a",
                flow_id="flow",
                node_id="agent",
                user_id="user",
                content=f"{marker} billing preferences are remembered here.",
            )
        )

        with service_client_asgi_auth_context(auth_headers_system):
            found = await store.recall(
                LLMContextMemoryRecallRequest(
                    query=f"{marker} billing",
                    scope="session",
                    session_id="flow:session-a",
                    top_k=3,
                    search_options={
                        "channels": {"semantic": True, "lexical": True},
                        "rerank": False,
                    },
                )
            )
            missing = await store.recall(
                LLMContextMemoryRecallRequest(
                    query=f"{marker} billing",
                    scope="session",
                    session_id="flow:session-b",
                    top_k=3,
                    search_options={
                        "channels": {"semantic": True, "lexical": True},
                        "rerank": False,
                    },
                )
            )

        assert len(found) == 1
        assert marker in found[0].content
        assert found[0].scope == "session"
        assert found[0].session_id == "flow:session-a"
        assert missing == []
    finally:
        with service_client_asgi_auth_context(auth_headers_system):
            await get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID).delete_namespace(namespace_id)
            await di.namespace_service.delete(namespace_id)


@pytest.mark.asyncio
async def test_rag_memory_store_handles_empty_namespace_and_scope_filters() -> None:
    provider = FakeRagProvider()
    client = FakeRagClient()
    missing_ns = FakeNamespaceService(exists=False)
    store = RAGLLMContextMemoryStore(
        rag_provider=provider,
        rag_client=client,
        namespace_service=missing_ns,
        namespace_id="memory-test",
    )

    assert await store.recall(
        LLMContextMemoryRecallRequest(query="q", scope="session", session_id="s")
    ) == []
    assert client.searches == []

    await store.write_episode(
        LLMContextMemoryEpisode(
            memory_id="m1",
            content="hello",
            scope="company",
            title="Title",
            metadata={"custom": "yes"},
        )
    )
    assert missing_ns.created[0].name == "memory-test"
    assert provider.uploads[0]["metadata"]["custom"] == "yes"

    await store.recall(LLMContextMemoryRecallRequest(query="q", scope="session"))
    await store.recall(LLMContextMemoryRecallRequest(query="q", scope="node", flow_id="f"))
    await store.recall(LLMContextMemoryRecallRequest(query="q", scope="flow"))
    await store.recall(
        LLMContextMemoryRecallRequest(query="q", scope="node", flow_id="f", node_id="n")
    )
    await store.recall(LLMContextMemoryRecallRequest(query="q", scope="flow", flow_id="f"))

    filters = [call["filters"] for call in client.searches]
    assert filters == [
        {"company_id": "system", "memory_scope": "__missing_session__"},
        {"company_id": "system", "memory_scope": "__missing_node__"},
        {"company_id": "system", "memory_scope": "__missing_flow__"},
        {"company_id": "system", "memory_scope": "node", "flow_id": "f", "node_id": "n"},
        {"company_id": "system", "memory_scope": "flow", "flow_id": "f"},
    ]


@pytest.mark.asyncio
async def test_rag_memory_store_without_namespace_repository_and_result_coercion() -> None:
    provider = FakeRagProvider()
    client = FakeRagClient(
        {
            "results": [
                {
                    "content": "remembered",
                    "score": 2.0,
                    "document_id": "document-id",
                    "document_name": "doc",
                    "attributes": {
                        "memory_id": "memory-from-metadata",
                        "memory_scope": "company",
                        "session_id": "",
                        "created_at": "2026-05-25T00:00:00+00:00",
                        LLM_CONTEXT_MEMORY_RECALL_CONTENT_METADATA_KEY: "compact remembered",
                    },
                    "namespace": "memory-test",
                    "chunk_id": "chunk",
                    "provenance": {},
                }
            ]
        }
    )
    store = RAGLLMContextMemoryStore(
        rag_provider=provider,
        rag_client=client,
        namespace_service=None,
        namespace_id=None,
    )

    await store.write_episode(
        LLMContextMemoryEpisode(
            memory_id="m-no-namespace-repo",
            content="stored without namespace repository",
            scope="company",
        )
    )
    records = await store.recall(LLMContextMemoryRecallRequest(query="q", scope="company"))

    assert provider.uploads[0]["metadata"]["memory_id"] == "m-no-namespace-repo"
    assert records[0].memory_id == "memory-from-metadata"
    assert records[0].content == "compact remembered"
    assert records[0].score == 1.0
    assert records[0].session_id is None
    assert records[0].created_at is not None
    assert records[0].created_at.isoformat() == "2026-05-25T00:00:00+00:00"
    assert client.searches[0]["namespace_id"] == llm_context_memory_namespace_id("system")
    assert _clamp_score("bad-score") is None
    assert _parse_datetime(None) is None



@pytest.mark.asyncio
async def test_rag_memory_store_strict_error_paths() -> None:
    store = RAGLLMContextMemoryStore(
        rag_provider=FakeRagProvider(), rag_client=FakeRagClient({"results": "bad"}),
        namespace_service=None,
        namespace_id="memory-test",
    )
    with pytest.raises(ValueError, match="response.results"):
        await store.recall(LLMContextMemoryRecallRequest(query="q", scope="company"))

    strict_store = RAGLLMContextMemoryStore(
        rag_provider=FakeRagProvider(), rag_client=FakeRagClient({
                "results": [
                    {
                        "content": "remembered",
                        "score": 1.0,
                        "document_id": "document-id",
                        "document_name": "doc",
                        "attributes": {"memory_scope": "company"},
                        "namespace": "memory-test",
                        "chunk_id": "chunk",
                        "provenance": {},
                    }
                ]
            }
        ),
        namespace_service=None,
        namespace_id="memory-test",
    )
    with pytest.raises(ValueError, match="attributes.memory_id"):
        await strict_store.recall(LLMContextMemoryRecallRequest(query="q", scope="company"))

    invalid_created_at_store = RAGLLMContextMemoryStore(
        rag_provider=FakeRagProvider(), rag_client=FakeRagClient({
                "results": [
                    {
                        "content": "remembered",
                        "score": 1.0,
                        "document_id": "document-id",
                        "document_name": "doc",
                        "attributes": {
                            "memory_id": "memory-id",
                            "memory_scope": "company",
                            "created_at": "not-a-date",
                        },
                        "namespace": "memory-test",
                        "chunk_id": "chunk",
                        "provenance": {},
                    }
                ]
            }
        ),
        namespace_service=None,
        namespace_id="memory-test",
    )
    with pytest.raises(ValueError, match="attributes.created_at"):
        await invalid_created_at_store.recall(
            LLMContextMemoryRecallRequest(query="q", scope="company")
        )

    context = get_context()
    clear_context()
    try:
        with pytest.raises(ValueError, match="active company"):
            await store.recall(LLMContextMemoryRecallRequest(query="q", scope="company"))
    finally:
        if context is not None:
            set_context(context)


def test_memory_namespace_id_is_stable_and_sanitized() -> None:
    assert llm_context_memory_namespace_id(" ACME Inc! ").startswith("llm-memory-acme-inc-")
    assert llm_context_memory_namespace_id("   ").startswith("llm-memory-company-")
