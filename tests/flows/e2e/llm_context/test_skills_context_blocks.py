"""Agent Skill index blocks through the generic context layer."""
from __future__ import annotations

from typing import Any

import pytest

from apps.flows.src.container import FlowContainer
from apps.flows.src.services.agent_skill_service import AgentSkillCreateInput
from tests.fixtures.auth import service_client_asgi_auth_context
from tests.flows.e2e.llm_context.harness import (
    call_text,
    cleanup_flow_context,
    context_config,
    run_context_flow,
    single_node_flow,
)

pytestmark = pytest.mark.asyncio


def _captured_tool_names(call: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for tool in call.get("tools") or []:
        if not isinstance(tool, dict):
            continue
        direct = tool.get("name")
        if isinstance(direct, str) and direct.strip():
            names.add(direct)
            continue
        function = tool.get("function")
        if isinstance(function, dict):
            function_name = function.get("name")
            if isinstance(function_name, str) and function_name.strip():
                names.add(function_name)
    return names


@pytest.mark.parametrize(("profile", "expect_index"), [("off", False), ("standard", True)])
async def test_skills_index_respects_context_profile(
    app,
    container: FlowContainer,
    unique_id: str,
    mock_llm_capture,
    mock_llm_with_queue,
    auth_headers_system: dict[str, str],
    profile: str,
    expect_index: bool,
) -> None:
    """Skill remains loadable, but its index is injected only in enabled context mode."""
    _ = app
    flow_id = f"ctx-skills-{profile}-{unique_id}"
    agent_skill_id = f"ctx-skill-{profile}-{unique_id}"
    with service_client_asgi_auth_context(auth_headers_system):
        await container.agent_skill_service.create(
            AgentSkillCreateInput(
                agent_skill_id=agent_skill_id,
                name="context-skill",
                description=f"skill-description-{profile}-{unique_id}",
                body_markdown="## Context skill body",
            )
        )
        await container.flow_repository.set(
            single_node_flow(
                flow_id=flow_id,
                prompt="Use the attached skill when appropriate.",
                llm_context=context_config(profile=profile),
                agent_skills=[agent_skill_id],
            )
        )
    try:
        call, _ = await run_context_flow(
            container=container,
            flow_id=flow_id,
            query=f"QUERY_SKILL_{profile}_{unique_id}",
            response="skill response",
            capture=mock_llm_capture,
            mock_llm_with_queue=mock_llm_with_queue,
            auth_headers_system=auth_headers_system,
            context_id=f"context-skills-{profile}-{unique_id}",
        )
        prompt = call_text(call)
        tool_names = _captured_tool_names(call)
        assert "load_agent_skill" in tool_names
        assert ("Available Agent Skills" in prompt) is expect_index
        assert (f"skill-description-{profile}-{unique_id}" in prompt) is expect_index
    finally:
        with service_client_asgi_auth_context(auth_headers_system):
            await container.agent_skill_service.delete(agent_skill_id)
        await cleanup_flow_context(
            container=container,
            flow_id=flow_id,
            namespaces=[],
            auth_headers_system=auth_headers_system,
        )
