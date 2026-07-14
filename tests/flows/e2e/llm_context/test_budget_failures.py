"""Context budget failures must surface from a real llm_node run."""
from __future__ import annotations

import pytest

from apps.flows.src.container import FlowContainer
from apps.flows.src.services.agent_skill_service import AgentSkillCreateInput
from core.llm_context import LLMContextBudgetError
from tests.fixtures.auth import service_client_asgi_auth_context
from tests.flows.e2e.llm_context.harness import (
    cleanup_flow_context,
    context_config,
    run_context_flow,
    single_node_flow,
)

pytestmark = pytest.mark.asyncio


async def test_context_budget_rejects_oversized_system_prompt(
    app,
    container: FlowContainer,
    unique_id: str,
    mock_llm_capture,
    mock_llm_with_queue,
    auth_headers_system: dict[str, str],
) -> None:
    """Обязательный system prompt не может быть молча усечён."""
    _ = app
    flow_id = f"ctx-budget-{unique_id}"
    await container.flow_repository.set(
        single_node_flow(
            flow_id=flow_id,
            prompt="MANDATORY_SYSTEM " + ("must-fit " * 500),
            llm_context=context_config(
                max_input_tokens=160,
                active_window_tokens=20,
                retrieval_mode="off",
                memory="off",
            ),
        )
    )
    try:
        with pytest.raises(LLMContextBudgetError, match="System LLM context prefix"):
            await run_context_flow(
                container=container,
                flow_id=flow_id,
                query=f"QUERY_BUDGET_{unique_id}",
                response="unreachable",
                capture=mock_llm_capture,
                mock_llm_with_queue=mock_llm_with_queue,
                auth_headers_system=auth_headers_system,
                context_id=f"context-budget-{unique_id}",
            )
    finally:
        await cleanup_flow_context(
            container=container,
            flow_id=flow_id,
            namespaces=[],
            auth_headers_system=auth_headers_system,
        )


async def test_context_budget_rejects_required_skill_index(
    app,
    container: FlowContainer,
    unique_id: str,
    mock_llm_capture,
    mock_llm_with_queue,
    auth_headers_system: dict[str, str],
) -> None:
    """Required Agent Skill index block must fail closed on tiny budget."""
    _ = app
    flow_id = f"ctx-budget-skill-{unique_id}"
    agent_skill_id = f"ctx-budget-skill-{unique_id}"
    tight_context = {
        "profile": "standard",
        "budget": {
            "max_input_tokens": 180,
            "output_reserve_tokens": 16,
            "reasoning_reserve_tokens": 0,
            "safety_buffer_tokens": 16,
            "active_window_tokens": 24,
            "memory_tokens": 8,
            "rag_tokens": 8,
            "tool_result_tokens": 8,
        },
        "memory": "off",
        "retrieval": {"mode": "off", "rerank": False},
        "compaction": "off",
        "cache": "off",
    }
    with service_client_asgi_auth_context(auth_headers_system):
        await container.agent_skill_service.create(
            AgentSkillCreateInput(
                agent_skill_id=agent_skill_id,
                name="budget-skill",
                description=("required-index-" + ("token " * 80))[:1000],
                body_markdown="## Body",
            )
        )
        await container.flow_repository.set(
            single_node_flow(
                flow_id=flow_id,
                prompt="SYS " + ("keep " * 60),
                llm_context=tight_context,
                agent_skills=[agent_skill_id],
            )
        )
    try:
        with pytest.raises(LLMContextBudgetError):
            await run_context_flow(
                container=container,
                flow_id=flow_id,
                query=f"QUERY_BUDGET_SKILL_{unique_id}",
                response="unreachable",
                capture=mock_llm_capture,
                mock_llm_with_queue=mock_llm_with_queue,
                auth_headers_system=auth_headers_system,
                context_id=f"context-budget-skill-{unique_id}",
            )
    finally:
        with service_client_asgi_auth_context(auth_headers_system):
            await container.agent_skill_service.delete(agent_skill_id)
        await cleanup_flow_context(
            container=container,
            flow_id=flow_id,
            namespaces=[],
            auth_headers_system=auth_headers_system,
        )
