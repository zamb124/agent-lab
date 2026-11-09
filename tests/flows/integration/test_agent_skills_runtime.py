"""Жёсткий runtime-контур Agent Skills: MockLLM + реальный ToolRegistry/builtins."""

from __future__ import annotations

from typing import cast

import pytest
from fastapi import FastAPI

from apps.flows.di import FlowsDi
from apps.flows.src.durable_execution import RunStartedPayload, WorkflowEventType
from apps.flows.src.models.agent_skill import AgentSkill, AgentSkillUpdatePayload
from apps.flows.src.models.enums import NodeType
from apps.flows.src.models.node_config import NodeConfig, NodeLLMConfig
from apps.flows.src.models.tool_reference import ToolReference
from apps.flows.src.runtime.agent_skill_runtime import (
    AgentSkillRuntimeHost,
    agent_skill_runtime_host_scope,
)
from apps.flows.src.runtime.execution_context import execution_context_for
from apps.flows.src.runtime.nodes import LlmNode
from apps.flows.src.runtime.runners.llm_runner import LlmNodeRunner
from apps.flows.src.streaming import InMemoryEmitter
from apps.flows.tools.flows.agent_skill_tools import load_agent_skill, read_agent_skill_reference
from core.di import require_di
from core.files.create_spec import FileCreateSpec
from core.files.file_ref import FileRef
from core.types import JsonObject
from tests.flows.agent_skills_harness import (
    assert_platform_assistant_attach,
    company_scope,
    ensure_platform_assistant_flow,
    make_skill_state,
    mock_load_skill_then_calculator,
)
from tests.flows.durable_runtime_harness import ensure_workflow_started

_EMPTY_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

_CALC_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {
        "expression": {"type": "string"},
    },
    "required": ["expression"],
    "additionalProperties": False,
}


def _flows_di(app: FastAPI) -> FlowsDi:
    return require_di(app, FlowsDi)


async def _persist_runner_state(app: FastAPI, state) -> FlowsDi:
    di = _flows_di(app)
    _ = await di.workflow_runtime.save_state(
        state.session_id,
        state,
        event_type=WorkflowEventType.run_started,
        payload=RunStartedPayload(),
        snapshot=True,
    )
    return di


async def _consume_runner(runner: LlmNodeRunner, state, content: str = "run") -> None:
    async for _ in runner.run({"content": content}, state, InMemoryEmitter(state)):
        pass


def _tool_names(runner: LlmNodeRunner) -> set[str]:
    return {tool.name for tool in runner.tools}


@pytest.mark.asyncio
async def test_llm_runner_load_skill_unlocks_and_runs_calculator(
    app: FastAPI,
    mock_llm_with_queue,
    unique_id: str, di,
) -> None:
    company_id = f"company_rt_{unique_id}"
    skill_id = f"calc-skill-{unique_id}"
    flow_id = f"skill_flow_{unique_id}"
    async with company_scope(company_id, unique_id, di=di):
        di = _flows_di(app)
        await AgentSkill.create(
            AgentSkill(
                agent_skill_id=skill_id,
                name=skill_id,
                description="Unlock calculator for math tasks",
                body_markdown="## Math\n\nUse calculator after load.",
                tool_refs=[
                    ToolReference(
                        tool_id="calculator",
                        description="calc",
                        parameters_schema=dict(_CALC_SCHEMA),
                    )
                ],
            )
        )
        mock_llm_with_queue(
            mock_load_skill_then_calculator(
                agent_skill_id=skill_id,
                expression="2+2",
                final_text="four",
            )
        )
        node_config = NodeConfig(
            node_id=f"node_{unique_id}",
            type=NodeType.LLM_NODE,
            name="Skill runner",
            description="",
            prompt="Load the skill then calculate.",
            tools=[],
            agent_skills=[skill_id],
            llm=NodeLLMConfig(provider="mock", model="mock-gpt-4"),
        )
        state = make_skill_state(flow_id=flow_id, unique_id=unique_id, content="compute")
        di = await _persist_runner_state(app, state)
        await ensure_workflow_started(
            di=di,
            state=state,
            flow_id=flow_id,
            branch_id=state.branch_id,
        )
        node = LlmNode(
            node_id=node_config.node_id,
            config=cast(JsonObject, node_config.model_dump(mode="json")),
            node_config=node_config,
            execution=execution_context_for(di.node_constructor.workflow_runtime), redis_client=di.node_constructor.redis_client, flow_factory=di.flow_factory, llm_context_memory_store=di.node_constructor.llm_context_memory_store, namespace_service=di.node_constructor.namespace_service, authz_service=di.node_constructor.authz_service, tool_registry=di.tool_registry, workflow_runtime=di.node_constructor.workflow_runtime, text_transform_service=di.node_constructor.text_transform_service, emitter_factory=di.node_constructor.emitter_factory, billing_service=di.node_constructor.billing_service,
        )
        runner = await node.get_runner(state)
        assert "load_agent_skill" in _tool_names(runner)
        assert "calculator" not in _tool_names(runner)

        await _consume_runner(runner, state, content="compute")

        assert "calculator" in _tool_names(runner)
        host = runner.agent_skill_host
        assert host is not None
        assert any(
            block.stable_key == f"agent_skills.body.{skill_id}"
            for block in host.context_blocks
        )
        tool_messages = [
            msg for msg in state.messages if getattr(msg, "role", None) is not None
        ]
        joined = " ".join(
            str(part.root.text)
            for msg in tool_messages
            for part in getattr(msg, "parts", [])
            if hasattr(part, "root") and hasattr(part.root, "text")
        )
        assert "4" in joined or "four" in joined.lower() or state.response


@pytest.mark.asyncio
async def test_llm_runner_rebuilds_tools_schema_after_skill_load(
    app: FastAPI,
    mock_llm_with_queue,
    mock_llm_capture,
    unique_id: str, di,
) -> None:
    """Doctrine: call[0] без unlocked tool, call[1] с ним после load_agent_skill."""
    company_id = f"company_schema_{unique_id}"
    skill_id = f"schema-skill-{unique_id}"
    flow_id = f"skill_schema_{unique_id}"

    def _captured_tool_names(call: JsonObject) -> set[str]:
        names: set[str] = set()
        raw_tools = call.get("tools")
        if not isinstance(raw_tools, list):
            return names
        for tool in raw_tools:
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

    async with company_scope(company_id, unique_id, di=di):
        di = _flows_di(app)
        await AgentSkill.create(
            AgentSkill(
                agent_skill_id=skill_id,
                name=skill_id,
                description="Unlock calculator for schema rebuild doctrine",
                body_markdown="## Math\n\nUse calculator after load.",
                tool_refs=[
                    ToolReference(
                        tool_id="calculator",
                        description="calc",
                        parameters_schema=dict(_CALC_SCHEMA),
                    )
                ],
            )
        )
        mock_llm_with_queue(
            mock_load_skill_then_calculator(
                agent_skill_id=skill_id,
                expression="2+2",
                final_text="four",
            )
        )
        node_config = NodeConfig(
            node_id=f"node_{unique_id}",
            type=NodeType.LLM_NODE,
            name="Skill schema rebuild",
            description="",
            prompt="Load the skill then calculate.",
            tools=[],
            agent_skills=[skill_id],
            llm=NodeLLMConfig(provider="mock", model="mock-gpt-4"),
        )
        state = make_skill_state(flow_id=flow_id, unique_id=unique_id, content="compute")
        di = await _persist_runner_state(app, state)
        await ensure_workflow_started(
            di=di,
            state=state,
            flow_id=flow_id,
            branch_id=state.branch_id,
        )
        node = LlmNode(
            node_id=node_config.node_id,
            config=cast(JsonObject, node_config.model_dump(mode="json")),
            node_config=node_config,
            execution=execution_context_for(di.node_constructor.workflow_runtime), redis_client=di.node_constructor.redis_client, flow_factory=di.flow_factory, llm_context_memory_store=di.node_constructor.llm_context_memory_store, namespace_service=di.node_constructor.namespace_service, authz_service=di.node_constructor.authz_service, tool_registry=di.tool_registry, workflow_runtime=di.node_constructor.workflow_runtime, text_transform_service=di.node_constructor.text_transform_service, emitter_factory=di.node_constructor.emitter_factory, billing_service=di.node_constructor.billing_service,
        )
        runner = await node.get_runner(state)
        await _consume_runner(runner, state, content="compute")

        calls = await mock_llm_capture()
        assert len(calls) >= 2
        first_tools = _captured_tool_names(calls[0])
        second_tools = _captured_tool_names(calls[1])
        assert "load_agent_skill" in first_tools
        assert "calculator" not in first_tools
        assert "calculator" in second_tools


@pytest.mark.asyncio
async def test_no_agent_skills_does_not_inject_meta_tools(
    app: FastAPI,
    unique_id: str,
) -> None:
    flow_id = f"noskill_{unique_id}"
    di = _flows_di(app)
    node_config = NodeConfig(
        node_id=f"node_{unique_id}",
        type=NodeType.LLM_NODE,
        name="No skills",
        description="",
        prompt="Hi",
        tools=[],
        agent_skills=[],
        llm=NodeLLMConfig(provider="mock", model="mock-gpt-4"),
    )
    state = make_skill_state(flow_id=flow_id, unique_id=unique_id)
    di = await _persist_runner_state(app, state)
    node = LlmNode(
        node_id=node_config.node_id,
        config=cast(JsonObject, node_config.model_dump(mode="json")),
        node_config=node_config,
        execution=execution_context_for(di.node_constructor.workflow_runtime), redis_client=di.node_constructor.redis_client, flow_factory=di.flow_factory, llm_context_memory_store=di.node_constructor.llm_context_memory_store, namespace_service=di.node_constructor.namespace_service, authz_service=di.node_constructor.authz_service, tool_registry=di.tool_registry, workflow_runtime=di.node_constructor.workflow_runtime, text_transform_service=di.node_constructor.text_transform_service, emitter_factory=di.node_constructor.emitter_factory, billing_service=di.node_constructor.billing_service,
    )
    tools = await node.get_tools(state)
    names = {tool.name for tool in tools}
    assert "load_agent_skill" not in names
    assert "read_agent_skill_reference" not in names


@pytest.mark.asyncio
async def test_load_agent_skill_without_host_raises(unique_id: str, di) -> None:
    async with company_scope(f"company_no_host_{unique_id}", unique_id, di=di):
        state = make_skill_state(flow_id=f"flow_{unique_id}", unique_id=unique_id)
        with pytest.raises(RuntimeError, match="AgentSkillRuntimeHost is not active"):
            await load_agent_skill.run({"agent_skill_id": "document-workspace"}, state)


@pytest.mark.asyncio
async def test_depends_on_merge_unlocks_child_tool(
    app: FastAPI,
    mock_llm_with_queue,
    unique_id: str, di,
) -> None:
    company_id = f"company_dep_{unique_id}"
    parent_id = f"parent-{unique_id}"
    child_id = f"child-{unique_id}"
    flow_id = f"dep_flow_{unique_id}"
    async with company_scope(company_id, unique_id, di=di):
        di = _flows_di(app)
        await AgentSkill.create(
            AgentSkill(
                agent_skill_id=child_id,
                name=child_id,
                description="Child skill with calculator",
                body_markdown="Child body",
                tool_refs=[
                    ToolReference(
                        tool_id="calculator",
                        description="calc",
                        parameters_schema=dict(_CALC_SCHEMA),
                    )
                ],
            )
        )
        await AgentSkill.create(
            AgentSkill(
                agent_skill_id=parent_id,
                name=parent_id,
                description="Parent skill",
                body_markdown="Parent body",
                depends_on=[child_id],
            )
        )
        mock_llm_with_queue(
            [
                {
                    "type": "tool_calls",
                    "calls": [
                        {"tool": "load_agent_skill", "args": {"agent_skill_id": parent_id}}
                    ],
                },
                {
                    "type": "tool_calls",
                    "calls": [
                        {"tool": "load_agent_skill", "args": {"agent_skill_id": child_id}}
                    ],
                },
                {"type": "text", "content": "loaded"},
            ]
        )
        node_config = NodeConfig(
            node_id=f"node_{unique_id}",
            type=NodeType.LLM_NODE,
            name="Depends",
            description="",
            prompt="Load parent then child.",
            tools=[],
            agent_skills=[parent_id],
            llm=NodeLLMConfig(provider="mock", model="mock-gpt-4"),
        )
        state = make_skill_state(flow_id=flow_id, unique_id=unique_id)
        di = await _persist_runner_state(app, state)
        await ensure_workflow_started(
            di=di,
            state=state,
            flow_id=flow_id,
            branch_id=state.branch_id,
        )
        node = LlmNode(
            node_id=node_config.node_id,
            config=cast(JsonObject, node_config.model_dump(mode="json")),
            node_config=node_config,
            execution=execution_context_for(di.node_constructor.workflow_runtime), redis_client=di.node_constructor.redis_client, flow_factory=di.flow_factory, llm_context_memory_store=di.node_constructor.llm_context_memory_store, namespace_service=di.node_constructor.namespace_service, authz_service=di.node_constructor.authz_service, tool_registry=di.tool_registry, workflow_runtime=di.node_constructor.workflow_runtime, text_transform_service=di.node_constructor.text_transform_service, emitter_factory=di.node_constructor.emitter_factory, billing_service=di.node_constructor.billing_service,
        )
        runner = await node.get_runner(state)
        await _consume_runner(runner, state)
        assert "calculator" in _tool_names(runner)
        host = runner.agent_skill_host
        assert host is not None
        assert host.loaded_depths[parent_id] == 0
        assert host.loaded_depths[child_id] == 1


@pytest.mark.asyncio
async def test_live_catalog_update_seen_on_next_load(
    di,
    unique_id: str,
) -> None:
    company_id = f"company_live_{unique_id}"
    skill_id = f"live-skill-{unique_id}"
    async with company_scope(company_id, unique_id, di=di):
        await AgentSkill.create(
            AgentSkill(
                agent_skill_id=skill_id,
                name=skill_id,
                description="Old description for live skill",
                body_markdown="## Old body",
                tool_refs=[
                    ToolReference(
                        tool_id="calculator",
                        description="calc",
                        parameters_schema=dict(_CALC_SCHEMA),
                    )
                ],
            )
        )
        host = AgentSkillRuntimeHost(
            attached_ids=frozenset({skill_id}),
            index_entries=tuple(
                await AgentSkill.resolve_index([skill_id])
            ),
        )
        state = make_skill_state(flow_id=f"live_{unique_id}", unique_id=unique_id)
        with agent_skill_runtime_host_scope(host):
            first = await load_agent_skill.run({"agent_skill_id": skill_id}, state)
            assert first["tools_unlocked"] == ["calculator"]
            assert any("Old body" in b.content for b in host.context_blocks)

        await AgentSkill.update(
            AgentSkillUpdatePayload(
                agent_skill_id=skill_id,
                name=skill_id,
                description="New description for live skill",
                body_markdown="## New body after update",
                tool_refs=[
                    ToolReference(
                        tool_id="finish",
                        description="finish",
                        parameters_schema=dict(_EMPTY_SCHEMA),
                    )
                ],
                depends_on=[],
                references=[],
                assets=[],
            ),
        )
        host2 = AgentSkillRuntimeHost(
            attached_ids=frozenset({skill_id}),
            index_entries=tuple(
                await AgentSkill.resolve_index([skill_id])
            ),
        )
        with agent_skill_runtime_host_scope(host2):
            second = await load_agent_skill.run({"agent_skill_id": skill_id}, state)
            assert second["tools_unlocked"] == ["finish"]
            assert any("New body after update" in b.content for b in host2.context_blocks)


@pytest.mark.asyncio
async def test_company_isolation_skills(di, unique_id: str) -> None:
    skill_id = f"iso-skill-{unique_id}"
    company_a = f"company_a_{unique_id}"
    company_b = f"company_b_{unique_id}"
    async with company_scope(company_a, unique_id, di=di):
        await AgentSkill.create(
            AgentSkill(
                agent_skill_id=skill_id,
                name=skill_id,
                description="Skill only in company A",
                body_markdown="Body A",
            )
        )
        loaded = await AgentSkill.require_by_agent_skill_id(skill_id)
        assert loaded.agent_skill_id == skill_id
    async with company_scope(company_b, f"b{unique_id}", di=di):
        with pytest.raises(LookupError, match="not found"):
            await AgentSkill.require_by_agent_skill_id(skill_id)


@pytest.mark.asyncio
async def test_read_reference_requires_loaded_skill(di, unique_id: str) -> None:
    company_id = f"company_ref_{unique_id}"
    skill_id = f"ref-skill-{unique_id}"
    async with company_scope(company_id, unique_id, di=di):
        record = await di.files_service.create(
            FileCreateSpec.model_validate(
                {
                    "source_kind": "platform_auxiliary",
                    "source_ref": {},
                    "retention": {"kind": "platform_default"},
                    "post_create": {"is_public": True},
                }
            ),
            b"# ref",
            original_name=f"ref-{unique_id}.md",
            content_type="text/markdown",
        )
        await AgentSkill.create(
            AgentSkill(
                agent_skill_id=skill_id,
                name=skill_id,
                description="Skill with reference",
                body_markdown="Body",
                references=[
                    FileRef(
                        file_id=record.file_id,
                        original_name=record.original_name,
                        url=record.url,
                        content_type=record.content_type,
                        file_size=record.file_size,
                    )
                ],
            )
        )
        host = AgentSkillRuntimeHost(
            attached_ids=frozenset({skill_id}),
            index_entries=tuple(
                await AgentSkill.resolve_index([skill_id])
            ),
        )
        state = make_skill_state(flow_id=f"ref_{unique_id}", unique_id=unique_id)
        with agent_skill_runtime_host_scope(host):
            with pytest.raises(ValueError, match="not loaded"):
                await read_agent_skill_reference.run(
                    {"agent_skill_id": skill_id, "file_id": record.file_id},
                    state,
                )
            await load_agent_skill.run({"agent_skill_id": skill_id}, state)
            by_id = await read_agent_skill_reference.run(
                {"agent_skill_id": skill_id, "file_id": record.file_id},
                state,
            )
            assert by_id["content"] == "# ref"
            by_name = await read_agent_skill_reference.run(
                {
                    "agent_skill_id": skill_id,
                    "original_name": record.original_name,
                },
                state,
            )
            assert by_name["content"] == "# ref"


@pytest.mark.asyncio
async def test_platform_assistant_flow_factory_loads(di, unique_id: str) -> None:
    _ = unique_id
    flow_config = await ensure_platform_assistant_flow(di)
    assert_platform_assistant_attach(flow_config)
    flow = await di.flow_factory.get_flow("platform_assistant", tool_registry=di.tool_registry)
    assert flow.flow_id == "platform_assistant"
