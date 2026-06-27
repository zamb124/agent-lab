"""
E2E тесты handoff/handback: все сценарии.
Используем FlowFactory.get_flow() из БД (строковые ссылки на tool_id работают через этот путь).
Flow.from_config() не инлайнит tool-ссылки, поэтому сохраняем flow в БД через flow_repository.set().
"""

from __future__ import annotations

import pytest

from apps.flows.src.models.flow_config import FlowConfig
from core.clients.llm import setup_mock_responses
from core.state.interrupt import HandoffInterrupt, InterruptKind
from core.types import JsonObject
from tests.flows.durable_runtime_harness import run_flow, workflow_state

pytestmark = [pytest.mark.timeout(120, func_only=True)]


async def _run(container, flow_id, unique_id, content, mock_responses, **extra):
    """Создаёт state, настраивает MockLLM, получает flow из flow_factory и запускает."""
    setup_mock_responses(response_queue=mock_responses)
    state = workflow_state(flow_id=flow_id, unique_id=unique_id, content=content, **extra)
    flow = await container.flow_factory.get_flow(flow_id)
    return await run_flow(container=container, flow=flow, state=state)


async def _resume(container, flow_id, unique_id, state, content, mock_responses):
    setup_mock_responses(response_queue=mock_responses)
    state.content = content
    state.interrupt = None
    flow = await container.flow_factory.get_flow(flow_id)
    return await run_flow(container=container, flow=flow, state=state)


def _save_flow(container, flow_config: JsonObject):
    return container.flow_repository.set(FlowConfig.model_validate(flow_config))


# ── Block A: handoff через tool (in-process @tool) ──────────────────────────


class TestHandoffViaTool:
    @pytest.mark.asyncio
    async def test_a1_basic_handoff_interrupt(self, container, unique_id):
        parent_fid = f"ht-a1-{unique_id}"
        child_fid = f"ht-child-{unique_id}"

        await _save_flow(container, {
            "flow_id": parent_fid, "name": "Parent", "entry": "main",
            "nodes": {"main": {"type": "llm_node", "node_id": "p", "prompt": "parent", "llm": {"model": "mock-gpt-4"}, "tools": [{"tool_id": "handoff_to_flow", "description": "Handoff"}]}},
            "edges": [{"from_node": "main", "to_node": None}],
        })
        await _save_flow(container, {
            "flow_id": child_fid, "name": "Child", "entry": "main",
            "nodes": {"main": {"type": "llm_node", "node_id": "c", "prompt": "child", "llm": {"model": "mock-gpt-4"}, "tools": [{"tool_id": "handback_to_parent", "description": "Handback"}]}},
            "edges": [{"from_node": "main", "to_node": None}],
        })

        result = await _run(container, parent_fid, f"ps-a1-{unique_id}", "handoff", [
            {"type": "tool_call", "tool": "handoff_to_flow", "args": {"target_flow_id": child_fid, "variables": {"order_id": "42"}, "reason": "test"}},
        ])
        assert result.interrupt is not None
        assert result.interrupt.body.kind == InterruptKind.HANDOFF
        ha = result.interrupt.body
        assert isinstance(ha, HandoffInterrupt)
        assert ha.target_flow_id == child_fid
        assert ha.variables == {"order_id": "42"}
        assert ha.reason == "test"
        assert result.current_nodes == ["main"]

    @pytest.mark.asyncio
    async def test_a2_variables_passed_to_body(self, container, unique_id):
        parent_fid = f"ht-a2-{unique_id}"
        await _save_flow(container, {
            "flow_id": parent_fid, "name": "P", "entry": "main",
            "nodes": {"main": {"type": "llm_node", "node_id": "p", "prompt": "p", "llm": {"model": "mock-gpt-4"}, "tools": [{"tool_id": "handoff_to_flow", "description": "Handoff"}]}},
            "edges": [{"from_node": "main", "to_node": None}],
        })
        result = await _run(container, parent_fid, f"ps-a2-{unique_id}", "go", [
            {"type": "tool_call", "tool": "handoff_to_flow", "args": {"target_flow_id": "c", "variables": {"x": 1, "y": 2}}},
        ])
        ha = result.interrupt.body
        assert isinstance(ha, HandoffInterrupt)
        assert ha.variables == {"x": 1, "y": 2}

    @pytest.mark.asyncio
    async def test_a3_reason_field(self, container, unique_id):
        parent_fid = f"ht-a3-{unique_id}"
        await _save_flow(container, {
            "flow_id": parent_fid, "name": "P", "entry": "main",
            "nodes": {"main": {"type": "llm_node", "node_id": "p", "prompt": "p", "llm": {"model": "mock-gpt-4"}, "tools": [{"tool_id": "handoff_to_flow", "description": "Handoff"}]}},
            "edges": [{"from_node": "main", "to_node": None}],
        })
        result = await _run(container, parent_fid, f"ps-a3-{unique_id}", "go", [
            {"type": "tool_call", "tool": "handoff_to_flow", "args": {"target_flow_id": "c", "reason": "complaint"}},
        ])
        assert isinstance(result.interrupt.body, HandoffInterrupt)
        assert result.interrupt.body.reason == "complaint"

    @pytest.mark.asyncio
    async def test_a4_empty_variables(self, container, unique_id):
        parent_fid = f"ht-a4-{unique_id}"
        await _save_flow(container, {
            "flow_id": parent_fid, "name": "P", "entry": "main",
            "nodes": {"main": {"type": "llm_node", "node_id": "p", "prompt": "p", "llm": {"model": "mock-gpt-4"}, "tools": [{"tool_id": "handoff_to_flow", "description": "Handoff"}]}},
            "edges": [{"from_node": "main", "to_node": None}],
        })
        result = await _run(container, parent_fid, f"ps-a4-{unique_id}", "go", [
            {"type": "tool_call", "tool": "handoff_to_flow", "args": {"target_flow_id": "c"}},
        ])
        assert isinstance(result.interrupt.body, HandoffInterrupt)
        assert result.interrupt.body.variables == {}

    @pytest.mark.asyncio
    async def test_a5_no_handoff_then_ask_user_is_normal_interrupt(self, container, unique_id):
        """Без handoff ask_user даёт обычный USER_MESSAGE interrupt."""
        parent_fid = f"ht-a5-{unique_id}"
        await _save_flow(container, {
            "flow_id": parent_fid, "name": "P", "entry": "main",
            "nodes": {"main": {"type": "llm_node", "node_id": "p", "prompt": "p", "llm": {"model": "mock-gpt-4"}, "tools": [
                {"tool_id": "ask_user", "description": "Ask"},
            ]}},
            "edges": [{"from_node": "main", "to_node": None}],
        })
        result = await _run(container, parent_fid, f"ps-a5-{unique_id}", "question", [
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "Уточните?"}},
        ])
        assert result.interrupt is not None
        assert result.interrupt.body.kind == InterruptKind.USER_MESSAGE


# ── Block B: FlowNode handoff_mode=true ──────────────────────────────────────


class TestFlowNodeHandoffMode:
    @pytest.mark.asyncio
    async def test_b1_flows_to_next_node(self, container, unique_id):
        parent_fid = f"ht-b1-{unique_id}"
        child_fid = f"ht-child-b1-{unique_id}"
        await _save_flow(container, {
            "flow_id": child_fid, "name": "Child", "entry": "main",
            "nodes": {"main": {"type": "llm_node", "node_id": "c", "prompt": "c", "llm": {"model": "mock-gpt-4"}, "tools": [{"tool_id": "handback_to_parent", "description": "Handback"}]}},
            "edges": [{"from_node": "main", "to_node": None}],
        })
        await _save_flow(container, {
            "flow_id": parent_fid, "name": "Parent", "entry": "start",
            "nodes": {
                "start": {"type": "llm_node", "node_id": "s", "prompt": "start", "llm": {"model": "mock-gpt-4"}, "tools": [{"tool_id": "ask_user", "description": "Ask"}]},
                "call_child": {"type": "flow", "flow_id": child_fid, "handoff_mode": True},
            },
            "edges": [{"from_node": "start", "to_node": "call_child"}, {"from_node": "call_child", "to_node": None}],
        })
        result = await _run(container, parent_fid, f"ps-b1-{unique_id}", "go", [
            "starting child",
        ])
        assert result.interrupt is None

    @pytest.mark.asyncio
    async def test_b2_with_input_mapping(self, container, unique_id):
        parent_fid = f"ht-b2-{unique_id}"
        child_fid = f"ht-child-b2-{unique_id}"
        await _save_flow(container, {
            "flow_id": child_fid, "name": "Child", "entry": "main",
            "nodes": {"main": {"type": "llm_node", "node_id": "c", "prompt": "c", "llm": {"model": "mock-gpt-4"}, "tools": [{"tool_id": "handback_to_parent", "description": "Handback"}]}},
            "edges": [{"from_node": "main", "to_node": None}],
        })
        await _save_flow(container, {
            "flow_id": parent_fid, "name": "Parent", "entry": "call_child",
            "nodes": {
                "call_child": {"type": "flow", "flow_id": child_fid, "handoff_mode": True, "input_mapping": {"order_id": "@state:order_id"}, "output_mapping": {"ticket_id": "created_ticket"}},
            },
            "edges": [{"from_node": "call_child", "to_node": None}],
        })
        result = await _run(container, parent_fid, f"ps-b2-{unique_id}", "go", [], order_id="42")
        assert result.interrupt is None


# ── Block C: NodeAsToolWrapper ───────────────────────────────────────────────


class TestWrapperCallTypeHandoff:
    @pytest.mark.asyncio
    async def test_c1_builtin_handoff_tool_works(self, container, unique_id):
        parent_fid = f"ht-c1-{unique_id}"
        await _save_flow(container, {
            "flow_id": parent_fid, "name": "P", "entry": "main",
            "nodes": {"main": {"type": "llm_node", "node_id": "p", "prompt": "p", "llm": {"model": "mock-gpt-4"}, "tools": [{"tool_id": "handoff_to_flow", "description": "Handoff"}]}},
            "edges": [{"from_node": "main", "to_node": None}],
        })
        result = await _run(container, parent_fid, f"ps-c1-{unique_id}", "delegate", [
            {"type": "tool_call", "tool": "handoff_to_flow", "args": {"target_flow_id": "t", "variables": {}}},
        ])
        assert result.interrupt is not None
        assert result.interrupt.body.kind == InterruptKind.HANDOFF

    @pytest.mark.asyncio
    async def test_c2_normal_flow_completes(self, container, unique_id):
        parent_fid = f"ht-c2-{unique_id}"
        await _save_flow(container, {
            "flow_id": parent_fid, "name": "P", "entry": "main",
            "nodes": {"main": {"type": "llm_node", "node_id": "p", "prompt": "p", "llm": {"model": "mock-gpt-4"}, "tools": [{"tool_id": "calculator", "description": "Calc"}]}},
            "edges": [{"from_node": "main", "to_node": None}],
        })
        result = await _run(container, parent_fid, f"ps-c2-{unique_id}", "2+2", [
            {"type": "tool_call", "tool": "calculator", "args": {"expression": "2+2"}},
            "Result is 4",
        ])
        assert result.response is not None


# ── Block D: цепочка ────────────────────────────────────────────────────────


class TestHandoffChain:
    @pytest.mark.asyncio
    async def test_d1_two_level_chain(self, container, unique_id):
        fid_a = f"ht-ca-{unique_id}"
        fid_b = f"ht-cb-{unique_id}"
        fid_c = f"ht-cc-{unique_id}"

        for fid, tools in [
            (fid_a, [{"tool_id": "handoff_to_flow", "description": "H"}]),
            (fid_b, [{"tool_id": "handoff_to_flow", "description": "H"}, {"tool_id": "handback_to_parent", "description": "HB"}]),
            (fid_c, [{"tool_id": "handback_to_parent", "description": "HB"}]),
        ]:
            await _save_flow(container, {
                "flow_id": fid, "name": fid, "entry": "main",
                "nodes": {"main": {"type": "llm_node", "node_id": fid, "prompt": fid, "llm": {"model": "mock-gpt-4"}, "tools": tools}},
                "edges": [{"from_node": "main", "to_node": None}],
            })

        ra = await _run(container, fid_a, f"sa-{unique_id}", "start", [
            {"type": "tool_call", "tool": "handoff_to_flow", "args": {"target_flow_id": fid_b, "variables": {"x": 1}}},
        ])
        assert ra.interrupt is not None
        ha = ra.interrupt.body
        assert isinstance(ha, HandoffInterrupt)
        assert ha.target_flow_id == fid_b
        assert ha.variables == {"x": 1}

        rb = await _run(container, fid_b, f"sb-{unique_id}", "from A", [
            {"type": "tool_call", "tool": "handoff_to_flow", "args": {"target_flow_id": fid_c, "variables": {"y": 2}}},
        ], **ha.variables)
        assert rb.interrupt is not None
        hb = rb.interrupt.body
        assert isinstance(hb, HandoffInterrupt)
        assert hb.target_flow_id == fid_c

        rc = await _run(container, fid_c, f"sc-{unique_id}", "from B", [
            {"type": "tool_call", "tool": "handback_to_parent", "args": {"response": "C done", "variables": {"z": 3}}},
            "result",
        ], **{"x": 1, "y": 2})
        assert rc.response is not None


# ── Block E: изоляция variables ──────────────────────────────────────────────


class TestVariablesIsolation:
    @pytest.mark.asyncio
    async def test_e1_empty_vars_no_leak(self, container, unique_id):
        parent_fid = f"ht-e1-{unique_id}"
        await _save_flow(container, {
            "flow_id": parent_fid, "name": "P", "entry": "main",
            "nodes": {"main": {"type": "llm_node", "node_id": "p", "prompt": "p", "llm": {"model": "mock-gpt-4"}, "tools": [{"tool_id": "handoff_to_flow", "description": "Handoff"}]}},
            "edges": [{"from_node": "main", "to_node": None}],
        })
        result = await _run(container, parent_fid, f"ps-e1-{unique_id}", "go", [
            {"type": "tool_call", "tool": "handoff_to_flow", "args": {"target_flow_id": "c", "variables": {}}},
        ], variables={"secret": "parent-only"})
        ha = result.interrupt.body
        assert isinstance(ha, HandoffInterrupt)
        assert ha.variables == {}
        assert result.variables["secret"] == "parent-only"

    @pytest.mark.asyncio
    async def test_e2_only_explicit_vars_in_body(self, container, unique_id):
        parent_fid = f"ht-e2-{unique_id}"
        await _save_flow(container, {
            "flow_id": parent_fid, "name": "P", "entry": "main",
            "nodes": {"main": {"type": "llm_node", "node_id": "p", "prompt": "p", "llm": {"model": "mock-gpt-4"}, "tools": [{"tool_id": "handoff_to_flow", "description": "Handoff"}]}},
            "edges": [{"from_node": "main", "to_node": None}],
        })
        result = await _run(container, parent_fid, f"ps-e2-{unique_id}", "go", [
            {"type": "tool_call", "tool": "handoff_to_flow", "args": {"target_flow_id": "c", "variables": {"k1": "v1"}}},
        ], variables={"k1": "ignored", "k2": "v2"})
        ha = result.interrupt.body
        assert isinstance(ha, HandoffInterrupt)
        assert ha.variables == {"k1": "v1"}
        assert result.variables["k2"] == "v2"


# ── Block F: граничные случаи ───────────────────────────────────────────────


class TestHandoffEdgeCases:
    @pytest.mark.asyncio
    async def test_f1_all_fields_set(self, container, unique_id):
        parent_fid = f"ht-f1-{unique_id}"
        await _save_flow(container, {
            "flow_id": parent_fid, "name": "P", "entry": "main",
            "nodes": {"main": {"type": "llm_node", "node_id": "p", "prompt": "p", "llm": {"model": "mock-gpt-4"}, "tools": [{"tool_id": "handoff_to_flow", "description": "Handoff"}]}},
            "edges": [{"from_node": "main", "to_node": None}],
        })
        result = await _run(container, parent_fid, f"ps-f1-{unique_id}", "go", [
            {"type": "tool_call", "tool": "handoff_to_flow", "args": {"target_flow_id": "nonexistent", "variables": {"t": "v"}}},
        ])
        ha = result.interrupt.body
        assert isinstance(ha, HandoffInterrupt)
        assert ha.kind == InterruptKind.HANDOFF
        assert ha.target_flow_id == "nonexistent"
        assert ha.target_branch_id == "default"
        assert ha.target_name == "nonexistent"

    @pytest.mark.asyncio
    async def test_f2_child_no_handback_parent_preserved(self, container, unique_id):
        parent_fid = f"ht-f2-{unique_id}"
        child_fid = f"ht-f2c-{unique_id}"
        await _save_flow(container, {
            "flow_id": parent_fid, "name": "P", "entry": "main",
            "nodes": {"main": {"type": "llm_node", "node_id": "p", "prompt": "p", "llm": {"model": "mock-gpt-4"}, "tools": [
                {"tool_id": "handoff_to_flow", "description": "Handoff"}, {"tool_id": "ask_user", "description": "Ask"}]}},
            "edges": [{"from_node": "main", "to_node": None}],
        })
        await _save_flow(container, {
            "flow_id": child_fid, "name": "C", "entry": "main",
            "nodes": {"main": {"type": "llm_node", "node_id": "c", "prompt": "c", "llm": {"model": "mock-gpt-4"}, "tools": [{"tool_id": "finish", "description": "Finish"}]}},
            "edges": [{"from_node": "main", "to_node": None}],
        })
        parent_result = await _run(container, parent_fid, f"ps-f2-{unique_id}", "handoff", [
            {"type": "tool_call", "tool": "handoff_to_flow", "args": {"target_flow_id": child_fid, "variables": {}}},
        ])
        assert parent_result.interrupt is not None
        assert parent_result.interrupt.body.kind == InterruptKind.HANDOFF

        child_result = await _run(container, child_fid, f"cs-f2-{unique_id}", "start", [
            "child finished normally",
        ])
        assert child_result.response is not None

    @pytest.mark.asyncio
    async def test_f3_parent_vars_not_modified_without_handback(self, container, unique_id):
        parent_fid = f"ht-f3-{unique_id}"
        await _save_flow(container, {
            "flow_id": parent_fid, "name": "P", "entry": "main",
            "nodes": {"main": {"type": "llm_node", "node_id": "p", "prompt": "p", "llm": {"model": "mock-gpt-4"}, "tools": [
                {"tool_id": "handoff_to_flow", "description": "Handoff"}, {"tool_id": "ask_user", "description": "Ask"}]}},
            "edges": [{"from_node": "main", "to_node": None}],
        })
        result = await _run(container, parent_fid, f"ps-f3-{unique_id}", "go", [
            {"type": "tool_call", "tool": "handoff_to_flow", "args": {"target_flow_id": "c", "variables": {}}},
        ], variables={"original": "stays"})
        assert result.interrupt is not None
        assert result.variables["original"] == "stays"


__all__ = [
    "TestHandoffViaTool",
    "TestFlowNodeHandoffMode",
    "TestWrapperCallTypeHandoff",
    "TestHandoffChain",
    "TestVariablesIsolation",
    "TestHandoffEdgeCases",
    "TestHandoffChainWithAskUser",
    "TestFlowNodeHandoffDeep",
    "TestWrapperAndBoundaryCases",
]


# ── Block G: цепочки с ask_user и variables ──────────────────────────────────


class TestHandoffChainWithAskUser:
    """Цепочки handoff с ask_user: прерывание, resume, передача управления."""

    @pytest.mark.asyncio
    async def test_g1_chain_with_ask_user_in_middle(self, container, unique_id):
        """A→B, B спрашивает пользователя, затем handoff в C, C handback."""
        fid_a = f"ht-g1a-{unique_id}"
        fid_b = f"ht-g1b-{unique_id}"
        fid_c = f"ht-g1c-{unique_id}"

        for fid, tools in [
            (fid_a, [{"tool_id": "handoff_to_flow", "description": "H"}, {"tool_id": "ask_user", "description": "Ask"}]),
            (fid_b, [{"tool_id": "handoff_to_flow", "description": "H"}, {"tool_id": "handback_to_parent", "description": "HB"}, {"tool_id": "ask_user", "description": "Ask"}]),
            (fid_c, [{"tool_id": "handback_to_parent", "description": "HB"}]),
        ]:
            await _save_flow(container, {
                "flow_id": fid, "name": fid, "entry": "main",
                "nodes": {"main": {"type": "llm_node", "node_id": fid, "prompt": fid, "llm": {"model": "mock-gpt-4"}, "tools": tools}},
                "edges": [{"from_node": "main", "to_node": None}],
            })

        # A спрашивает пользователя
        ra = await _run(container, fid_a, f"sa-g1-{unique_id}", "start", [
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "В чём проблема?"}},
        ])
        assert ra.interrupt is not None
        assert ra.interrupt.body.kind == InterruptKind.USER_MESSAGE

        # пользователь отвечает, A handoff в B
        ra.content = "проблема с курьером"
        ra.interrupt = None
        ra = await _run(container, fid_a, f"sa-g1b-{unique_id}", "resume", [
            {"type": "tool_call", "tool": "handoff_to_flow", "args": {"target_flow_id": fid_b, "variables": {}}},
        ])
        assert ra.interrupt is not None
        assert ra.interrupt.body.kind == InterruptKind.HANDOFF

        # B спрашивает пользователя
        rb = await _run(container, fid_b, f"sb-g1-{unique_id}", "from A", [
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "Номер заказа?"}},
        ])
        assert rb.interrupt is not None
        assert rb.interrupt.body.kind == InterruptKind.USER_MESSAGE

        # пользователь отвечает, B handoff в C
        rb.content = "42"
        rb.interrupt = None
        rb = await _run(container, fid_b, f"sb-g1c-{unique_id}", "resume", [
            {"type": "tool_call", "tool": "handoff_to_flow", "args": {"target_flow_id": fid_c, "variables": {"order_id": "42"}}},
        ])
        assert rb.interrupt is not None
        assert rb.interrupt.body.kind == InterruptKind.HANDOFF

        # C handback в B
        rc = await _run(container, fid_c, f"sc-g1-{unique_id}", "from B", [
            {"type": "tool_call", "tool": "handback_to_parent", "args": {"response": "C done", "variables": {"z": 3}}},
            "result",
        ], **{"order_id": "42"})
        assert rc.response is not None

    @pytest.mark.asyncio
    async def test_g2_chain_variables_cascade(self, container, unique_id):
        """Цепочка с переменными на каждом уровне: A→B(x=1), B→C(y=2), C→B(z=3), B→A(w=4)."""
        fid_a = f"ht-g2a-{unique_id}"
        fid_b = f"ht-g2b-{unique_id}"
        fid_c = f"ht-g2c-{unique_id}"

        for fid, tools in [
            (fid_a, [{"tool_id": "handoff_to_flow", "description": "H"}]),
            (fid_b, [{"tool_id": "handoff_to_flow", "description": "H"}, {"tool_id": "handback_to_parent", "description": "HB"}]),
            (fid_c, [{"tool_id": "handback_to_parent", "description": "HB"}]),
        ]:
            await _save_flow(container, {
                "flow_id": fid, "name": fid, "entry": "main",
                "nodes": {"main": {"type": "llm_node", "node_id": fid, "prompt": fid, "llm": {"model": "mock-gpt-4"}, "tools": tools}},
                "edges": [{"from_node": "main", "to_node": None}],
            })

        ra = await _run(container, fid_a, f"sa-g2-{unique_id}", "start", [
            {"type": "tool_call", "tool": "handoff_to_flow", "args": {"target_flow_id": fid_b, "variables": {"x": 1}}},
        ])
        ha = ra.interrupt.body
        assert isinstance(ha, HandoffInterrupt)
        assert ha.variables == {"x": 1}

        rb = await _run(container, fid_b, f"sb-g2-{unique_id}", "from A", [
            {"type": "tool_call", "tool": "handoff_to_flow", "args": {"target_flow_id": fid_c, "variables": {"y": 2}}},
        ], **ha.variables)
        hb = rb.interrupt.body
        assert isinstance(hb, HandoffInterrupt)
        assert hb.variables == {"y": 2}

        rc = await _run(container, fid_c, f"sc-g2-{unique_id}", "from B", [
            {"type": "tool_call", "tool": "handback_to_parent", "args": {"response": "C done", "variables": {"z": 3}}},
            "result",
        ], **{"x": 1, "y": 2})
        assert rc.response is not None

        rb.interrupt = None
        rb.content = "handback from C"
        rb.variables["z"] = 3
        rb_final = await _run(container, fid_b, f"sb-g2b-{unique_id}", "resume", [
            {"type": "tool_call", "tool": "handback_to_parent", "args": {"response": "B done", "variables": {"w": 4}}},
            "result",
        ])
        assert rb_final.response is not None

        ra.interrupt = None
        ra.content = "handback from B"
        ra.variables["w"] = 4
        ra_final = await _run(container, fid_a, f"sa-g2b-{unique_id}", "resume", [
            "A done",
        ])
        assert ra_final.response is not None

    @pytest.mark.asyncio
    async def test_g3_three_level_chain_with_ask_user_on_last(self, container, unique_id):
        """A→B→C, C: ask_user → resume → handback→B→A."""
        fid_a = f"ht-g3a-{unique_id}"
        fid_b = f"ht-g3b-{unique_id}"
        fid_c = f"ht-g3c-{unique_id}"

        for fid, tools in [
            (fid_a, [{"tool_id": "handoff_to_flow", "description": "H"}]),
            (fid_b, [{"tool_id": "handoff_to_flow", "description": "H"}, {"tool_id": "handback_to_parent", "description": "HB"}]),
            (fid_c, [{"tool_id": "handback_to_parent", "description": "HB"}, {"tool_id": "ask_user", "description": "Ask"}]),
        ]:
            await _save_flow(container, {
                "flow_id": fid, "name": fid, "entry": "main",
                "nodes": {"main": {"type": "llm_node", "node_id": fid, "prompt": fid, "llm": {"model": "mock-gpt-4"}, "tools": tools}},
                "edges": [{"from_node": "main", "to_node": None}],
            })

        ra = await _run(container, fid_a, f"sa-g3-{unique_id}", "start", [
            {"type": "tool_call", "tool": "handoff_to_flow", "args": {"target_flow_id": fid_b, "variables": {}}},
        ])
        assert ra.interrupt is not None

        rb = await _run(container, fid_b, f"sb-g3-{unique_id}", "from A", [
            {"type": "tool_call", "tool": "handoff_to_flow", "args": {"target_flow_id": fid_c, "variables": {}}},
        ])
        assert rb.interrupt is not None

        rc = await _run(container, fid_c, f"sc-g3-{unique_id}", "from B", [
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "Подтвердите?"}},
        ])
        assert rc.interrupt is not None
        assert rc.interrupt.body.kind == InterruptKind.USER_MESSAGE

        rc_resumed = await _resume(container, fid_c, f"sc-g3b-{unique_id}", rc, "да", [
            {"type": "tool_call", "tool": "handback_to_parent", "args": {"response": "C done", "variables": {"z": 3}}},
            "result",
        ])
        assert rc_resumed.response is not None

    @pytest.mark.asyncio
    async def test_g4_parent_handoff_child_ask_user_resume_handback(self, container, unique_id):
        """Parent handoff, child спрашивает, пользователь отвечает, child handback, parent продолжает."""
        fid_a = f"ht-g4a-{unique_id}"
        fid_b = f"ht-g4b-{unique_id}"

        await _save_flow(container, {
            "flow_id": fid_a, "name": "A", "entry": "main",
            "nodes": {"main": {"type": "llm_node", "node_id": "a", "prompt": "A", "llm": {"model": "mock-gpt-4"}, "tools": [
                {"tool_id": "handoff_to_flow", "description": "H"}, {"tool_id": "ask_user", "description": "Ask"}]}},
            "edges": [{"from_node": "main", "to_node": None}],
        })
        await _save_flow(container, {
            "flow_id": fid_b, "name": "B", "entry": "main",
            "nodes": {"main": {"type": "llm_node", "node_id": "b", "prompt": "B", "llm": {"model": "mock-gpt-4"}, "tools": [
                {"tool_id": "handback_to_parent", "description": "HB"}, {"tool_id": "ask_user", "description": "Ask"}]}},
            "edges": [{"from_node": "main", "to_node": None}],
        })

        ra = await _run(container, fid_a, f"sa-g4-{unique_id}", "start", [
            {"type": "tool_call", "tool": "handoff_to_flow", "args": {"target_flow_id": fid_b, "variables": {}}},
        ])
        assert ra.interrupt is not None
        assert ra.interrupt.body.kind == InterruptKind.HANDOFF

        rb = await _run(container, fid_b, f"sb-g4-{unique_id}", "from A", [
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "Номер?"}},
        ])
        assert rb.interrupt is not None
        assert rb.interrupt.body.kind == InterruptKind.USER_MESSAGE

        rb_resumed = await _resume(container, fid_b, f"sb-g4b-{unique_id}", rb, "42", [
            {"type": "tool_call", "tool": "handback_to_parent", "args": {"response": "B done", "variables": {"ticket_id": "TKT-1"}}},
            "result",
        ])
        assert rb_resumed.response is not None

        ra.interrupt = None
        ra.content = "handback from B"
        ra.variables["ticket_id"] = "TKT-1"
        ra_final = await _run(container, fid_a, f"sa-g4b-{unique_id}", "resume", [
            "A resumed successfully",
        ])
        assert ra_final.response is not None


# ── Block H: FlowNode углублённо ─────────────────────────────────────────────


class TestFlowNodeHandoffDeep:
    """Углублённые тесты FlowNode с handoff_mode: child interrupt, output_mapping, без handback."""

    @pytest.mark.asyncio
    async def test_h1_flow_node_handoff_child_ask_user_handback(self, container, unique_id):
        """FlowNode handoff_mode: child ask_user, resume, handback — parent переходит по графу."""
        parent_fid = f"ht-h1-{unique_id}"
        child_fid = f"ht-h1c-{unique_id}"

        await _save_flow(container, {
            "flow_id": child_fid, "name": "Child", "entry": "main",
            "nodes": {"main": {"type": "llm_node", "node_id": "c", "prompt": "c", "llm": {"model": "mock-gpt-4"}, "tools": [
                {"tool_id": "handback_to_parent", "description": "HB"}, {"tool_id": "ask_user", "description": "Ask"}]}},
            "edges": [{"from_node": "main", "to_node": None}],
        })
        await _save_flow(container, {
            "flow_id": parent_fid, "name": "Parent", "entry": "start",
            "nodes": {
                "start": {"type": "llm_node", "node_id": "s", "prompt": "s", "llm": {"model": "mock-gpt-4"}, "tools": [{"tool_id": "ask_user", "description": "Ask"}]},
                "call_child": {"type": "flow", "flow_id": child_fid, "handoff_mode": True},
                "after": {"type": "llm_node", "node_id": "after", "prompt": "after", "llm": {"model": "mock-gpt-4"}, "tools": [{"tool_id": "ask_user", "description": "Ask"}]},
            },
            "edges": [
                {"from_node": "start", "to_node": "call_child"},
                {"from_node": "call_child", "to_node": "after"},
                {"from_node": "after", "to_node": None},
            ],
        })

        result = await _run(container, parent_fid, f"ps-h1-{unique_id}", "go", [
            "starting child flow",
        ])
        assert result.interrupt is None

    @pytest.mark.asyncio
    async def test_h2_flow_node_output_mapping_after_handback(self, container, unique_id):
        """FlowNode handoff_mode: child handback с ticket_id мапится через output_mapping."""
        parent_fid = f"ht-h2-{unique_id}"
        child_fid = f"ht-h2c-{unique_id}"

        await _save_flow(container, {
            "flow_id": child_fid, "name": "Child", "entry": "main",
            "nodes": {"main": {"type": "llm_node", "node_id": "c", "prompt": "c", "llm": {"model": "mock-gpt-4"}, "tools": [{"tool_id": "handback_to_parent", "description": "HB"}]}},
            "edges": [{"from_node": "main", "to_node": None}],
        })
        await _save_flow(container, {
            "flow_id": parent_fid, "name": "Parent", "entry": "call_child",
            "nodes": {
                "call_child": {
                    "type": "flow", "flow_id": child_fid, "handoff_mode": True,
                    "input_mapping": {"order_id": "@state:order_id"},
                    "output_mapping": {"ticket_id": "created_ticket"},
                },
            },
            "edges": [{"from_node": "call_child", "to_node": None}],
        })

        result = await _run(container, parent_fid, f"ps-h2-{unique_id}", "go", [], order_id="42")
        assert result.interrupt is None

    @pytest.mark.asyncio
    async def test_h3_child_without_handback_in_flow_node(self, container, unique_id):
        """FlowNode handoff_mode: child завершается без handback, parent state сохраняется."""
        parent_fid = f"ht-h3-{unique_id}"
        child_fid = f"ht-h3c-{unique_id}"

        await _save_flow(container, {
            "flow_id": child_fid, "name": "Child", "entry": "main",
            "nodes": {"main": {"type": "llm_node", "node_id": "c", "prompt": "c", "llm": {"model": "mock-gpt-4"}, "tools": [{"tool_id": "finish", "description": "Finish"}]}},
            "edges": [{"from_node": "main", "to_node": None}],
        })
        await _save_flow(container, {
            "flow_id": parent_fid, "name": "Parent", "entry": "call_child",
            "nodes": {
                "call_child": {"type": "flow", "flow_id": child_fid, "handoff_mode": True},
            },
            "edges": [{"from_node": "call_child", "to_node": None}],
        })

        result = await _run(container, parent_fid, f"ps-h3-{unique_id}", "go", [], variables={"protected": "stays"})
        assert result.interrupt is None


# ── Block I: NodeAsToolWrapper и граничные случаи ────────────────────────────


class TestWrapperAndBoundaryCases:
    """NodeAsToolWrapper с call_type, отмена, разнотипные variables."""

    @pytest.mark.asyncio
    async def test_i1_wrapper_with_call_type_handoff(self, container, unique_id):
        """NodeAsToolWrapper с call_type='handoff' бросает HandoffInterrupt."""
        parent_fid = f"ht-i1-{unique_id}"
        child_fid = f"ht-i1c-{unique_id}"

        await _save_flow(container, {
            "flow_id": child_fid, "name": "Child", "entry": "main",
            "nodes": {"main": {"type": "llm_node", "node_id": "c", "prompt": "c", "llm": {"model": "mock-gpt-4"}, "tools": [{"tool_id": "handback_to_parent", "description": "HB"}]}},
            "edges": [{"from_node": "main", "to_node": None}],
        })
        await _save_flow(container, {
            "flow_id": parent_fid, "name": "Parent", "entry": "main",
            "nodes": {"main": {"type": "llm_node", "node_id": "p", "prompt": "p", "llm": {"model": "mock-gpt-4"}, "tools": [
                {
                    "tool_id": "child_handoff", "description": "Child handoff",
                    "type": "flow", "flow_id": child_fid, "call_type": "handoff", "code": "",
                    "parameters_schema": {"type": "object", "properties": {}, "required": []},
                },
            ]}},
            "edges": [{"from_node": "main", "to_node": None}],
        })

        result = await _run(container, parent_fid, f"ps-i1-{unique_id}", "go", [
            {"type": "tool_call", "tool": "child_handoff", "args": {}},
        ])
        assert result.interrupt is not None
        assert result.interrupt.body.kind == InterruptKind.HANDOFF
        assert isinstance(result.interrupt.body, HandoffInterrupt)
        assert result.interrupt.body.target_flow_id == child_fid

    @pytest.mark.asyncio
    async def test_i2_handoff_preserves_parent_state_on_cancel(self, container, unique_id):
        """Handoff: parent state сохраняется при любом исходе."""
        parent_fid = f"ht-i2-{unique_id}"
        await _save_flow(container, {
            "flow_id": parent_fid, "name": "P", "entry": "main",
            "nodes": {"main": {"type": "llm_node", "node_id": "p", "prompt": "p", "llm": {"model": "mock-gpt-4"}, "tools": [
                {"tool_id": "handoff_to_flow", "description": "H"}, {"tool_id": "ask_user", "description": "Ask"}]}},
            "edges": [{"from_node": "main", "to_node": None}],
        })

        result = await _run(container, parent_fid, f"ps-i2-{unique_id}", "go", [
            {"type": "tool_call", "tool": "handoff_to_flow", "args": {"target_flow_id": "child", "variables": {}}},
        ], variables={"original": "kept"})
        assert result.interrupt is not None
        assert result.variables["original"] == "kept"

    @pytest.mark.asyncio
    async def test_i3_handoff_with_diverse_variable_types(self, container, unique_id):
        """Handoff с разнотипными variables: str, int, bool, list, nested dict."""
        parent_fid = f"ht-i3-{unique_id}"
        await _save_flow(container, {
            "flow_id": parent_fid, "name": "P", "entry": "main",
            "nodes": {"main": {"type": "llm_node", "node_id": "p", "prompt": "p", "llm": {"model": "mock-gpt-4"}, "tools": [{"tool_id": "handoff_to_flow", "description": "H"}]}},
            "edges": [{"from_node": "main", "to_node": None}],
        })

        complex_vars = {
            "name": "test",
            "count": 42,
            "active": True,
            "tags": ["urgent", "vip"],
            "metadata": {"source": "api", "version": 2},
        }
        result = await _run(container, parent_fid, f"ps-i3-{unique_id}", "go", [
            {"type": "tool_call", "tool": "handoff_to_flow", "args": {"target_flow_id": "c", "variables": complex_vars}},
        ])
        ha = result.interrupt.body
        assert isinstance(ha, HandoffInterrupt)
        assert ha.variables == complex_vars


# ── Block L: многократный handoff/handback in-process ───────────────────────


class TestHandoffMultiCycleInProcess:
    """Повторные циклы handoff→child→handback в одной parent-сессии без channel layer."""

    @pytest.mark.asyncio
    async def test_l6_two_cycles_same_child_in_process(self, container, unique_id):
        parent_fid = f"ht-l6p-{unique_id}"
        child_fid = f"ht-l6c-{unique_id}"
        run_id = f"ctx-l6-{unique_id}"
        orchestrator = container.handoff_orchestrator_service

        await _save_flow(container, {
            "flow_id": parent_fid, "name": "Parent", "entry": "main",
            "nodes": {"main": {"type": "llm_node", "node_id": "p", "prompt": "p", "llm": {"model": "mock-gpt-4"}, "tools": [
                {"tool_id": "handoff_to_flow", "description": "H"}, {"tool_id": "ask_user", "description": "Ask"}]}},
            "edges": [{"from_node": "main", "to_node": None}],
        })
        await _save_flow(container, {
            "flow_id": child_fid, "name": "Child", "entry": "main",
            "nodes": {"main": {"type": "llm_node", "node_id": "c", "prompt": "c", "llm": {"model": "mock-gpt-4"}, "tools": [
                {"tool_id": "handback_to_parent", "description": "HB"}]}},
            "edges": [{"from_node": "main", "to_node": None}],
        })

        parent = await _run(container, parent_fid, run_id, "cycle 1", [
            {"type": "tool_call", "tool": "handoff_to_flow", "args": {
                "target_flow_id": child_fid, "variables": {"cycle": 1},
            }},
        ])
        assert parent.interrupt is not None
        assert parent.interrupt.body.kind == InterruptKind.HANDOFF

        child_context_id, child_session_id = orchestrator.build_child_session_ids(
            parent.context_id, child_fid
        )
        child_run_id = child_context_id.removeprefix("context-")

        child1 = await _run(container, child_fid, child_run_id, "from parent cycle 1", [
            {"type": "tool_call", "tool": "handback_to_parent", "args": {
                "response": "done 1", "variables": {"cycle": 1, "result": "r1"},
            }},
            "child cycle 1 done",
        ], **parent.interrupt.body.variables)
        assert child1.response is not None
        messages_after_cycle1 = len(child1.messages)

        parent.interrupt = None
        parent.content = "resume after cycle 1"
        parent = await _run(container, parent_fid, run_id, "cycle 2 handoff", [
            {"type": "tool_call", "tool": "handoff_to_flow", "args": {
                "target_flow_id": child_fid, "variables": {"cycle": 2},
            }},
        ])
        assert parent.interrupt is not None
        assert parent.interrupt.body.kind == InterruptKind.HANDOFF

        child2 = await _run(container, child_fid, child_run_id, "from parent cycle 2", [
            {"type": "tool_call", "tool": "handback_to_parent", "args": {
                "response": "done 2", "variables": {"cycle": 2, "result": "r2"},
            }},
            "child cycle 2 done",
        ], **parent.interrupt.body.variables)
        assert child2.response is not None
        assert len(child2.messages) >= messages_after_cycle1
        assert child2.variables.get("result") == "r2"

        parent.interrupt = None
        parent.content = "resume after cycle 2"
        parent_final = await _run(container, parent_fid, run_id, "parent finished", [
            "parent after two cycles",
        ])
        assert parent_final.response is not None

        child_state = await container.workflow_runtime.get_state(child_session_id)
        assert child_state is not None
        assert len(child_state.messages) >= 2