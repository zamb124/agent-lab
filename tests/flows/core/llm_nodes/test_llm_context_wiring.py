"""L3 wiring: llm_node registry gate and company/runtime policy."""
from __future__ import annotations

from typing import cast

import pytest
from fastapi import FastAPI

from apps.flows.src.container_contracts import FlowRuntimeContainer, as_flow_runtime_container
from apps.flows.src.durable_execution import RunStartedPayload, WorkflowEventType
from apps.flows.src.models.enums import NodeType
from apps.flows.src.models.node_config import NodeConfig, NodeLLMConfig
from apps.flows.src.runtime.nodes import LlmNode
from core.ai.company_settings import METADATA_KEY, CompanyAIProviders, LLMContextPatch
from core.context import Company, Context, User, clear_context, set_context
from core.llm_context import LLMContextProfile
from core.types import JsonObject
from tests.flows.agent_skills_harness import make_skill_state
from tests.flows.durable_runtime_harness import ensure_workflow_started


def _runtime_container(app: FastAPI) -> FlowRuntimeContainer:
    return as_flow_runtime_container(app.state.container)


async def _persist_state(app: FastAPI, state) -> FlowRuntimeContainer:
    container = _runtime_container(app)
    _ = await container.workflow_runtime.save_state(
        state.session_id,
        state,
        event_type=WorkflowEventType.run_started,
        payload=RunStartedPayload(),
        snapshot=True,
    )
    return container


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("llm_context", "expect_registry"),
    [
        ({"profile": "off"}, False),
        ({"profile": "compact"}, False),
        ({"profile": "standard"}, True),
        ({"mode": "smart", "retrieval": {"mode": "off", "rerank": False}}, False),
    ],
)
async def test_llm_node_source_registry_respects_mode_and_retrieval(
    app: FastAPI,
    unique_id: str,
    llm_context: dict[str, object],
    expect_registry: bool,
) -> None:
    """Registry (memory/RAG sources) создаётся только при mode!=off и retrieval!=off."""
    flow_id = f"ctx_registry_{unique_id}"
    node_config = NodeConfig(
        node_id=f"node_{unique_id}",
        type=NodeType.LLM_NODE,
        name="Registry gate",
        description="",
        prompt="Hi",
        tools=[],
        llm=NodeLLMConfig(provider="mock", model="mock-gpt-4"),
        llm_context=LLMContextPatch.model_validate(llm_context),
    )
    state = make_skill_state(flow_id=flow_id, unique_id=unique_id)
    container = await _persist_state(app, state)
    await ensure_workflow_started(
        container=container,
        state=state,
        flow_id=flow_id,
        branch_id=state.branch_id,
    )
    node = LlmNode(
        node_id=node_config.node_id,
        config=cast(JsonObject, node_config.model_dump(mode="json")),
        node_config=node_config,
        container=container,
    )
    runner = await node.get_runner(state)
    assert isinstance(runner.llm_context_policy, LLMContextProfile)
    if expect_registry:
        assert runner.llm_context_source_registry is not None
        assert runner.llm_context_source_registry.has_sources is True
    else:
        assert runner.llm_context_source_registry is None


@pytest.mark.asyncio
async def test_llm_node_applies_company_llm_context_patch(
    app: FastAPI,
    unique_id: str,
) -> None:
    """Company metadata.ai_providers.llm_context влияет на resolved policy ноды."""
    flow_id = f"ctx_company_{unique_id}"
    node_config = NodeConfig(
        node_id=f"node_{unique_id}",
        type=NodeType.LLM_NODE,
        name="Company patch",
        description="",
        prompt="Hi",
        tools=[],
        llm=NodeLLMConfig(provider="mock", model="mock-gpt-4"),
    )
    state = make_skill_state(flow_id=flow_id, unique_id=unique_id)
    container = await _persist_state(app, state)
    await ensure_workflow_started(
        container=container,
        state=state,
        flow_id=flow_id,
        branch_id=state.branch_id,
    )
    clear_context()
    try:
        providers = CompanyAIProviders(llm_context=LLMContextPatch(profile="standard"))
        company = Company(
            company_id="system",
            name="System",
            metadata={METADATA_KEY: providers.to_metadata_dict()},
        )
        user = User(user_id="test_user", name="User", active_company_id="system")
        set_context(Context(user=user, active_company=company, channel="test"))
        node = LlmNode(
            node_id=node_config.node_id,
            config=cast(JsonObject, node_config.model_dump(mode="json")),
            node_config=node_config,
            container=container,
        )
        runner = await node.get_runner(state)
        assert runner.llm_context_policy is not None
        assert runner.llm_context_policy.mode == "smart"
        assert runner.llm_context_policy.retrieval.mode == "hybrid"
        assert runner.llm_context_source_registry is not None
    finally:
        clear_context()
