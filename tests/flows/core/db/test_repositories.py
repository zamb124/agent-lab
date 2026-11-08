"""
Тесты репозиториев (PostgreSQL).

Используют реальную БД через app fixture.
"""


import pytest

from apps.flows.src.durable_execution import WorkflowEventType
from apps.flows.src.models import (
    CodeMode,
    FlowConfig,
    NodeConfig,
    ToolReference,
)
from apps.flows.src.models.enums import NodeType
from apps.flows.src.state import ExecutionState


class TestNodeRepository:
    """Тесты NodeRepository."""

    @pytest.mark.asyncio
    async def test_set_and_get_node(self, app, di):
        """Сохранение и получение ноды."""

        node = NodeConfig(
            node_id="test_node_repo",
            type=NodeType.LLM_NODE,
            name="Test Node",
            description="For testing",
            prompt="Test prompt",
        )

        await NodeConfig.set(node)
        loaded = await NodeConfig.get(NodeConfig.node_row_id_for_active_company("test_node_repo"))

        assert loaded is not None
        assert loaded.node_id == "test_node_repo"
        assert loaded.name == "Test Node"

        # Cleanup
        await NodeConfig.delete_by_id(NodeConfig.node_row_id_for_active_company("test_node_repo"))

    @pytest.mark.asyncio
    async def test_get_nonexistent_node(self, app, di):
        """Получение несуществующей ноды возвращает None."""

        result = await NodeConfig.get(NodeConfig.node_row_id_for_active_company("nonexistent_node_xyz"))
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_node(self, app, di):
        """Удаление ноды."""

        node = NodeConfig(
            node_id="node_to_delete",
            type=NodeType.LLM_NODE,
            name="Delete Me",
        )
        await NodeConfig.set(node)
        await NodeConfig.delete_by_id(NodeConfig.node_row_id_for_active_company("node_to_delete"))

        result = await NodeConfig.get(NodeConfig.node_row_id_for_active_company("node_to_delete"))
        assert result is None


class TestFlowRepository:
    """Тесты FlowRepository."""

    @pytest.mark.asyncio
    async def test_set_and_get_flow(self, app, di):
        """Сохранение и получение flow."""

        flow = FlowConfig(
            flow_id="test_flow_repo",
            name="Test Agent",
            description="For testing",
            entry="main",
            nodes={
                "main": {
                    "type": "llm_node",
                    "prompt": "Test",
                    "next": None
                }
            },
        )

        await FlowConfig.create_version(flow)
        loaded = await FlowConfig.current_for_flow("test_flow_repo")

        assert loaded is not None
        assert loaded.flow_id == "test_flow_repo"
        nodes = loaded.nodes
        assert nodes is not None
        assert "main" in nodes

        await FlowConfig.delete_by_flow_id("test_flow_repo")

    @pytest.mark.asyncio
    async def test_create_version_dedups_identical_content(self, app, di, unique_id):
        """Запись идентичного содержимого не создаёт новую строку версии; изменение — создаёт."""
        flow_id = f"dedup_{unique_id}"
        base = {
            "flow_id": flow_id,
            "name": "Dedup",
            "entry": "main",
            "nodes": {"main": {"type": "llm_node", "prompt": "Test", "next": None}},
        }
        await FlowConfig.create_version(FlowConfig.model_validate(base))
        try:
            versions_initial = await FlowConfig.list_version_strings_by_version_desc(flow_id)
            assert len(versions_initial) == 1
            first_version = versions_initial[0]

            await FlowConfig.create_version(FlowConfig.model_validate(base))
            versions_after_identical = await FlowConfig.list_version_strings_by_version_desc(
                flow_id
            )
            assert versions_after_identical == [first_version], (
                f"Идентичная запись создала новую версию: {versions_after_identical}"
            )
            current = await FlowConfig.current_for_flow(flow_id)
            assert current is not None
            assert current.version == first_version
            assert current.is_current is True

            changed = dict(base)
            changed["name"] = "Dedup changed"
            await FlowConfig.create_version(FlowConfig.model_validate(changed))
            versions_after_change = await FlowConfig.list_version_strings_by_version_desc(flow_id)
            assert len(versions_after_change) == 2
            assert versions_after_change[0] != first_version
            current_changed = await FlowConfig.current_for_flow(flow_id)
            assert current_changed is not None
            assert current_changed.name == "Dedup changed"
            assert current_changed.is_current is True
        finally:
            await FlowConfig.delete_by_flow_id(flow_id)

    @pytest.mark.asyncio
    async def test_list_all_flows(self, app, di):
        """Получение списка всех flows."""

        flows = await FlowConfig.list(limit=1000)
        assert isinstance(flows, list)


class TestToolRepository:
    """Тесты ToolRepository."""

    @pytest.mark.asyncio
    async def test_set_and_get_tool(self, app, di):
        """Сохранение и получение tool."""

        tool = ToolReference(
            tool_id="test_tool_repo",
            title="Test Tool",
            description="For testing",
            code_mode=CodeMode.INLINE_CODE,
            code="async def run(args, state):\n    return args.get('x', 0) + 1",
        )

        await ToolReference.set(tool)
        loaded = await ToolReference.get(ToolReference.row_id_for_active_company("test_tool_repo"))

        assert loaded is not None
        assert loaded.tool_id == "test_tool_repo"

        await ToolReference.delete_by_id(ToolReference.row_id_for_active_company("test_tool_repo"))


class TestDurableWorkflowRuntime:
    """Тесты durable projection read/write."""

    @pytest.mark.asyncio
    async def test_set_and_get_state(self, app, unique_id, di):
        """Сохранение и получение state."""
        runtime = di.workflow_runtime

        state = ExecutionState(
            task_id=f"test-task-{unique_id}",
            context_id=f"test-context-{unique_id}",
            user_id="test-user",
            session_id=f"test-agent:test-context-{unique_id}",
            content="test",
            messages=[],
        )
        from a2a.types import Message, Part
        from a2a.types.a2a_pb2 import ROLE_USER

        message = Message(
            message_id="test-msg",
            role=ROLE_USER,
            parts=[Part(text="Hello")],
            task_id=f"test-task-{unique_id}"
        )
        state.messages.append(message)

        await runtime.save_state(
            state.session_id,
            state,
            event_type=WorkflowEventType.state_projection_committed,
            snapshot=True,
        )
        loaded = await runtime.get_state(state.session_id)

        assert loaded is not None
        assert loaded.content == "test"
        assert len(loaded.messages) == 1
