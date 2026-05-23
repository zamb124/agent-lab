from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from apps.flows.src.container import FlowContainer
from apps.flows.src.models import BranchConfig, Edge, FlowConfig, ResourceDefinition, ResourceType
from apps.flows.src.models.enums import MergeMode
from apps.flows.src.runtime.a2a_messages import build_assistant_message, build_user_message
from core.llm_context import LLMContextMemoryEpisode
from core.rag.llm_context_memory_store import llm_context_memory_namespace_id
from core.rag.rag_resource import RAGResource
from core.state import ExecutionState
from tests.fixtures.auth import service_client_asgi_auth_context

pytestmark = pytest.mark.asyncio

CaptureReader = Callable[[], Awaitable[list[dict[str, Any]]]]


BASE_BRANCH = "default"
SKILL_BRANCH = "skill_override"
NODE_BRANCH = "node_override"
SHARED_BRANCH = "shared_resource"
RETRIEVAL_OFF_BRANCH = "retrieval_off"


def _context_config(
    *,
    retrieval_mode: str = "hybrid",
    rag_tokens: int = 1_200,
    top_k: int = 4,
) -> dict[str, Any]:
    return {
        "mode": "smart",
        "budget": {
            "max_input_tokens": 4_096,
            "output_reserve_tokens": 64,
            "reasoning_reserve_tokens": 0,
            "safety_buffer_tokens": 64,
            "active_window_tokens": 20,
            "memory_tokens": 512,
            "rag_tokens": rag_tokens,
            "tool_result_tokens": 64,
        },
        "memory": "session",
        "retrieval": {"mode": retrieval_mode, "top_k": top_k, "rerank": False},
        "compaction": "auto",
        "cache": "provider_hints",
    }


def _rag_config(
    *,
    namespace: str,
    collection_id: str,
    top_k: int = 4,
) -> dict[str, Any]:
    return {
        "namespace": namespace,
        "company_id": "system",
        "default_top_k": top_k,
        "filters": {"collection_id": collection_id},
        "search_options": {
            "channels": {"semantic": True, "lexical": True},
            "rerank": False,
        },
    }


def _agent_node(
    *,
    prompt: str,
    resources: dict[str, Any] | None = None,
    llm_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    node: dict[str, Any] = {
        "type": "llm_node",
        "name": "Context Layer E2E Agent",
        "prompt": prompt,
        "llm": {"provider": "mock", "model": "mock-gpt-4", "temperature": 0.0},
        "llm_context_resource_key": "ctx",
        "tools": [],
    }
    if resources is not None:
        node["resources"] = resources
    if llm_context is not None:
        node["llm_context"] = llm_context
    return node


def _flow_config(
    *,
    flow_id: str,
    namespaces: dict[str, str],
    collections: dict[str, str],
    shared_ctx_id: str,
    shared_rag_id: str,
) -> FlowConfig:
    base_node = _agent_node(prompt=f"SYSTEM_BRANCH_{BASE_BRANCH}_{flow_id}")
    return FlowConfig(
        flow_id=flow_id,
        name="Context Layer E2E Matrix",
        entry="agent",
        nodes={"agent": base_node},
        edges=[Edge(from_node="agent", to_node=None)],
        resources={
            "ctx": {"type": "llm_context", "config": _context_config()},
            "kb": {
                "type": "rag",
                "config": _rag_config(
                    namespace=namespaces[BASE_BRANCH],
                    collection_id=collections[BASE_BRANCH],
                ),
            },
        },
        branches={
            SKILL_BRANCH: BranchConfig(
                name="Skill override",
                resources={
                    "ctx": {
                        "type": "llm_context",
                        "config": _context_config(top_k=2, rag_tokens=800),
                    },
                    "kb": {
                        "type": "rag",
                        "config": _rag_config(
                            namespace=namespaces[SKILL_BRANCH],
                            collection_id=collections[SKILL_BRANCH],
                            top_k=2,
                        ),
                    },
                },
            ),
            NODE_BRANCH: BranchConfig(
                name="Node override",
                nodes_mode=MergeMode.MERGE,
                nodes={
                    "agent": {
                        "prompt": f"SYSTEM_BRANCH_{NODE_BRANCH}_{flow_id}",
                        "llm_context": {"budget": {"active_window_tokens": 20}},
                        "resources": {
                            "kb": {
                                "type": "rag",
                                "config": _rag_config(
                                    namespace=namespaces[NODE_BRANCH],
                                    collection_id=collections[NODE_BRANCH],
                                    top_k=3,
                                ),
                            }
                        },
                    }
                },
            ),
            SHARED_BRANCH: BranchConfig(
                name="Shared resources",
                nodes_mode=MergeMode.MERGE,
                nodes={"agent": {"prompt": f"SYSTEM_BRANCH_{SHARED_BRANCH}_{flow_id}"}},
                resources={
                    "ctx": {
                        "resource_id": shared_ctx_id,
                        "config": {"retrieval": {"top_k": 3}, "budget": {"rag_tokens": 900}},
                    },
                    "kb": {
                        "resource_id": shared_rag_id,
                        "config": {"filters": {"collection_id": collections[SHARED_BRANCH]}},
                    },
                },
            ),
            RETRIEVAL_OFF_BRANCH: BranchConfig(
                name="Retrieval off",
                nodes_mode=MergeMode.MERGE,
                nodes={
                    "agent": {
                        "prompt": f"SYSTEM_BRANCH_{RETRIEVAL_OFF_BRANCH}_{flow_id}",
                        "llm_context": {"retrieval": {"mode": "off", "rerank": False}},
                    }
                },
            ),
        },
    )


async def _store_shared_resources(
    *,
    container: FlowContainer,
    shared_ctx_id: str,
    shared_rag_id: str,
    shared_namespace: str,
) -> None:
    await container.resource_repository.set(
        ResourceDefinition(
            resource_id=shared_ctx_id,
            type=ResourceType.LLM_CONTEXT,
            name="Shared context profile",
            config=_context_config(top_k=1, rag_tokens=600),
        )
    )
    await container.resource_repository.set(
        ResourceDefinition(
            resource_id=shared_rag_id,
            type=ResourceType.RAG,
            name="Shared RAG bind",
            config=_rag_config(
                namespace=shared_namespace,
                collection_id="will-be-overridden",
                top_k=1,
            ),
        )
    )


async def _index_rag_document(
    *,
    container: FlowContainer,
    namespace: str,
    collection_id: str,
    marker: str,
) -> None:
    rag = RAGResource(
        namespace=namespace,
        company_id="system",
        container=container,
        search_options={
            "channels": {"semantic": True, "lexical": True},
            "rerank": False,
        },
    )
    await rag.add_document(
        f"doc-{marker}",
        f"{marker} context-layer-rag-answer searchable knowledge about billing limits.",
        metadata={"collection_id": collection_id, "marker": marker},
        name=f"{marker}.md",
    )


def _stale_messages(*, branch_id: str, context_id: str, task_id: str) -> list[Any]:
    old_text = f"OLD_CONTEXT_SHOULD_BE_TRIMMED_{branch_id} " + ("obsolete " * 80)
    return [
        build_user_message(old_text, "agent", context_id=context_id, task_id=task_id),
        build_assistant_message(
            f"OLD_ASSISTANT_SHOULD_BE_TRIMMED_{branch_id} " + ("obsolete " * 80),
            "agent",
            context_id=context_id,
            task_id=task_id,
        ),
    ]


async def _run_branch(
    *,
    container: FlowContainer,
    flow_id: str,
    branch_id: str,
    query_marker: str,
    response_marker: str,
    capture: CaptureReader,
    mock_llm_with_queue: Callable[[list[Any]], Any],
    auth_headers_system: dict[str, str],
    context_id: str | None = None,
    initial_messages: list[Any] | None = None,
    memory_summary_marker: str | None = None,
) -> dict[str, Any]:
    expect_compaction = initial_messages is None or len(initial_messages) > 1
    queued_responses = [{"type": "text", "content": f"LLM_RESPONSE_{response_marker}"}]
    if expect_compaction:
        summary_marker = memory_summary_marker or query_marker
        queued_responses.append(
            {
                "type": "text",
                "content": f"SUMMARY_{response_marker} remembered {summary_marker}",
            }
        )
    mock_llm_with_queue(queued_responses)

    context_id = context_id or f"context-{branch_id}-{uuid.uuid4().hex[:8]}"
    task_id = f"task-{branch_id}-{uuid.uuid4().hex[:8]}"
    state = ExecutionState(
        task_id=task_id,
        context_id=context_id,
        user_id="test_user",
        session_id=f"{flow_id}:{context_id}",
        branch_id=branch_id,
        content=f"{query_marker} please answer from the relevant knowledge base",
        messages=(
            initial_messages
            if initial_messages is not None
            else _stale_messages(branch_id=branch_id, context_id=context_id, task_id=task_id)
        ),
    )

    before_count = len(await capture())
    with service_client_asgi_auth_context(auth_headers_system):
        flow = await container.flow_factory.get_flow(flow_id, branch_id=branch_id)
        assert flow is not None
        result = await flow.run(state)

    calls = await capture()
    assert result["response"] == f"LLM_RESPONSE_{response_marker}"
    new_calls = calls[before_count:]
    main_calls = [
        call
        for call in new_calls
        if query_marker in _call_text(call)
        and "Compress this closed conversation segment" not in _call_text(call)
    ]
    assert main_calls
    if expect_compaction:
        await _wait_for_compacted_memory(
            container=container,
            flow_id=flow_id,
            session_id=f"{flow_id}:{context_id}",
        )
    return main_calls[-1]


def _call_text(call: dict[str, Any]) -> str:
    return "\n".join(str(message.get("text") or "") for message in call["messages"])


async def _wait_for_compacted_memory(
    *,
    container: FlowContainer,
    flow_id: str,
    session_id: str,
) -> None:
    namespace_id = llm_context_memory_namespace_id("system")
    filters = {
        "flow_id": flow_id,
        "session_id": session_id,
        "source": "llm_context_compaction",
    }
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        documents = await container.rag_repository.list_with_filters(
            namespace_id,
            filters,
            limit=10,
        )
        if documents:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"Timed out waiting for compacted LLM memory: {filters}")


async def test_context_layer_e2e_runs_flow_branches_with_rag_and_context_budget(
    app,
    rag_app,
    container: FlowContainer,
    unique_id: str,
    mock_llm_capture: CaptureReader,
    mock_llm_with_queue,
    auth_headers_system: dict[str, str],
) -> None:
    _ = app, rag_app
    flow_id = f"ctx_layer_e2e_{unique_id}"
    shared_ctx_id = f"ctx_layer_shared_ctx_{unique_id}"
    shared_rag_id = f"ctx_layer_shared_rag_{unique_id}"

    all_branches = [
        BASE_BRANCH,
        SKILL_BRANCH,
        NODE_BRANCH,
        SHARED_BRANCH,
        RETRIEVAL_OFF_BRANCH,
    ]
    markers = {branch: f"RAG_MARKER_{branch}_{unique_id}" for branch in all_branches}
    query_markers = {branch: f"QUERY_MARKER_{branch}_{unique_id}" for branch in all_branches}
    namespaces = {branch: f"ctx-layer-{branch}-{unique_id}" for branch in all_branches}
    shared_namespace = f"ctx-layer-shared-{unique_id}"
    collections = {branch: f"collection-{branch}-{unique_id}" for branch in all_branches}
    base_context_id = f"context-memory-{unique_id}"
    auto_memory_context_id = f"context-auto-memory-{unique_id}"
    memory_id = f"ctx-memory-{unique_id}"
    memory_marker = f"MEMORY_MARKER_{unique_id}"
    auto_memory_query_marker = f"AUTO_MEMORY_QUERY_{unique_id}"
    auto_memory_payload_marker = f"AUTO_MEMORY_PAYLOAD_{unique_id}"

    await _store_shared_resources(
        container=container,
        shared_ctx_id=shared_ctx_id,
        shared_rag_id=shared_rag_id,
        shared_namespace=shared_namespace,
    )
    await container.flow_repository.set(
        _flow_config(
            flow_id=flow_id,
            namespaces=namespaces,
            collections=collections,
            shared_ctx_id=shared_ctx_id,
            shared_rag_id=shared_rag_id,
        )
    )

    indexed_namespaces = [*namespaces.values(), shared_namespace]
    try:
        for branch in (BASE_BRANCH, SKILL_BRANCH, NODE_BRANCH, RETRIEVAL_OFF_BRANCH):
            await _index_rag_document(
                container=container,
                namespace=namespaces[branch],
                collection_id=collections[branch],
                marker=markers[branch],
            )
        await _index_rag_document(
            container=container,
            namespace=shared_namespace,
            collection_id=collections[SHARED_BRANCH],
            marker=markers[SHARED_BRANCH],
        )
        await _index_rag_document(
            container=container,
            namespace=shared_namespace,
            collection_id="wrong-shared-collection",
            marker=f"WRONG_SHARED_COLLECTION_{unique_id}",
        )
        await container.llm_context_memory_store.write_episode(
            LLMContextMemoryEpisode(
                memory_id=memory_id,
                scope="session",
                session_id=f"{flow_id}:{base_context_id}",
                flow_id=flow_id,
                branch_id=BASE_BRANCH,
                node_id="agent",
                user_id="test_user",
                content=(
                    f"{memory_marker} {query_markers[BASE_BRANCH]} remembered billing preference."
                ),
            )
        )
        await _run_branch(
            container=container,
            flow_id=flow_id,
            branch_id=BASE_BRANCH,
            query_marker=f"AUTO_MEMORY_SEED_{unique_id}",
            response_marker="auto_memory_seed",
            capture=mock_llm_capture,
            mock_llm_with_queue=mock_llm_with_queue,
            auth_headers_system=auth_headers_system,
            context_id=auto_memory_context_id,
            memory_summary_marker=auto_memory_payload_marker,
            initial_messages=[
                build_user_message(
                    (
                        f"{auto_memory_query_marker} {auto_memory_payload_marker} "
                        + ("closed preference " * 12)
                    ),
                    "agent",
                    context_id=auto_memory_context_id,
                    task_id=f"seed-{unique_id}",
                ),
                build_assistant_message(
                    "seed reply " + ("closed answer " * 12),
                    "agent",
                    context_id=auto_memory_context_id,
                    task_id=f"seed-{unique_id}",
                ),
            ],
        )
        await _wait_for_compacted_memory(
            container=container,
            flow_id=flow_id,
            session_id=f"{flow_id}:{auto_memory_context_id}",
        )
        auto_memory_call = await _run_branch(
            container=container,
            flow_id=flow_id,
            branch_id=BASE_BRANCH,
            query_marker=auto_memory_query_marker,
            response_marker="auto_memory_recall",
            capture=mock_llm_capture,
            mock_llm_with_queue=mock_llm_with_queue,
            auth_headers_system=auth_headers_system,
            context_id=auto_memory_context_id,
            initial_messages=[],
        )

        calls: dict[str, dict[str, Any]] = {}
        for branch in all_branches:
            calls[branch] = await _run_branch(
                container=container,
                flow_id=flow_id,
                branch_id=branch,
                query_marker=query_markers[branch],
                response_marker=branch,
                capture=mock_llm_capture,
                mock_llm_with_queue=mock_llm_with_queue,
                auth_headers_system=auth_headers_system,
                context_id=base_context_id if branch == BASE_BRANCH else None,
            )

        prompt_by_branch = {
            branch: _call_text(call)
            for branch, call in calls.items()
        }

        for branch, prompt in prompt_by_branch.items():
            assert query_markers[branch] in prompt
            assert f"OLD_CONTEXT_SHOULD_BE_TRIMMED_{branch}" not in prompt
            assert f"OLD_ASSISTANT_SHOULD_BE_TRIMMED_{branch}" not in prompt

        assert markers[BASE_BRANCH] in prompt_by_branch[BASE_BRANCH]
        assert memory_marker in prompt_by_branch[BASE_BRANCH]
        assert auto_memory_payload_marker in _call_text(auto_memory_call)
        assert "closed preference" not in _call_text(auto_memory_call)
        assert markers[SKILL_BRANCH] in prompt_by_branch[SKILL_BRANCH]
        assert markers[NODE_BRANCH] in prompt_by_branch[NODE_BRANCH]
        assert markers[SHARED_BRANCH] in prompt_by_branch[SHARED_BRANCH]
        assert markers[RETRIEVAL_OFF_BRANCH] not in prompt_by_branch[RETRIEVAL_OFF_BRANCH]

        assert markers[BASE_BRANCH] not in prompt_by_branch[SKILL_BRANCH]
        assert markers[BASE_BRANCH] not in prompt_by_branch[NODE_BRANCH]
        assert markers[BASE_BRANCH] not in prompt_by_branch[SHARED_BRANCH]
        assert memory_marker not in prompt_by_branch[SKILL_BRANCH]
        assert f"WRONG_SHARED_COLLECTION_{unique_id}" not in prompt_by_branch[SHARED_BRANCH]

        assert f"SYSTEM_BRANCH_{NODE_BRANCH}_{flow_id}" in prompt_by_branch[NODE_BRANCH]
        assert f"SYSTEM_BRANCH_{SHARED_BRANCH}_{flow_id}" in prompt_by_branch[SHARED_BRANCH]
        assert f"SYSTEM_BRANCH_{RETRIEVAL_OFF_BRANCH}_{flow_id}" in prompt_by_branch[
            RETRIEVAL_OFF_BRANCH
        ]
    finally:
        with service_client_asgi_auth_context(auth_headers_system):
            await container.flow_repository.delete(flow_id)
            await container.resource_repository.delete(shared_ctx_id)
            await container.resource_repository.delete(shared_rag_id)
            memory_namespace = llm_context_memory_namespace_id("system")
            await container.rag_repository.delete_document(memory_namespace, memory_id)
            compacted_docs = await container.rag_repository.list_with_filters(
                memory_namespace,
                {"flow_id": flow_id, "source": "llm_context_compaction"},
                limit=100,
            )
            for doc in compacted_docs:
                await container.rag_repository.delete_document(memory_namespace, doc.document_id)
            for namespace in indexed_namespaces:
                await container.rag_repository.delete_namespace(namespace)
                await container.namespace_repository.delete(namespace)
