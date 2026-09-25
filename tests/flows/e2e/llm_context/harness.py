"""Общий E2E harness для контекстного слоя LLM."""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from apps.flows.di import FlowsDi
from apps.flows.src.models import Edge, FlowConfig, ResourceDefinition, ResourceType
from apps.flows.src.runtime.a2a_messages import build_assistant_message, build_user_message
from core.context import get_context
from core.db.models.rag import VectorDocument
from core.rag.llm_context_memory_store import llm_context_memory_namespace_id
from core.rag.rag_resource import RAGResource
from core.state import ExecutionState
from tests.fixtures.auth import service_client_asgi_auth_context
from tests.flows.durable_runtime_harness import run_flow

CaptureReader = Callable[[], Awaitable[list[dict[str, Any]]]]
MockQueue = Callable[[list[Any]], Any]


def context_config(
    *,
    profile: str | None = None,
    mode: str | None = None,
    retrieval_mode: str | None = None,
    memory: str | None = None,
    compaction: str | None = None,
    max_input_tokens: int = 4_096,
    active_window_tokens: int = 20,
    rag_tokens: int = 1_200,
    tool_result_tokens: int = 64,
    cache: str | None = "provider_hints",
) -> dict[str, Any]:
    """Собирает llm_context patch.

    Если задан ``profile``, mode/memory/retrieval/compaction не подставляются
    по умолчанию — иначе они перетирают named profile при deep-merge.
    """
    config: dict[str, Any] = {
        "budget": {
            "max_input_tokens": max_input_tokens,
            "output_reserve_tokens": 64,
            "reasoning_reserve_tokens": 0,
            "safety_buffer_tokens": 64,
            "active_window_tokens": active_window_tokens,
            "memory_tokens": 512,
            "rag_tokens": rag_tokens,
            "tool_result_tokens": tool_result_tokens,
        },
    }
    if profile is not None:
        config["profile"] = profile
    else:
        config["mode"] = mode if mode is not None else "smart"
        config["memory"] = memory if memory is not None else "session"
        config["retrieval"] = {
            "mode": retrieval_mode if retrieval_mode is not None else "hybrid",
            "top_k": 4,
            "rerank": False,
        }
        config["compaction"] = compaction if compaction is not None else "auto"
    if mode is not None and profile is not None:
        config["mode"] = mode
    if memory is not None:
        config["memory"] = memory
    if retrieval_mode is not None:
        config["retrieval"] = {"mode": retrieval_mode, "top_k": 4, "rerank": False}
    if compaction is not None:
        config["compaction"] = compaction
    if cache is not None:
        config["cache"] = cache
    return config


def rag_config(*, namespace: str, collection_id: str, top_k: int = 4) -> dict[str, Any]:
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


def agent_node(
    *,
    prompt: str,
    resources: dict[str, Any] | None = None,
    llm_context: dict[str, Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
    agent_skills: list[str] | None = None,
) -> dict[str, Any]:
    node: dict[str, Any] = {
        "type": "llm_node",
        "name": "Context Layer E2E Agent",
        "prompt": prompt,
        "llm": {"provider": "mock", "model": "mock-gpt-4", "temperature": 0.0},
        "tools": tools or [],
    }
    if resources is not None:
        node["resources"] = resources
    if llm_context is not None:
        node["llm_context"] = llm_context
        node["llm_context_resource_key"] = "ctx"
    if agent_skills is not None:
        node["agent_skills"] = agent_skills
    return node


def single_node_flow(
    *,
    flow_id: str,
    prompt: str,
    llm_context: dict[str, Any] | None = None,
    rag_namespace: str | None = None,
    collection_id: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    agent_skills: list[str] | None = None,
) -> FlowConfig:
    resources: dict[str, Any] = {}
    if llm_context is not None:
        resources["ctx"] = {"type": "llm_context", "config": llm_context}
    if rag_namespace is not None and collection_id is not None:
        resources["kb"] = {
            "type": "rag",
            "config": rag_config(namespace=rag_namespace, collection_id=collection_id),
        }
    return FlowConfig(
        flow_id=flow_id,
        name="LLM context E2E",
        entry="agent",
        nodes={
            "agent": agent_node(
                prompt=prompt,
                llm_context=llm_context,
                tools=tools,
                agent_skills=agent_skills,
            )
        },
        edges=[Edge(from_node="agent", to_node=None)],
        resources=resources,
    )


async def index_rag_document(
    *,
    di: FlowsDi,
    namespace: str,
    collection_id: str,
    marker: str,
) -> None:
    rag = RAGResource(
        namespace,
        di.namespace_service,
        company_id="system",
        search_options={"channels": {"semantic": True, "lexical": True}, "rerank": False},
    )
    await rag.add_document(
        f"doc-{marker}",
        f"{marker} context-layer-rag-answer searchable knowledge about billing limits.",
        metadata={"collection_id": collection_id, "marker": marker},
        name=f"{marker}.md",
    )


def stale_messages(*, context_id: str, task_id: str, marker: str = "OLD_CONTEXT") -> list[Any]:
    return [
        build_user_message(
            f"{marker} " + ("obsolete " * 80),
            "agent",
            context_id=context_id,
            task_id=task_id,
        ),
        build_assistant_message(
            f"{marker}_ASSISTANT " + ("obsolete " * 80),
            "agent",
            context_id=context_id,
            task_id=task_id,
        ),
    ]


async def run_context_flow(
    *,
    di: FlowsDi,
    flow_id: str,
    query: str,
    response: str,
    capture: CaptureReader,
    mock_llm_with_queue: MockQueue,
    auth_headers_system: dict[str, str],
    context_id: str,
    initial_messages: list[Any] | None = None,
    branch_id: str = "default",
    queued_responses: list[Any] | None = None,
) -> tuple[dict[str, Any], ExecutionState]:
    task_id = f"task-{context_id}"
    before_count = len(await capture())
    mock_llm_with_queue(queued_responses or [{"type": "text", "content": response}])
    with service_client_asgi_auth_context(auth_headers_system):
        ctx = get_context()
        if ctx is None or ctx.user is None or ctx.active_company is None:
            raise ValueError("run_context_flow requires authenticated user and active_company")
        # RAG Check uses ExecutionState.user_id as OpenFGA subject. Actor must already
        # have company tuples from auth_token_system — do not invent a synthetic user.
        state = ExecutionState(
            task_id=task_id,
            context_id=context_id,
            user_id=ctx.user.user_id,
            session_id=f"{flow_id}:{context_id}",
            branch_id=branch_id,
            content=query,
            messages=initial_messages or [],
        )
        flow = await di.flow_factory.get_flow(flow_id, branch_id=branch_id, tool_registry=di.tool_registry)
        result = await run_flow(di=di, flow=flow, state=state)
    assert result["response"] == response
    calls = await capture()
    new_calls = calls[before_count:]
    main_calls = [
        call
        for call in new_calls
        if query in call_text(call) and "Compress this closed conversation segment" not in call_text(call)
    ]
    assert main_calls
    return main_calls[-1], state


async def _documents_matching(
    namespace_id: str, filters: dict[str, str], *, limit: int
) -> list[VectorDocument]:
    rows = await VectorDocument.objects.filter(namespace_id=namespace_id).limit(1000).all()
    matched = [
        row
        for row in rows
        if all(row.metadata.get(key) == value for key, value in filters.items())
    ]
    return matched[:limit]


def call_text(call: dict[str, Any]) -> str:
    return "\n".join(str(message.get("text") or "") for message in call["messages"])


async def wait_for_compacted_memory(
    *, di: FlowsDi, flow_id: str, session_id: str
) -> None:
    namespace_id = llm_context_memory_namespace_id("system")
    filters = {
        "flow_id": flow_id,
        "session_id": session_id,
        "source": "llm_context_compaction",
    }
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        documents = await _documents_matching(namespace_id, filters, limit=10)
        if documents:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"Timed out waiting for compacted LLM memory: {filters}")


async def cleanup_flow_context(
    *,
    di: FlowsDi,
    flow_id: str,
    namespaces: list[str],
    auth_headers_system: dict[str, str],
    resource_ids: list[str] | None = None,
) -> None:
    with service_client_asgi_auth_context(auth_headers_system):
        await FlowConfig.delete_by_flow_id(flow_id)
        for resource_id in resource_ids or []:
            await ResourceDefinition.delete_by_id(ResourceDefinition.row_id(resource_id))
        memory_namespace = llm_context_memory_namespace_id("system")
        compacted_documents = await _documents_matching(
            memory_namespace, {"flow_id": flow_id, "source": "llm_context_compaction"}, limit=100
        )
        for document in compacted_documents:
            _ = await VectorDocument.delete_document_chunks(memory_namespace, document.document_id)
        for namespace in namespaces:
            _ = await VectorDocument.delete_namespace_chunks(namespace)
            _ = await di.namespace_service.delete(namespace)


async def store_context_resource(
    *, di: FlowsDi, resource_id: str, config: dict[str, Any]
) -> None:
    await ResourceDefinition.set(
        ResourceDefinition(
            resource_id=resource_id,
            type=ResourceType.LLM_CONTEXT,
            name="Shared context profile",
            config=config,
        )
    )
