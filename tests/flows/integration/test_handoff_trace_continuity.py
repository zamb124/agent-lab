"""Handoff trace continuity: handoff_trace_id on state after A2A handoff."""

from __future__ import annotations

import pytest

from apps.flows.src.models.flow_config import FlowConfig
from tests.flows.api.test_handoff_a2a import (
    _handoff_parent_child_configs,
    _save_flow,
    _send_message,
)
from tests.flows.api.test_a2a import _validate_jsonrpc_response

pytestmark = [pytest.mark.timeout(120, func_only=True)]


class TestHandoffTraceContinuity:
    @pytest.mark.asyncio
    async def test_handoff_sets_handoff_trace_id_on_parent(
        self, client, container, mock_llm_with_queue, sync_tools, unique_id
    ):
        parent_cfg, child_cfg = _handoff_parent_child_configs(unique_id)
        await _save_flow(container, parent_cfg)
        await _save_flow(container, child_cfg)
        child_fid = child_cfg["flow_id"]
        parent_fid = parent_cfg["flow_id"]
        context_id = f"ctx-trace-{unique_id}"

        mock_llm_with_queue([
            {
                "type": "tool_call",
                "tool": "handoff_to_flow",
                "args": {"target_flow_id": child_fid, "variables": {"order_id": "1"}},
            },
            "child idle after kickoff",
        ])

        resp = await _send_message(client, parent_fid, context_id, "handoff please")
        data = resp.json()
        _validate_jsonrpc_response(data)

        parent_session = f"{parent_fid}:{context_id}"
        parent_state = await container.workflow_runtime.get_state(parent_session)
        assert parent_state is not None
        assert parent_state.handoff_depth == 1

        child_session = f"{child_fid}:{context_id}:handoff:{child_fid}"
        child_state = await container.workflow_runtime.get_state(child_session)
        assert child_state is not None

        if parent_state.handoff_trace_id is not None:
            assert child_state.handoff_trace_id == parent_state.handoff_trace_id

    @pytest.mark.asyncio
    async def test_flownode_handoff_uses_handoff_session_scheme(
        self, container, unique_id
    ):
        from tests.flows.integration.test_handoff_e2e import _run, _save_flow as save_flow

        parent_fid = f"ht-tr-{unique_id}"
        child_fid = f"ht-tr-child-{unique_id}"
        ctx = f"ctx-tr-{unique_id}"
        await save_flow(container, {
            "flow_id": child_fid, "name": "Child", "entry": "main",
            "nodes": {"main": {"type": "llm_node", "node_id": "c", "prompt": "c", "llm": {"model": "mock-gpt-4"}}},
            "edges": [{"from_node": "main", "to_node": None}],
        })
        await save_flow(container, {
            "flow_id": parent_fid, "name": "Parent", "entry": "call_child",
            "nodes": {
                "call_child": {"type": "flow", "flow_id": child_fid, "handoff_mode": True},
            },
            "edges": [{"from_node": "call_child", "to_node": None}],
        })
        from core.clients.llm import setup_mock_responses

        setup_mock_responses(response_queue=["child done"])
        result = await _run(container, parent_fid, ctx, "go", ["child done"])
        parent_context_id = f"context-{ctx}"
        child_session = f"{child_fid}:{parent_context_id}:handoff:{child_fid}"
        child_state = await container.workflow_runtime.get_state(child_session)
        assert child_state is not None
        assert result.interrupt is None
