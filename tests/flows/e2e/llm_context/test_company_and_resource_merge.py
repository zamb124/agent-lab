"""Company-level resources, branch overrides, RAG, and memory roundtrip."""
from __future__ import annotations

import pytest

from apps.flows.di import FlowsDi
from apps.flows.src.models import BranchConfig, Edge, FlowConfig
from apps.flows.src.models.enums import MergeMode
from core.llm_context.memory import LLMContextMemoryEpisode
from tests.flows.e2e.llm_context.harness import (
    call_text,
    cleanup_flow_context,
    context_config,
    index_rag_document,
    rag_config,
    run_context_flow,
    stale_messages,
    store_context_resource,
    wait_for_compacted_memory,
)

pytestmark = pytest.mark.asyncio


async def test_context_layer_merges_branch_resources_and_recalls_memory(
    app,
    rag_app,
    di: FlowsDi,
    unique_id: str,
    mock_llm_capture,
    mock_llm_with_queue,
    auth_headers_system: dict[str, str],
    system_user_id: str,
) -> None:
    """Ветки изолируют RAG, сохраняют memory и применяют node/resource overrides."""
    _ = app, rag_app
    flow_id = f"ctx_layer_e2e_{unique_id}"
    branches = ("default", "node_override", "shared_resource", "retrieval_off")
    namespaces = {branch: f"ctx-layer-{branch}-{unique_id}" for branch in branches}
    collections = {branch: f"collection-{branch}-{unique_id}" for branch in branches}
    markers = {branch: f"RAG_MARKER_{branch}_{unique_id}" for branch in branches}
    shared_ctx_id = f"ctx_layer_shared_ctx_{unique_id}"
    shared_namespace = f"ctx-layer-shared-{unique_id}"
    shared_collection = f"collection-shared-{unique_id}"
    memory_marker = f"MEMORY_MARKER_{unique_id}"
    base_context_id = f"context-memory-{unique_id}"

    flow_config = FlowConfig(
        flow_id=flow_id,
        name="Context layer resource merge",
        entry="agent",
        nodes={
            "agent": {
                "type": "llm_node",
                "name": "Context layer agent",
                "prompt": f"SYSTEM_DEFAULT_{flow_id}",
                "llm": {"provider": "mock", "model": "mock-gpt-4", "temperature": 0.0},
                "llm_context_resource_key": "ctx",
                "tools": [],
            }
        },
        edges=[Edge(from_node="agent", to_node=None)],
        resources={
            "ctx": {"type": "llm_context", "config": context_config()},
            "kb": {
                "type": "rag",
                "config": rag_config(
                    namespace=namespaces["default"], collection_id=collections["default"]
                ),
            },
        },
        branches={
            "node_override": BranchConfig(
                name="Node override",
                nodes_mode=MergeMode.MERGE,
                nodes={
                    "agent": {
                        "prompt": f"SYSTEM_NODE_{flow_id}",
                        "llm_context": {"budget": {"active_window_tokens": 20}},
                        "resources": {
                            "kb": {
                                "type": "rag",
                                "config": rag_config(
                                    namespace=namespaces["node_override"],
                                    collection_id=collections["node_override"],
                                ),
                            }
                        },
                    }
                },
            ),
            "shared_resource": BranchConfig(
                name="Shared resource",
                nodes_mode=MergeMode.MERGE,
                nodes={"agent": {"prompt": f"SYSTEM_SHARED_{flow_id}"}},
                resources={
                    "ctx": {"resource_id": shared_ctx_id},
                    "kb": {
                        "type": "rag",
                        "config": rag_config(
                            namespace=shared_namespace, collection_id=shared_collection
                        ),
                    },
                },
            ),
            "retrieval_off": BranchConfig(
                name="Retrieval off",
                nodes_mode=MergeMode.MERGE,
                nodes={
                    "agent": {
                        "llm_context": {"retrieval": {"mode": "off", "rerank": False}}
                    }
                },
            ),
        },
    )
    await store_context_resource(
        di=di,
        resource_id=shared_ctx_id,
        config=context_config(rag_tokens=900),
    )
    await FlowConfig.create_version(flow_config)
    indexed_namespaces = [*namespaces.values(), shared_namespace]
    try:
        for branch in ("default", "node_override", "retrieval_off"):
            await index_rag_document(
                di=di,
                namespace=namespaces[branch],
                collection_id=collections[branch],
                marker=markers[branch],
            )
        await index_rag_document(
            di=di,
            namespace=shared_namespace,
            collection_id=shared_collection,
            marker=markers["shared_resource"],
        )
        await di.node_constructor.llm_context_memory_store.write_episode(
            LLMContextMemoryEpisode(
                memory_id=f"memory-{unique_id}",
                scope="session",
                session_id=f"{flow_id}:{base_context_id}",
                flow_id=flow_id,
                branch_id="default",
                node_id="agent",
                user_id=system_user_id,
                content=memory_marker,
            )
        )

        prompts: dict[str, str] = {}
        for branch in branches:
            query = f"QUERY_{branch}_{unique_id}"
            call, state = await run_context_flow(
                di=di,
                flow_id=flow_id,
                branch_id=branch,
                query=query,
                response=f"RESPONSE_{branch}",
                capture=mock_llm_capture,
                mock_llm_with_queue=mock_llm_with_queue,
                auth_headers_system=auth_headers_system,
                context_id=base_context_id if branch == "default" else f"context-{branch}-{unique_id}",
                initial_messages=stale_messages(
                    context_id=base_context_id if branch == "default" else f"context-{branch}-{unique_id}",
                    task_id=f"task-{branch}-{unique_id}",
                    marker=f"OLD_CONTEXT_{branch}_{unique_id}",
                ),
            )
            await wait_for_compacted_memory(
                di=di, flow_id=flow_id, session_id=state.session_id
            )
            prompts[branch] = call_text(call)
            assert query in prompts[branch]
            assert f"OLD_CONTEXT_{branch}_{unique_id}" not in prompts[branch]

        assert markers["default"] in prompts["default"]
        assert memory_marker in prompts["default"]
        assert markers["node_override"] in prompts["node_override"]
        assert markers["shared_resource"] in prompts["shared_resource"]
        assert markers["retrieval_off"] not in prompts["retrieval_off"]
        assert markers["default"] not in prompts["node_override"]
        assert markers["default"] not in prompts["shared_resource"]
        assert "SYSTEM_NODE_" in prompts["node_override"]
        assert "SYSTEM_SHARED_" in prompts["shared_resource"]
    finally:
        await cleanup_flow_context(
            di=di,
            flow_id=flow_id,
            namespaces=indexed_namespaces,
            auth_headers_system=auth_headers_system,
            resource_ids=[shared_ctx_id],
        )
