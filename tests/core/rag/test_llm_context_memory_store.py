from __future__ import annotations

import uuid

import pytest

from apps.flows.src.container import FlowContainer
from core.config import get_settings
from core.context import clear_context, get_context, set_context
from core.llm_context import (
    LLM_CONTEXT_MEMORY_RECALL_CONTENT_METADATA_KEY,
    LLMContextMemoryEpisode,
    LLMContextMemoryRecallRequest,
)
from core.models.identity_models import Namespace
from core.rag.llm_context_memory_store import (
    RAGLLMContextMemoryStore,
    _clamp_score,
    _parse_datetime,
    llm_context_memory_namespace_id,
)
from tests.fixtures.auth import service_client_asgi_auth_context


class FakeRAGRepository:
    def __init__(self, response: dict | None = None) -> None:
        self.response = response or {"results": []}
        self.uploads: list[dict] = []
        self.searches: list[dict] = []

    async def upload_text(self, **kwargs):
        self.uploads.append(kwargs)
        return {"document_id": kwargs["metadata"]["document_id"]}

    async def search_namespace(self, **kwargs):
        self.searches.append(kwargs)
        return self.response


class FakeNamespaceRepository:
    def __init__(self, exists: bool) -> None:
        self.exists = exists
        self.set_calls: list[Namespace] = []

    async def get(self, namespace_id: str) -> Namespace | None:
        if not self.exists:
            return None
        return Namespace(name=namespace_id, company_id="system")

    async def set(self, namespace: Namespace) -> None:
        self.exists = True
        self.set_calls.append(namespace)


@pytest.fixture
def flow_container_for_memory() -> FlowContainer:
    settings = get_settings()
    return FlowContainer(db_url=settings.database.flows_url, shared_db_url=settings.database.shared_url)


@pytest.mark.asyncio
async def test_rag_memory_store_writes_and_recalls_scoped_episode(
    flow_container_for_memory: FlowContainer,
    rag_app,
    auth_headers_system: dict[str, str],
) -> None:
    _ = rag_app
    namespace_id = f"ctx-memory-{uuid.uuid4().hex[:10]}"
    marker = f"MEMORY_STORE_MARKER_{uuid.uuid4().hex[:10]}"
    store = RAGLLMContextMemoryStore(
        repository=flow_container_for_memory.rag_repository,
        namespace_repository=flow_container_for_memory.namespace_repository,
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
            await flow_container_for_memory.rag_repository.delete_namespace(namespace_id)
            await flow_container_for_memory.namespace_repository.delete(namespace_id)


@pytest.mark.asyncio
async def test_rag_memory_store_handles_empty_namespace_and_scope_filters() -> None:
    repo = FakeRAGRepository()
    missing_ns = FakeNamespaceRepository(exists=False)
    store = RAGLLMContextMemoryStore(
        repository=repo,
        namespace_repository=missing_ns,
        namespace_id="memory-test",
    )

    assert await store.recall(
        LLMContextMemoryRecallRequest(query="q", scope="session", session_id="s")
    ) == []
    assert repo.searches == []

    await store.write_episode(
        LLMContextMemoryEpisode(
            memory_id="m1",
            content="hello",
            scope="company",
            title="Title",
            metadata={"custom": "yes"},
        )
    )
    assert missing_ns.set_calls[0].name == "memory-test"
    assert repo.uploads[0]["metadata"]["custom"] == "yes"

    await store.recall(LLMContextMemoryRecallRequest(query="q", scope="session"))
    await store.recall(LLMContextMemoryRecallRequest(query="q", scope="node", flow_id="f"))
    await store.recall(LLMContextMemoryRecallRequest(query="q", scope="flow"))
    await store.recall(
        LLMContextMemoryRecallRequest(query="q", scope="node", flow_id="f", node_id="n")
    )
    await store.recall(LLMContextMemoryRecallRequest(query="q", scope="flow", flow_id="f"))

    filters = [call["bind"].filters for call in repo.searches]
    assert filters == [
        {"company_id": "system", "memory_scope": "__missing_session__"},
        {"company_id": "system", "memory_scope": "__missing_node__"},
        {"company_id": "system", "memory_scope": "__missing_flow__"},
        {"company_id": "system", "memory_scope": "node", "flow_id": "f", "node_id": "n"},
        {"company_id": "system", "memory_scope": "flow", "flow_id": "f"},
    ]


@pytest.mark.asyncio
async def test_rag_memory_store_without_namespace_repository_and_result_coercion() -> None:
    repo = FakeRAGRepository(
        {
            "results": [
                {
                    "content": "remembered",
                    "score": 2.0,
                    "document_id": "fallback-id",
                    "document_name": "doc",
                    "metadata": {
                        "memory_scope": "company",
                        "session_id": "",
                        "created_at": "not-a-date",
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
        repository=repo,
        namespace_repository=None,
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

    assert repo.uploads[0]["metadata"]["memory_id"] == "m-no-namespace-repo"
    assert records[0].memory_id == "fallback-id"
    assert records[0].content == "compact remembered"
    assert records[0].score == 1.0
    assert records[0].session_id is None
    assert records[0].created_at is None
    assert repo.searches[0]["bind"].namespace == llm_context_memory_namespace_id("system")
    assert _clamp_score("bad-score") is None
    assert _parse_datetime(None) is None


@pytest.mark.asyncio
async def test_rag_memory_store_strict_error_paths() -> None:
    store = RAGLLMContextMemoryStore(
        repository=FakeRAGRepository({"results": "bad"}),
        namespace_repository=None,
        namespace_id="memory-test",
    )
    with pytest.raises(ValueError, match="response.results"):
        await store.recall(LLMContextMemoryRecallRequest(query="q", scope="company"))

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
