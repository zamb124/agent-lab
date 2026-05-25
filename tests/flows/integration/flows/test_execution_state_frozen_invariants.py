"""
Интеграционные тесты: системные поля ExecutionState нельзя перезаписать
из CodeNode, structured output LLM и параллельных tool calls.

Мок только MockLLM (очередь). Без patch/monkeypatch на guard и раннер.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import cast

import pytest
from fastapi import FastAPI

from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.durable_execution import RunStartedPayload, WorkflowEventType
from apps.flows.src.models.enums import NodeType
from apps.flows.src.models.node_config import NodeConfig, NodeLLMConfig
from apps.flows.src.runtime.flow import Flow
from apps.flows.src.runtime.nodes import CodeNode, LlmNode
from apps.flows.src.runtime.runners.llm_runner import LlmNodeRunner
from apps.flows.src.streaming import InMemoryEmitter
from apps.flows.src.tools.code_tool import CodeTool
from core.errors import FrozenStateFieldError, ToolExecutionError
from core.state import ExecutionState
from core.state.mutation_policy import FROZEN_STATE_FIELDS
from core.types import JsonObject

MockLLMQueue = Callable[[list[JsonObject]], None]

USER_FORGE_GUARD_FIELDS: tuple[str, ...] = (
    "task_id",
    "context_id",
    "user_id",
    "session_id",
    "user_groups",
    "flow_deadline_monotonic",
    "flow_timeout_effective_seconds",
    "branch_id",
    "flow_config_version",
)


def _runtime_container(app: FastAPI) -> FlowRuntimeContainer:
    return cast(FlowRuntimeContainer, cast(object, app.state.container))


def frozen_snapshot(state: ExecutionState) -> dict[str, object]:
    return {name: deepcopy(state[name]) for name in FROZEN_STATE_FIELDS}


def assert_frozen_identical(before: dict[str, object], after: ExecutionState) -> None:
    for field_name, old_val in before.items():
        new_val = after[field_name]
        if new_val != old_val:
            raise AssertionError(
                f"frozen field {field_name!r} changed: {old_val!r} -> {new_val!r}"
            )


def assert_identity_frozen_unchanged(
    before: dict[str, object], after: ExecutionState, field_names: tuple[str, ...]
) -> None:
    """Поля идентичности/лимитов: не должны меняться из structured output и т.п."""
    for name in field_names:
        old_val = before[name]
        new_val = after[name]
        if new_val != old_val:
            raise AssertionError(
                f"field {name!r} changed: {old_val!r} -> {new_val!r}"
            )


def make_state(unique_id: str, **extra: object) -> ExecutionState:
    flow_id = f"flow_{unique_id}"
    ctx_id = f"ctx_{unique_id}"
    data: dict[str, object] = {
        "task_id": f"task_{unique_id}",
        "context_id": ctx_id,
        "user_id": f"user_{unique_id}",
        "session_id": f"{flow_id}:{ctx_id}",
        "messages": [],
        "variables": {},
    }
    data.update(extra)
    return ExecutionState.model_validate(data)


async def _run_single_node_flow(
    app: FastAPI,
    *,
    state: ExecutionState,
    node: CodeNode | LlmNode,
) -> None:
    flow = Flow(
        flow_id=state.session_flow_id,
        name=f"frozen invariant {state.session_flow_id}",
        entry=node.node_id,
        nodes={node.node_id: node},
        edges=[],
        container=_runtime_container(app),
    )
    _ = await flow.run(state)


async def _persist_runner_state(app: FastAPI, state: ExecutionState) -> FlowRuntimeContainer:
    container = _runtime_container(app)
    _ = await container.workflow_runtime.save_state(
        state.session_id,
        state,
        event_type=WorkflowEventType.run_started,
        payload=RunStartedPayload(),
        snapshot=True,
    )
    return container


async def _consume_runner(
    runner: LlmNodeRunner,
    state: ExecutionState,
    content: str = "run",
) -> None:
    async for _ in runner.run({"content": content}, state, InMemoryEmitter(state)):
        pass


class TestCodeNodeFrozenFields:
    @pytest.mark.asyncio
    async def test_dict_with_frozen_key_raises_and_state_unchanged(
        self,
        app: FastAPI,
        unique_id: str,
    ) -> None:
        snap = make_state(unique_id)

        code = """
async def run(args, state):
    return {"task_id": "forged", "safe_marker": 1}
"""
        node = CodeNode(node_id=f"code_{unique_id}", config={"type": "code", "code": code})
        snap.current_nodes = [node.node_id]
        frozen_before = frozen_snapshot(snap)

        with pytest.raises(FrozenStateFieldError):
            await _run_single_node_flow(app, state=snap, node=node)

        assert_frozen_identical(frozen_before, snap)
        assert "safe_marker" not in snap

    @pytest.mark.asyncio
    async def test_output_mapping_to_frozen_field_raises(
        self,
        app: FastAPI,
        unique_id: str,
    ) -> None:
        snap = make_state(unique_id)

        code = """
async def run(args, state):
    return {"x": "evil"}
"""
        node = CodeNode(
            node_id=f"code_{unique_id}",
            config={"type": "code", "code": code, "output_mapping": {"x": "session_id"}},
        )
        snap.current_nodes = [node.node_id]
        frozen_before = frozen_snapshot(snap)

        with pytest.raises(FrozenStateFieldError):
            await _run_single_node_flow(app, state=snap, node=node)

        assert_frozen_identical(frozen_before, snap)


class TestLlmNodeStructuredOutputFrozenFields:
    @pytest.mark.asyncio
    async def test_structured_output_extra_system_keys_raises(
        self,
        app: FastAPI,
        mock_llm_with_queue: MockLLMQueue,
        unique_id: str,
    ) -> None:
        mock_llm_with_queue(
            [
                {
                    "type": "structured_output",
                    "data": {
                        "answer": "ok",
                        "task_id": "forged",
                        "user_groups": ["intruder"],
                        "flow_deadline_monotonic": 1.5,
                    },
                }
            ]
        )

        node = LlmNode(
            node_id=f"llm_{unique_id}",
            config={
                "type": "llm_node",
                "prompt": "Extract",
                "structured_output": True,
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "answer": {"type": "string"},
                        "task_id": {"type": "string"},
                        "user_groups": {"type": "array", "items": {"type": "string"}},
                        "flow_deadline_monotonic": {"type": "number"},
                    },
                    "additionalProperties": True,
                },
            },
        )

        snap = make_state(unique_id, user_groups=["g_keep"])
        frozen_before = frozen_snapshot(snap)

        with pytest.raises(FrozenStateFieldError):
            await _run_single_node_flow(app, state=snap, node=node)

        assert_identity_frozen_unchanged(frozen_before, snap, USER_FORGE_GUARD_FIELDS)

    @pytest.mark.asyncio
    async def test_structured_output_single_forbidden_key_message_clear(
        self,
        app: FastAPI,
        mock_llm_with_queue: MockLLMQueue,
        unique_id: str,
    ) -> None:
        mock_llm_with_queue(
            [{"type": "structured_output", "data": {"task_id": "only_evil"}}]
        )

        node = LlmNode(
            node_id=f"llm_{unique_id}",
            config={
                "type": "llm_node",
                "prompt": "Out",
                "structured_output": True,
                "output_schema": {
                    "type": "object",
                    "properties": {"task_id": {"type": "string"}},
                    "additionalProperties": False,
                },
            },
        )

        snap = make_state(unique_id)
        frozen_before = frozen_snapshot(snap)

        with pytest.raises(FrozenStateFieldError) as exc:
            await _run_single_node_flow(app, state=snap, node=node)

        assert exc.value.payload["field"] == "task_id"
        assert snap.task_id == frozen_before["task_id"]


class TestLlmNodeRunnerParallelToolsFrozen:
    @pytest.mark.asyncio
    async def test_parallel_code_tools_merge_variables_frozen_unchanged(
        self,
        app: FastAPI,
        mock_llm_with_queue: MockLLMQueue,
        unique_id: str,
    ) -> None:
        mock_llm_with_queue(
            [
                {
                    "type": "tool_calls",
                    "calls": [
                        {"tool": f"t_a_{unique_id}", "args": {}},
                        {"tool": f"t_b_{unique_id}", "args": {}},
                    ],
                },
                {"type": "text", "content": "ok"},
            ]
        )

        code_a = f"""
async def run(args, state):
    state.variables["vk_{unique_id}_a"] = "a"
    return "a"
"""
        code_b = f"""
async def run(args, state):
    state.variables["vk_{unique_id}_b"] = "b"
    return "b"
"""

        t_a = CodeTool(tool_id=f"t_a_{unique_id}", code=code_a)
        t_b = CodeTool(tool_id=f"t_b_{unique_id}", code=code_b)

        node_config = NodeConfig(
            node_id=f"agent_{unique_id}",
            type=NodeType.LLM_NODE,
            name="Parallel frozen test",
            description="",
            prompt="Call tools.",
            llm=NodeLLMConfig(provider="mock"),
        )

        state = make_state(unique_id, user_groups=["ug1"])
        container = await _persist_runner_state(app, state)
        runner = LlmNodeRunner(
            node_config=node_config,
            tools=[t_a, t_b],
            llm=None,
            prompt="Call tools.",
            container=container,
        )

        frozen_before = frozen_snapshot(state)

        await _consume_runner(runner, state)

        assert_identity_frozen_unchanged(frozen_before, state, USER_FORGE_GUARD_FIELDS)
        assert state.variables[f"vk_{unique_id}_a"] == "a"
        assert state.variables[f"vk_{unique_id}_b"] == "b"

    @pytest.mark.asyncio
    async def test_parallel_code_tool_assigns_frozen_field_raises(
        self,
        app: FastAPI,
        mock_llm_with_queue: MockLLMQueue,
        unique_id: str,
    ) -> None:
        mock_llm_with_queue(
            [
                {
                    "type": "tool_calls",
                    "calls": [
                        {"tool": f"t_ok_{unique_id}", "args": {}},
                        {"tool": f"t_evil_{unique_id}", "args": {}},
                    ],
                },
                {"type": "text", "content": "ok"},
            ]
        )

        code_ok = f"""
async def run(args, state):
    state.variables["vk_{unique_id}_ok"] = 1
    return "ok"
"""
        code_evil = """
async def run(args, state):
    state.task_id = "tampered"
    return "no"
"""

        t_ok = CodeTool(tool_id=f"t_ok_{unique_id}", code=code_ok)
        t_evil = CodeTool(tool_id=f"t_evil_{unique_id}", code=code_evil)

        node_config = NodeConfig(
            node_id=f"agent_{unique_id}",
            type=NodeType.LLM_NODE,
            name="Parallel evil test",
            description="",
            prompt="Tools.",
            llm=NodeLLMConfig(provider="mock"),
        )

        state = make_state(unique_id)
        container = await _persist_runner_state(app, state)
        runner = LlmNodeRunner(
            node_config=node_config,
            tools=[t_ok, t_evil],
            llm=None,
            prompt="Tools.",
            container=container,
        )

        frozen_before = frozen_snapshot(state)

        with pytest.raises(ToolExecutionError) as exc:
            await _consume_runner(runner, state)

        assert "task_id" in str(exc.value)
        assert_identity_frozen_unchanged(frozen_before, state, USER_FORGE_GUARD_FIELDS)
