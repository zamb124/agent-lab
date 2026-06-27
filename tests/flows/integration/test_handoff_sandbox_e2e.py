"""
E2E тест: handoff из sandbox-кода через capability gateway.
"""

from __future__ import annotations

import pytest

from apps.flows.src.models.flow_config import FlowConfig
from core.clients.llm import setup_mock_responses
from core.state.interrupt import HandoffInterrupt, InterruptKind
from tests.flows.durable_runtime_harness import run_flow, workflow_state

pytestmark = [pytest.mark.timeout(120, func_only=True)]


async def _run(container, flow_id, unique_id, content, mock_responses, **extra):
    setup_mock_responses(response_queue=mock_responses)
    state = workflow_state(flow_id=flow_id, unique_id=unique_id, content=content, **extra)
    flow = await container.flow_factory.get_flow(flow_id)
    return await run_flow(container=container, flow=flow, state=state)


async def _save_flow(container, flow_config):
    return await container.flow_repository.set(FlowConfig.model_validate(flow_config))


class TestHandoffViaSandbox:
    """Handoff через node-as-tool call_type=handoff (контракт wrapper → HandoffInterrupt)."""

    @pytest.mark.asyncio
    async def test_j1_flow_tool_call_type_handoff_raises_interrupt(self, container, unique_id):
        parent_fid = f"ht-sb-{unique_id}"
        child_fid = f"ht-sbc-{unique_id}"

        await _save_flow(container, {
            "flow_id": child_fid, "name": "Child", "entry": "main",
            "nodes": {"main": {"type": "llm_node", "node_id": "c", "prompt": "c", "llm": {"model": "mock-gpt-4"}, "tools": [{"tool_id": "handback_to_parent", "description": "HB"}]}},
            "edges": [{"from_node": "main", "to_node": None}],
        })

        await _save_flow(container, {
            "flow_id": parent_fid, "name": "Parent", "entry": "main",
            "nodes": {
                "main": {
                    "type": "llm_node",
                    "node_id": "p",
                    "prompt": "Handoff via flow tool.",
                    "llm": {"model": "mock-gpt-4"},
                    "tools": [{
                        "tool_id": "child_handoff",
                        "description": "Handoff child",
                        "type": "flow",
                        "flow_id": child_fid,
                        "call_type": "handoff",
                        "parameters_schema": {"type": "object", "properties": {}, "required": []},
                    }],
                }
            },
            "edges": [{"from_node": "main", "to_node": None}],
        })

        result = await _run(container, parent_fid, f"ps-j1-{unique_id}", "handoff", [
            {"type": "tool_call", "tool": "child_handoff", "args": {}},
        ])

        assert result.interrupt is not None
        assert result.interrupt.body.kind == InterruptKind.HANDOFF
        body = result.interrupt.body
        assert isinstance(body, HandoffInterrupt)
        assert body.target_flow_id == child_fid


class TestHandoffViaSandboxCode:
    """CodeNode → capability gateway → handoff_to_flow (требует sandbox_services)."""

    @pytest.mark.asyncio
    async def test_j2_code_node_calls_handoff_via_capability(
        self,
        container,
        unique_id,
        sandbox_services,
        auth_token_system,
        system_user_id,
    ):
        from core.context import set_context
        from core.models.context_models import Context
        from core.models.identity_models import User
        from tests.fixtures.ai_provider_defaults import make_test_company

        _ = sandbox_services
        set_context(
            Context(
                user=User(user_id=system_user_id, name="Handoff sandbox"),
                active_company=make_test_company(company_id="system", name="System"),
                auth_token=auth_token_system,
                channel="test",
                metadata={
                    "user_id": system_user_id,
                    "email": "test@example.com",
                    "grps": [],
                },
            )
        )
        parent_fid = f"ht-sb2-{unique_id}"
        child_fid = f"ht-sbc2-{unique_id}"

        await _save_flow(container, {
            "flow_id": child_fid, "name": "Child", "entry": "main",
            "nodes": {"main": {"type": "llm_node", "node_id": "c", "prompt": "c", "llm": {"model": "mock-gpt-4"}, "tools": [{"tool_id": "handback_to_parent", "description": "HB"}]}},
            "edges": [{"from_node": "main", "to_node": None}],
        })

        handoff_code = (
            "async def run(args, state):\n"
            + f"    await tools.handoff_to_flow(target_flow_id='{child_fid}', reason='sandbox test')\n"
            + "    return {'handoff': 'requested'}\n"
        )

        await _save_flow(container, {
            "flow_id": parent_fid, "name": "Parent", "entry": "main",
            "nodes": {
                "main": {
                    "type": "llm_node",
                    "node_id": "p",
                    "prompt": "Вызови handoff.",
                    "llm": {"model": "mock-gpt-4"},
                    "tools": [{
                        "tool_id": "do_handoff",
                        "description": "Handoff via sandbox",
                        "language": "python",
                        "code": handoff_code,
                        "parameters_schema": {"type": "object", "properties": {}, "required": []},
                    }],
                }
            },
            "edges": [{"from_node": "main", "to_node": None}],
        })

        result = await _run(
            container,
            parent_fid,
            f"ps-j2-{unique_id}",
            "handoff via sandbox",
            [{"type": "tool_call", "tool": "do_handoff", "args": {}}],
            user_id=system_user_id,
        )

        assert result.interrupt is not None
        assert result.interrupt.body.kind == InterruptKind.HANDOFF
        body = result.interrupt.body
        assert isinstance(body, HandoffInterrupt)
        assert body.target_flow_id == child_fid


__all__ = ["TestHandoffViaSandbox", "TestHandoffViaSandboxCode"]
