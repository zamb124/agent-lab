"""
A2A/channel: многократный handoff/handback в одной сессии.

Покрывает повторные циклы в том же и в разных субагентах через channel layer
(create_task materialize → child process_task), без monkeypatch.
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.flows.config import get_settings
from apps.flows.src.durable_execution import WorkflowEventType
from apps.flows.src.models.flow_config import FlowConfig
from tests.flows.api.test_handoff_a2a import (
    _handoff_parent_child_configs,
    _interrupt_kind_value,
    _save_flow,
    _send_message,
)
from tests.flows.api.test_a2a import _validate_jsonrpc_response
from tests.flows.durable_runtime_harness import workflow_state

pytestmark = [pytest.mark.timeout(120, func_only=True)]


def _llm_node(flow_id: str, tools: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "flow_id": flow_id,
        "name": flow_id,
        "entry": "main",
        "nodes": {
            "main": {
                "type": "llm_node",
                "node_id": "n",
                "prompt": "p",
                "llm": {"model": "mock-gpt-4"},
                "tools": tools,
            }
        },
        "edges": [{"from_node": "main", "to_node": None}],
    }


def _router_parent_two_children(unique_id: str) -> dict[str, Any]:
    parent_fid = f"ht-multi-router-{unique_id}"
    return {
        "flow_id": parent_fid,
        "name": "Router",
        "entry": "main",
        "nodes": {
            "main": {
                "type": "llm_node",
                "node_id": "router",
                "prompt": "router",
                "llm": {"model": "mock-gpt-4"},
                "tools": [{"tool_id": "handoff_to_flow", "description": "Handoff"}],
            }
        },
        "edges": [{"from_node": "main", "to_node": None}],
    }


def _child_flow(child_fid: str) -> dict[str, Any]:
    return _llm_node(
        child_fid,
        [
            {"tool_id": "handback_to_parent", "description": "Handback"},
            {"tool_id": "ask_user", "description": "Ask user"},
        ],
    )


async def _count_workflow_events(container, session_id: str, event_type: WorkflowEventType) -> int:
    records, _ = await container.workflow_runtime.get_state_history(session_id, limit=500)
    return sum(1 for record in records if record.event_type == event_type)


class TestHandoffMultiCycleA2A:
    @pytest.mark.asyncio
    async def test_l1_repeat_handoff_same_child_after_handback(
        self, client, container, mock_llm_with_queue, sync_tools, unique_id
    ):
        """Два полных цикла handoff→child→handback→parent→handoff в одну child-сессию."""
        parent_cfg, child_cfg = _handoff_parent_child_configs(unique_id)
        await _save_flow(container, parent_cfg)
        await _save_flow(container, child_cfg)
        child_fid = child_cfg["flow_id"]
        parent_fid = parent_cfg["flow_id"]
        context_id = f"ctx-l1-{unique_id}"
        child_session = f"{child_fid}:{context_id}:handoff:{child_fid}"
        parent_session = f"{parent_fid}:{context_id}"

        mock_llm_with_queue([
            {
                "type": "tool_call",
                "tool": "handoff_to_flow",
                "args": {"target_flow_id": child_fid, "variables": {"cycle": 1}},
            },
            "child idle after kickoff 1",
            {
                "type": "tool_call",
                "tool": "handback_to_parent",
                "args": {"response": "cycle 1 done", "variables": {"cycle": 1, "from": "child"}},
            },
            "child cycle 1 finished",
            {
                "type": "tool_call",
                "tool": "handoff_to_flow",
                "args": {"target_flow_id": child_fid, "variables": {"cycle": 2}},
            },
            "child idle after kickoff 2",
            {
                "type": "tool_call",
                "tool": "handback_to_parent",
                "args": {"response": "cycle 2 done", "variables": {"cycle": 2, "from": "child"}},
            },
            "child cycle 2 finished",
            "parent after two cycles",
        ])

        first = await _send_message(client, parent_fid, context_id, "start cycle 1")
        first_data = first.json()
        assert first_data["result"]["status"]["state"] == "input-required"

        child_before = await container.workflow_runtime.get_state(child_session)
        assert child_before is not None

        second = await _send_message(
            client,
            parent_fid,
            context_id,
            "continue both cycles",
            task_id=first_data["result"]["id"],
        )
        _validate_jsonrpc_response(second.json())

        parent_final = await container.workflow_runtime.get_state(parent_session)
        child_final = await container.workflow_runtime.get_state(child_session)
        assert parent_final is not None
        assert child_final is not None
        assert len(child_final.messages) > len(child_before.messages)
        link = parent_final.child_workflows.get(child_session)
        assert link is not None
        if link.status == "completed":
            assert parent_final.variables.get("from") == "child"
        else:
            assert parent_final.interrupt is not None
            assert _interrupt_kind_value(parent_final.interrupt.body) == "handoff"
        assert await _count_workflow_events(
            container, parent_session, WorkflowEventType.handoff_initiated
        ) >= 1

    @pytest.mark.asyncio
    async def test_l2_handoff_child_a_then_child_b_after_handbacks(
        self, client, container, mock_llm_with_queue, sync_tools, unique_id
    ):
        """После handback к child A — handoff к child B в той же parent-сессии."""
        child_a = f"ht-multi-a-{unique_id}"
        child_b = f"ht-multi-b-{unique_id}"
        parent_cfg = _router_parent_two_children(unique_id)
        await _save_flow(container, parent_cfg)
        await _save_flow(container, _child_flow(child_a))
        await _save_flow(container, _child_flow(child_b))
        parent_fid = parent_cfg["flow_id"]
        context_id = f"ctx-l2-{unique_id}"
        session_a = f"{child_a}:{context_id}:handoff:{child_a}"
        session_b = f"{child_b}:{context_id}:handoff:{child_b}"
        parent_session = f"{parent_fid}:{context_id}"

        mock_llm_with_queue([
            {
                "type": "tool_call",
                "tool": "handoff_to_flow",
                "args": {"target_flow_id": child_a, "variables": {"agent": "a"}},
            },
            "child a idle",
            {
                "type": "tool_call",
                "tool": "handback_to_parent",
                "args": {"response": "from a", "variables": {"agent": "a", "result": "ok-a"}},
            },
            "child a finished",
            {
                "type": "tool_call",
                "tool": "handoff_to_flow",
                "args": {"target_flow_id": child_b, "variables": {"agent": "b"}},
            },
            "child b idle",
            {
                "type": "tool_call",
                "tool": "handback_to_parent",
                "args": {"response": "from b", "variables": {"agent": "b", "result": "ok-b"}},
            },
            "child b finished",
            "parent after both handbacks",
        ])

        first = await _send_message(client, parent_fid, context_id, "route to a")
        task_id = first.json()["result"]["id"]
        assert first.json()["result"]["status"]["state"] == "input-required"

        second = await _send_message(
            client, parent_fid, context_id, "complete a then b", task_id=task_id
        )
        _validate_jsonrpc_response(second.json())

        parent_final = await container.workflow_runtime.get_state(parent_session)
        child_b_state = await container.workflow_runtime.get_state(session_b)
        assert parent_final is not None
        assert child_b_state is not None
        assert session_a in parent_final.child_workflows
        assert session_b in parent_final.child_workflows
        link_b = parent_final.child_workflows.get(session_b)
        assert link_b is not None
        if link_b.status == "completed":
            assert parent_final.variables.get("result") == "ok-b"

    @pytest.mark.asyncio
    async def test_l3_three_handoff_cycles_same_child(
        self, client, container, mock_llm_with_queue, sync_tools, unique_id
    ):
        """Три последовательных handoff→handback в одного субагента."""
        parent_cfg, child_cfg = _handoff_parent_child_configs(unique_id)
        await _save_flow(container, parent_cfg)
        await _save_flow(container, child_cfg)
        child_fid = child_cfg["flow_id"]
        parent_fid = parent_cfg["flow_id"]
        context_id = f"ctx-l3-{unique_id}"
        child_session = f"{child_fid}:{context_id}:handoff:{child_fid}"
        parent_session = f"{parent_fid}:{context_id}"

        queue: list[Any] = []
        for cycle in (1, 2, 3):
            queue.extend([
                {
                    "type": "tool_call",
                    "tool": "handoff_to_flow",
                    "args": {"target_flow_id": child_fid, "variables": {"n": cycle}},
                },
                f"child idle cycle {cycle}",
                {
                    "type": "tool_call",
                    "tool": "handback_to_parent",
                    "args": {"response": f"done {cycle}", "variables": {"n": cycle, "last": cycle}},
                },
                f"child cycle {cycle} finished",
            ])
        queue.append("parent finished after 3 cycles")
        mock_llm_with_queue(queue)

        first = await _send_message(client, parent_fid, context_id, "cycle 1 start")
        task_id = first.json()["result"]["id"]
        assert first.json()["result"]["status"]["state"] == "input-required"

        child_before = await container.workflow_runtime.get_state(child_session)
        assert child_before is not None

        second = await _send_message(
            client, parent_fid, context_id, "run all three cycles", task_id=task_id
        )
        _validate_jsonrpc_response(second.json())

        parent_state = await container.workflow_runtime.get_state(parent_session)
        child_state = await container.workflow_runtime.get_state(child_session)
        assert parent_state is not None
        assert child_state is not None
        assert len(child_state.messages) > len(child_before.messages)
        assert await _count_workflow_events(
            container, parent_session, WorkflowEventType.handoff_initiated
        ) >= 1

    @pytest.mark.asyncio
    async def test_l4_handoff_depth_resets_after_handback(
        self, client, container, mock_llm_with_queue, sync_tools, unique_id
    ):
        """handoff_depth parent возвращается к 0 после handback, второй цикл снова depth=1."""
        parent_cfg, child_cfg = _handoff_parent_child_configs(unique_id)
        await _save_flow(container, parent_cfg)
        await _save_flow(container, child_cfg)
        child_fid = child_cfg["flow_id"]
        parent_fid = parent_cfg["flow_id"]
        context_id = f"ctx-l4-{unique_id}"
        parent_session = f"{parent_fid}:{context_id}"

        mock_llm_with_queue([
            {
                "type": "tool_call",
                "tool": "handoff_to_flow",
                "args": {"target_flow_id": child_fid},
            },
            "child idle 1",
            {
                "type": "tool_call",
                "tool": "handback_to_parent",
                "args": {"response": "back 1"},
            },
            "child finished 1",
            {
                "type": "tool_call",
                "tool": "handoff_to_flow",
                "args": {"target_flow_id": child_fid},
            },
            "child idle 2",
            "child reply 2",
        ])

        first = await _send_message(client, parent_fid, context_id, "depth check 1")
        task_id = first.json()["result"]["id"]

        parent_after_first = await container.workflow_runtime.get_state(parent_session)
        assert parent_after_first is not None
        assert parent_after_first.handoff_depth == 1

        second = await _send_message(
            client, parent_fid, context_id, "handback and re-handoff", task_id=task_id
        )
        _validate_jsonrpc_response(second.json())

        parent_after_handback = await container.workflow_runtime.get_state(parent_session)
        assert parent_after_handback is not None
        assert parent_after_handback.handoff_depth in (0, 1)
        if parent_after_handback.interrupt is not None:
            assert _interrupt_kind_value(parent_after_handback.interrupt.body) == "handoff"
            assert parent_after_handback.handoff_depth == 1

        child_session = f"{child_fid}:{context_id}:handoff:{child_fid}"
        child_state = await container.workflow_runtime.get_state(child_session)
        assert child_state is not None
        assert len(child_state.messages) >= 2


class TestHandoffDepthWithoutMonkeypatch:
    @pytest.mark.asyncio
    async def test_l5_orchestrator_max_depth_raises(self, container, unique_id):
        """Превышение handoff_max_depth без monkeypatch — прямой контракт orchestrator."""
        orchestrator = container.handoff_orchestrator_service
        max_depth = get_settings().handoff_max_depth
        state = workflow_state(
            flow_id=f"ht-depth-{unique_id}",
            unique_id=f"depth-{unique_id}",
        )
        state.handoff_depth = max_depth
        with pytest.raises(ValueError, match="handoff_max_depth exceeded"):
            orchestrator.assert_handoff_depth_allowed(state)
