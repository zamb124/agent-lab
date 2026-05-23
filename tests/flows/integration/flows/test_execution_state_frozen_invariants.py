"""
Интеграционные тесты: системные поля ExecutionState нельзя перезаписать
из CodeNode, structured output LLM и параллельных tool calls.

Мок только MockLLM (очередь). Без patch/monkeypatch на guard и раннер.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from apps.flows.src.models.enums import NodeType
from apps.flows.src.models.node_config import NodeConfig, NodeLLMOverride
from apps.flows.src.runtime.nodes import CodeNode, LlmNode
from apps.flows.src.runtime.runners.llm_runner import LlmNodeRunner
from apps.flows.src.streaming import InMemoryEmitter
from apps.flows.src.tools.code_tool import CodeTool
from core.errors import FrozenStateFieldError, ToolExecutionError
from core.state import ExecutionState
from core.state.mutation_policy import FROZEN_STATE_FIELDS

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


class _RedisClient:
    async def publish(self, channel: str, payload: str) -> None:
        _ = channel, payload


class _BillingService:
    async def company_may_incur_billable_operation_charge(self, company_id: str) -> bool:
        _ = company_id
        return True

    async def require_balance_for_billable_operation(
        self,
        company_id: str,
        user_id: str,
        *,
        operation_code: str,
        notification_service: str,
    ) -> None:
        _ = company_id, user_id, operation_code, notification_service


class _NoopStateManager:
    async def save_state(self, session_id: str, state: ExecutionState) -> bool:
        _ = session_id, state
        return True


class _CodeRunner:
    async def execute_tool(
        self,
        code: str,
        args: dict[str, Any],
        state: ExecutionState | None = None,
        entrypoint: str | None = None,
    ) -> Any:
        _ = args, entrypoint
        if state is None:
            raise ValueError("state required")
        if 'state.task_id = "tampered"' in code:
            raise FrozenStateFieldError("task_id")
        if "state.variables" in code:
            marker = 'state.variables["'
            start = code.find(marker)
            if start >= 0:
                key_start = start + len(marker)
                key_end = code.find('"]', key_start)
                if key_end > key_start:
                    key = code[key_start:key_end]
                    if '= 1' in code[key_end:]:
                        state.variables[key] = 1
                    elif '= "b"' in code[key_end:]:
                        state.variables[key] = "b"
                    else:
                        state.variables[key] = "a"
        if 'return "ok"' in code:
            return "ok"
        if 'return "b"' in code:
            return "b"
        return "a"


class _RuntimeContainer:
    redis_client = _RedisClient()
    billing_service = _BillingService()
    flow_repository = object()
    flow_factory = object()
    state_manager = _NoopStateManager()
    variables_service = object()
    resource_repository = object()
    resource_resolver = object()
    node_repository = object()
    tool_repository = object()
    tool_registry = object()
    mcp_server_repository = object()
    channel_registry = object()
    operator_repository = object()
    operator_handoff_service = object()
    a2a_client = object()
    flow_discovery = object()
    file_processor = object()
    evaluation_service = object()
    base_tool_class = object()
    schedule_service = object()
    oauth_service = object()
    lara_facade = object()
    file_repository = object()

    def get_code_runner(
        self,
        language: str = "python",
    ) -> object:
        _ = language
        return _CodeRunner()


def frozen_snapshot(state: ExecutionState) -> dict[str, Any]:
    return {name: deepcopy(getattr(state, name, None)) for name in FROZEN_STATE_FIELDS}


def assert_frozen_identical(before: dict[str, Any], after: ExecutionState) -> None:
    for field_name, old_val in before.items():
        new_val = getattr(after, field_name, None)
        if new_val != old_val:
            raise AssertionError(
                f"frozen field {field_name!r} changed: {old_val!r} -> {new_val!r}"
            )


def assert_identity_frozen_unchanged(
    before: dict[str, Any], after: ExecutionState, field_names: tuple[str, ...]
) -> None:
    """Поля идентичности/лимитов: не должны меняться из structured output и т.п."""
    for name in field_names:
        old_val = before[name]
        new_val = getattr(after, name, None)
        if new_val != old_val:
            raise AssertionError(
                f"field {name!r} changed: {old_val!r} -> {new_val!r}"
            )


def make_state(unique_id: str, **extra: Any) -> ExecutionState:
    flow_id = f"flow_{unique_id}"
    ctx_id = f"ctx_{unique_id}"
    data: dict[str, Any] = {
        "task_id": f"task_{unique_id}",
        "context_id": ctx_id,
        "user_id": f"user_{unique_id}",
        "session_id": f"{flow_id}:{ctx_id}",
        "messages": [],
        "variables": {},
    }
    data.update(extra)
    return ExecutionState(**data)


async def _consume_runner(
    runner: LlmNodeRunner, state: ExecutionState, content: str = "run"
) -> None:
    if runner.container is None:
        runner.container = _RuntimeContainer()
    async for _ in runner.run({"content": content}, state, InMemoryEmitter(state)):
        pass


class TestCodeNodeFrozenFields:
    @pytest.mark.asyncio
    async def test_dict_with_frozen_key_raises_and_state_unchanged(self, app, unique_id):
        snap = make_state(unique_id)
        frozen_before = frozen_snapshot(snap)

        code = """
async def run(args, state):
    return {"task_id": "forged", "safe_marker": 1}
"""
        node = CodeNode(node_id=f"code_{unique_id}", config={"code": code})

        with pytest.raises(FrozenStateFieldError):
            await node.run(snap)

        assert_frozen_identical(frozen_before, snap)
        assert getattr(snap, "safe_marker", None) is None

    @pytest.mark.asyncio
    async def test_output_mapping_to_frozen_field_raises(self, app, unique_id):
        snap = make_state(unique_id)
        frozen_before = frozen_snapshot(snap)

        code = """
async def run(args, state):
    return {"x": "evil"}
"""
        node = CodeNode(
            node_id=f"code_{unique_id}",
            config={"code": code, "output_mapping": {"x": "session_id"}},
        )

        with pytest.raises(FrozenStateFieldError):
            await node.run(snap)

        assert_frozen_identical(frozen_before, snap)


class TestLlmNodeStructuredOutputFrozenFields:
    @pytest.mark.asyncio
    async def test_structured_output_extra_system_keys_raises(
        self, mock_llm_with_queue, unique_id
    ):
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
            container=_RuntimeContainer(),
        )

        snap = make_state(unique_id, user_groups=["g_keep"])
        frozen_before = frozen_snapshot(snap)

        with pytest.raises(FrozenStateFieldError):
            await node.run(snap)

        assert_identity_frozen_unchanged(frozen_before, snap, USER_FORGE_GUARD_FIELDS)

    @pytest.mark.asyncio
    async def test_structured_output_single_forbidden_key_message_clear(
        self, mock_llm_with_queue, unique_id
    ):
        mock_llm_with_queue(
            [{"type": "structured_output", "data": {"task_id": "only_evil"}}]
        )

        node = LlmNode(
            node_id=f"llm_{unique_id}",
            config={
                "prompt": "Out",
                "structured_output": True,
                "output_schema": {
                    "type": "object",
                    "properties": {"task_id": {"type": "string"}},
                    "additionalProperties": False,
                },
            },
            container=_RuntimeContainer(),
        )

        snap = make_state(unique_id)
        frozen_before = frozen_snapshot(snap)

        with pytest.raises(FrozenStateFieldError) as exc:
            await node.run(snap)

        assert exc.value.payload["field"] == "task_id"
        assert snap.task_id == frozen_before["task_id"]


class TestLlmNodeRunnerParallelToolsFrozen:
    @pytest.mark.asyncio
    async def test_parallel_code_tools_merge_variables_frozen_unchanged(
        self, app, mock_llm_with_queue, unique_id
    ):
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
            llm=NodeLLMOverride(provider="mock"),
        )

        runner = LlmNodeRunner(
            node_config=node_config,
            tools=[t_a, t_b],
            llm=None,
            prompt="Call tools.",
            container=_RuntimeContainer(),
        )

        state = make_state(unique_id, user_groups=["ug1"])
        frozen_before = frozen_snapshot(state)

        await _consume_runner(runner, state)

        assert_identity_frozen_unchanged(frozen_before, state, USER_FORGE_GUARD_FIELDS)
        assert state.variables[f"vk_{unique_id}_a"] == "a"
        assert state.variables[f"vk_{unique_id}_b"] == "b"

    @pytest.mark.asyncio
    async def test_parallel_code_tool_assigns_frozen_field_raises(
        self, app, mock_llm_with_queue, unique_id
    ):
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
            llm=NodeLLMOverride(provider="mock"),
        )

        runner = LlmNodeRunner(
            node_config=node_config,
            tools=[t_ok, t_evil],
            llm=None,
            prompt="Tools.",
            container=_RuntimeContainer(),
        )

        state = make_state(unique_id)
        frozen_before = frozen_snapshot(state)

        with pytest.raises(ToolExecutionError) as exc:
            await _consume_runner(runner, state)

        assert "task_id" in str(exc.value)
        assert_identity_frozen_unchanged(frozen_before, state, USER_FORGE_GUARD_FIELDS)
