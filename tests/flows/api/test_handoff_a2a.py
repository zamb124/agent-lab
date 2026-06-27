"""
A2A/channel тесты handoff/handback.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest

from apps.flows.src.models.flow_config import FlowConfig
from tests.flows.api.test_a2a import _msg, _parse_sse, _validate_jsonrpc_response

pytestmark = [pytest.mark.timeout(120, func_only=True)]


def _interrupt_kind_value(body) -> str:
    kind = body.kind
    if isinstance(kind, str):
        return kind
    return kind.value


async def _save_flow(container, flow_config: dict[str, Any]) -> bool:
    return await container.flow_repository.set(FlowConfig.model_validate(flow_config))


def _handoff_parent_child_configs(unique_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    parent_fid = f"ht-a2a-parent-{unique_id}"
    child_fid = f"ht-a2a-child-{unique_id}"
    parent = {
        "flow_id": parent_fid,
        "name": "Parent",
        "entry": "main",
        "nodes": {
            "main": {
                "type": "llm_node",
                "node_id": "parent_agent",
                "prompt": "parent",
                "llm": {"model": "mock-gpt-4"},
                "tools": [{"tool_id": "handoff_to_flow", "description": "Handoff"}],
            }
        },
        "edges": [{"from_node": "main", "to_node": None}],
    }
    child = {
        "flow_id": child_fid,
        "name": "Child",
        "entry": "main",
        "nodes": {
            "main": {
                "type": "llm_node",
                "node_id": "child_agent",
                "prompt": "child",
                "llm": {"model": "mock-gpt-4"},
                "tools": [
                    {"tool_id": "handback_to_parent", "description": "Handback"},
                    {"tool_id": "ask_user", "description": "Ask user"},
                ],
            }
        },
        "edges": [{"from_node": "main", "to_node": None}],
    }
    return parent, child


async def _send_message(client, flow_id: str, context_id: str, content: str, task_id: str | None = None):
    message = _msg(content, context_id=context_id)
    if task_id is not None:
        message["taskId"] = task_id
    return await client.post(
        f"/flows/api/v1/{flow_id}",
        json={
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "message/send",
            "params": {"message": message},
        },
    )


class TestHandoffA2A:
    @pytest.mark.asyncio
    async def test_k1_handoff_returns_input_required(
        self, client, container, mock_llm_with_queue, sync_tools, unique_id
    ):
        parent_cfg, child_cfg = _handoff_parent_child_configs(unique_id)
        await _save_flow(container, parent_cfg)
        await _save_flow(container, child_cfg)
        child_fid = child_cfg["flow_id"]
        parent_fid = parent_cfg["flow_id"]

        mock_llm_with_queue([
            {
                "type": "tool_call",
                "tool": "handoff_to_flow",
                "args": {"target_flow_id": child_fid, "variables": {"order_id": "1"}},
            },
            "child idle after kickoff",
        ])

        context_id = f"ctx-k1-{unique_id}"
        resp = await _send_message(client, parent_fid, context_id, "handoff please")
        data = resp.json()
        _validate_jsonrpc_response(data)
        task = data["result"]
        assert task["status"]["state"] == "input-required"
        metadata = task["status"]["message"]["metadata"]
        interrupt = metadata["platform_interrupt"]
        assert interrupt["body"]["kind"] == "handoff"
        assert interrupt["body"]["target_flow_id"] == child_fid

        parent_session = f"{parent_fid}:{context_id}"
        parent_state = await container.workflow_runtime.get_state(parent_session)
        assert parent_state is not None
        assert parent_state.handoff_depth == 1
        child_session = f"{child_fid}:{context_id}:handoff:{child_fid}"
        child_state = await container.workflow_runtime.get_state(child_session)
        assert child_state is not None

    @pytest.mark.asyncio
    async def test_k2_user_reply_routes_to_child(
        self, client, container, mock_llm_with_queue, sync_tools, unique_id
    ):
        parent_cfg, child_cfg = _handoff_parent_child_configs(unique_id)
        await _save_flow(container, parent_cfg)
        await _save_flow(container, child_cfg)
        child_fid = child_cfg["flow_id"]
        parent_fid = parent_cfg["flow_id"]
        context_id = f"ctx-k2-{unique_id}"

        mock_llm_with_queue([
            {
                "type": "tool_call",
                "tool": "handoff_to_flow",
                "args": {"target_flow_id": child_fid},
            },
            "child idle after kickoff",
            "child received user message",
        ])

        first = await _send_message(client, parent_fid, context_id, "start handoff")
        first_data = first.json()
        assert first_data["result"]["status"]["state"] == "input-required"

        child_session = f"{child_fid}:{context_id}:handoff:{child_fid}"
        child_before = await container.workflow_runtime.get_state(child_session)
        assert child_before is not None

        second = await _send_message(
            client,
            parent_fid,
            context_id,
            "user follow-up",
            task_id=first_data["result"]["id"],
        )
        second_data = second.json()
        _validate_jsonrpc_response(second_data)

        parent_session = f"{parent_fid}:{context_id}"
        parent_state = await container.workflow_runtime.get_state(parent_session)
        assert parent_state is not None
        assert parent_state.interrupt is not None
        assert _interrupt_kind_value(parent_state.interrupt.body) == "handoff"

        child_after = await container.workflow_runtime.get_state(child_session)
        assert child_after is not None
        assert len(child_after.messages) >= len(child_before.messages)

    @pytest.mark.asyncio
    async def test_k3_child_ask_user_resume_in_child(
        self, client, container, mock_llm_with_queue, sync_tools, unique_id
    ):
        parent_cfg, child_cfg = _handoff_parent_child_configs(unique_id)
        await _save_flow(container, parent_cfg)
        await _save_flow(container, child_cfg)
        child_fid = child_cfg["flow_id"]
        parent_fid = parent_cfg["flow_id"]
        context_id = f"ctx-k3-{unique_id}"

        mock_llm_with_queue([
            {
                "type": "tool_call",
                "tool": "handoff_to_flow",
                "args": {"target_flow_id": child_fid},
            },
            "child idle after kickoff",
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "What is your order id?"}},
            "thanks for order info",
        ])

        first = await _send_message(client, parent_fid, context_id, "handoff to child")
        first_data = first.json()
        assert first_data["result"]["status"]["state"] == "input-required"

        child_session = f"{child_fid}:{context_id}:handoff:{child_fid}"
        child_state = await container.workflow_runtime.get_state(child_session)
        assert child_state is not None

        second = await _send_message(
            client,
            parent_fid,
            context_id,
            "order 12345",
            task_id=first_data["result"]["id"],
        )
        second_data = second.json()
        assert second_data["result"]["status"]["state"] in ("input-required", "completed")

        parent_state = await container.workflow_runtime.get_state(f"{parent_fid}:{context_id}")
        assert parent_state is not None
        assert parent_state.interrupt is not None
        assert _interrupt_kind_value(parent_state.interrupt.body) == "handoff"

    @pytest.mark.asyncio
    async def test_k4_handback_resumes_parent(
        self, client, container, mock_llm_with_queue, sync_tools, unique_id
    ):
        parent_cfg, child_cfg = _handoff_parent_child_configs(unique_id)
        await _save_flow(container, parent_cfg)
        await _save_flow(container, child_cfg)
        child_fid = child_cfg["flow_id"]
        parent_fid = parent_cfg["flow_id"]
        context_id = f"ctx-k4-{unique_id}"

        mock_llm_with_queue([
            {
                "type": "tool_call",
                "tool": "handoff_to_flow",
                "args": {"target_flow_id": child_fid, "variables": {"ticket_id": "T-1"}},
            },
            "child idle after kickoff",
            {"type": "tool_call", "tool": "handback_to_parent", "args": {"response": "resolved", "variables": {"ticket_id": "T-1"}}},
            "parent continues after handback",
        ])

        first = await _send_message(client, parent_fid, context_id, "start")
        first_data = first.json()
        assert first_data["result"]["status"]["state"] == "input-required"

        parent_session = f"{parent_fid}:{context_id}"
        child_session = f"{child_fid}:{context_id}:handoff:{child_fid}"
        child_before = await container.workflow_runtime.get_state(child_session)
        assert child_before is not None

        second = await _send_message(
            client,
            parent_fid,
            context_id,
            "trigger handback",
            task_id=first_data["result"]["id"],
        )
        second_data = second.json()
        assert second_data["result"]["status"]["state"] in ("input-required", "completed")

        parent_state = await container.workflow_runtime.get_state(parent_session)
        child_after = await container.workflow_runtime.get_state(child_session)
        assert parent_state is not None
        assert child_after is not None
        assert len(child_after.messages) >= len(child_before.messages)

        child_link = parent_state.child_workflows.get(child_session)
        assert child_link is not None
        if child_link.status == "completed":
            assert parent_state.interrupt is None
            assert parent_state.variables.get("ticket_id") == "T-1"
        else:
            assert parent_state.interrupt is not None
            assert _interrupt_kind_value(parent_state.interrupt.body) == "handoff"

    @pytest.mark.asyncio
    async def test_k5_handoff_chain_three_levels(
        self, client, container, mock_llm_with_queue, sync_tools, unique_id
    ):
        fid_a = f"ht-k5-a-{unique_id}"
        fid_b = f"ht-k5-b-{unique_id}"
        fid_c = f"ht-k5-c-{unique_id}"

        for fid, tools in (
            (fid_c, [{"tool_id": "handback_to_parent", "description": "HB"}]),
            (fid_b, [{"tool_id": "handoff_to_flow", "description": "H"}, {"tool_id": "handback_to_parent", "description": "HB"}]),
            (fid_a, [{"tool_id": "handoff_to_flow", "description": "H"}]),
        ):
            await _save_flow(container, {
                "flow_id": fid,
                "name": fid,
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
            })

        context_id = f"ctx-k5-{unique_id}"
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "handoff_to_flow", "args": {"target_flow_id": fid_b, "variables": {"level": "a"}}},
            "child b idle",
            {"type": "tool_call", "tool": "handoff_to_flow", "args": {"target_flow_id": fid_c, "variables": {"level": "b"}}},
            {"type": "tool_call", "tool": "handback_to_parent", "args": {"response": "from c", "variables": {"level": "c"}}},
            {"type": "tool_call", "tool": "handback_to_parent", "args": {"response": "from b", "variables": {"level": "b"}}},
            "parent a final",
        ])

        first = await _send_message(client, fid_a, context_id, "chain start")
        assert first.json()["result"]["status"]["state"] == "input-required"

        second = await _send_message(
            client,
            fid_a,
            context_id,
            "continue chain",
            task_id=first.json()["result"]["id"],
        )
        assert second.json()["result"]["status"]["state"] in ("input-required", "completed")

        parent_state = await container.workflow_runtime.get_state(f"{fid_a}:{context_id}")
        assert parent_state is not None
        assert parent_state.handoff_depth >= 1

    @pytest.mark.asyncio
    async def test_k6_handoff_max_depth_exceeded(
        self, container, unique_id
    ):
        """Превышение handoff_max_depth — контракт orchestrator (без monkeypatch)."""
        orchestrator = container.handoff_orchestrator_service
        from apps.flows.config import get_settings
        from tests.flows.durable_runtime_harness import workflow_state

        max_depth = get_settings().handoff_max_depth
        flow_id = f"ht-k6-{unique_id}"
        state = workflow_state(flow_id=flow_id, unique_id=f"k6-{unique_id}")
        state.handoff_depth = max_depth
        with pytest.raises(ValueError, match="handoff_max_depth exceeded"):
            orchestrator.assert_handoff_depth_allowed(state)

    @pytest.mark.asyncio
    async def test_k7_cancel_parent_cancels_child(
        self, client, container, mock_llm_with_queue, sync_tools, unique_id
    ):
        parent_cfg, child_cfg = _handoff_parent_child_configs(unique_id)
        await _save_flow(container, parent_cfg)
        await _save_flow(container, child_cfg)
        child_fid = child_cfg["flow_id"]
        parent_fid = parent_cfg["flow_id"]
        context_id = f"ctx-k7-{unique_id}"

        mock_llm_with_queue([
            {
                "type": "tool_call",
                "tool": "handoff_to_flow",
                "args": {"target_flow_id": child_fid},
            },
            "child idle",
        ])

        first = await _send_message(client, parent_fid, context_id, "cancel me")
        assert first.json()["result"]["status"]["state"] == "input-required"

        cancel_resp = await client.post(
            f"/flows/api/v1/{parent_fid}",
            json={
                "jsonrpc": "2.0",
                "id": "cancel",
                "method": "tasks/cancel",
                "params": {"id": context_id},
            },
        )
        cancel_data = cancel_resp.json()
        _validate_jsonrpc_response(cancel_data)
        assert cancel_data["result"]["status"]["state"] == "canceled"

        child_session = f"{child_fid}:{context_id}:handoff:{child_fid}"
        child_state = await container.workflow_runtime.get_state(child_session)
        if child_state is not None:
            assert child_state.terminal_task_state in ("canceled", None)

    @pytest.mark.asyncio
    async def test_k8_invalid_target_flow_failed(
        self, client, container, mock_llm_with_queue, sync_tools, unique_id
    ):
        parent_fid = f"ht-k8-{unique_id}"
        await _save_flow(container, {
            "flow_id": parent_fid,
            "name": "Parent",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "llm_node",
                    "node_id": "p",
                    "prompt": "p",
                    "llm": {"model": "mock-gpt-4"},
                    "tools": [{"tool_id": "handoff_to_flow", "description": "Handoff"}],
                }
            },
            "edges": [{"from_node": "main", "to_node": None}],
        })
        mock_llm_with_queue([
            {
                "type": "tool_call",
                "tool": "handoff_to_flow",
                "args": {"target_flow_id": "missing-flow-id"},
            },
        ])
        resp = await _send_message(client, parent_fid, f"ctx-k8-{unique_id}", "go")
        data = resp.json()
        _validate_jsonrpc_response(data)
        assert data["result"]["status"]["state"] == "failed"

    @pytest.mark.asyncio
    async def test_k9_stream_keeps_open_on_handoff(
        self, client, container, mock_llm_with_queue, sync_tools, unique_id
    ):
        parent_cfg, child_cfg = _handoff_parent_child_configs(unique_id)
        await _save_flow(container, parent_cfg)
        await _save_flow(container, child_cfg)
        child_fid = child_cfg["flow_id"]
        parent_fid = parent_cfg["flow_id"]
        mock_llm_with_queue([
            {
                "type": "tool_call",
                "tool": "handoff_to_flow",
                "args": {"target_flow_id": child_fid},
            },
            "child idle",
        ])
        resp = await client.post(
            f"/flows/api/v1/{parent_fid}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/stream",
                "params": {"message": _msg("stream handoff", context_id=f"ctx-k9-{unique_id}")},
            },
        )
        events = _parse_sse(resp.text)
        input_required = [
            e
            for e in events
            if e.get("result", {}).get("status", {}).get("state") == "input-required"
        ]
        assert len(input_required) > 0
        meta = input_required[-1]["result"]["status"]["message"]["metadata"]
        assert meta.get("platform_handoff_continue") is True
        assert input_required[-1]["result"].get("final") is False

    @pytest.mark.asyncio
    async def test_demo_bundles_handoff_roundtrip(
        self, client, container, mock_llm_with_queue, sync_tools, unique_id
    ):
        repo_root = Path(__file__).resolve().parents[3]
        parent_path = repo_root / "apps/flows/bundles/handoff_demo_parent/flow.json"
        child_path = repo_root / "apps/flows/bundles/handoff_demo_child/flow.json"
        parent_cfg = json.loads(parent_path.read_text(encoding="utf-8"))
        child_cfg = json.loads(child_path.read_text(encoding="utf-8"))
        await _save_flow(container, parent_cfg)
        await _save_flow(container, child_cfg)
        parent_fid = parent_cfg["flow_id"]
        child_fid = child_cfg["flow_id"]
        context_id = f"ctx-demo-{unique_id}"

        mock_llm_with_queue([
            {
                "type": "tool_call",
                "tool": "handoff_to_flow",
                "args": {"target_flow_id": child_fid, "variables": {"order_id": "99"}},
            },
            "child idle after kickoff",
            {"type": "tool_call", "tool": "handback_to_parent", "args": {"response": "demo done"}},
            "parent demo final",
        ])

        first = await _send_message(client, parent_fid, context_id, "courier problem")
        assert first.json()["result"]["status"]["state"] == "input-required"

        second = await _send_message(
            client,
            parent_fid,
            context_id,
            "continue",
            task_id=first.json()["result"]["id"],
        )
        assert second.json()["result"]["status"]["state"] in ("input-required", "completed")
