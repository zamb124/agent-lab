"""
Интеграционные тесты для RemoteFlowNode.
Используется реальный HTTP сервер.
"""

import json

import pytest
from aiohttp import web

from apps.flows.src.models import Edge, FlowConfig
from apps.flows.src.runtime.flow import Flow
from apps.flows.src.runtime.nodes import RemoteFlowNode, create_node
from core.state import ExecutionState
from tests.fixtures.aiohttp_ephemeral import tcp_site_assigned_port


class TestRemoteFlowNode:
    """Тесты RemoteFlowNode."""

    @pytest.fixture
    async def remote_flow_server(self):
        """Тестовый A2A сервер."""
        public = {"base": "http://127.0.0.1:0"}

        async def handle_agent_card(request):
            return web.json_response({
                "name": "Remote Test Agent",
                "url": public["base"],
                "branches": [{"id": "default", "name": "Default"}],
            })

        async def handle_send_task(request):
            data = await request.json()
            content = data["params"]["message"]["parts"][0]["text"]

            return web.json_response({
                "jsonrpc": "2.0",
                "id": data["id"],
                "result": {
                    "status": {"state": "completed"},
                    "artifacts": [
                        {"parts": [{"type": "text", "text": f"Remote says: {content}"}]}
                    ],
                },
            })

        app = web.Application()
        app.router.add_get("/.well-known/agent-card.json", handle_agent_card)
        app.router.add_post("/", handle_send_task)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = tcp_site_assigned_port(site)
        public["base"] = f"http://127.0.0.1:{port}"

        yield public["base"]

        await runner.cleanup()

    @pytest.mark.asyncio
    async def test_create_remote_flow_node(self):
        """Создание RemoteFlowNode через create_node."""
        node_config = {
            "type": "remote_flow",
            "url": "http://example.com:8080",
            "branch_id": "custom",
        }
        node = await create_node("remote_test", node_config)

        assert isinstance(node, RemoteFlowNode)
        assert node.url == "http://example.com:8080"
        assert node.branch_id == "custom"

    @pytest.mark.asyncio
    async def test_create_remote_flow_node_default_skill(self):
        """branch_id по умолчанию = 'default'."""
        node_config = {
            "type": "remote_flow",
            "url": "http://example.com:8080",
        }
        node = await create_node("remote_test", node_config)

        assert node.branch_id == "default"

    @pytest.mark.asyncio
    async def test_remote_flow_node_execution(self, remote_flow_server, container):
        """Выполнение RemoteFlowNode."""
        node = RemoteFlowNode(
            node_id="remote",
            config={"url": remote_flow_server},
            container=container,
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Hello from flow"
        )
        result = await node.run(state)

        assert result["response"] == "Remote says: Hello from flow"
        assert result["remote_status"] == "completed"

    @pytest.mark.asyncio
    async def test_remote_flow_node_preserves_state(self, remote_flow_server, container):
        """RemoteFlowNode сохраняет существующие поля state."""
        node = RemoteFlowNode(
            node_id="remote",
            config={"url": remote_flow_server},
            container=container,
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Test",
            existing_field="preserved",
            counter=42
        )
        result = await node.run(state)

        assert result["existing_field"] == "preserved"
        assert result["counter"] == 42
        assert "response" in result


class TestFlowWithRemoteAgent:
    """Тесты Agent с RemoteFlowNode."""

    @pytest.fixture
    async def remote_flow_server(self):
        """Тестовый A2A сервер."""
        public = {"base": "http://127.0.0.1:0"}

        async def handle_agent_card(request):
            return web.json_response({
                "name": "Agent Remote Agent",
                "url": public["base"],
                "branches": [{"id": "default", "name": "Default"}],
            })

        async def handle_send_task(request):
            data = await request.json()
            content = data["params"]["message"]["parts"][0]["text"]

            return web.json_response({
                "jsonrpc": "2.0",
                "id": data["id"],
                "result": {
                    "status": {"state": "completed"},
                    "artifacts": [
                        {"parts": [{"type": "text", "text": f"Processed: {content}"}]}
                    ],
                },
            })

        app = web.Application()
        app.router.add_get("/.well-known/agent-card.json", handle_agent_card)
        app.router.add_post("/", handle_send_task)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = tcp_site_assigned_port(site)
        public["base"] = f"http://127.0.0.1:{port}"

        yield public["base"]

        await runner.cleanup()

    @pytest.mark.asyncio
    async def test_flow_with_single_remote_node(self, remote_flow_server, container):
        """Agent с одной remote нодой."""
        config = FlowConfig(
            flow_id="remote_flow",
            name="Remote Agent",
            entry="remote",
            nodes={
                "remote": {
                    "type": "remote_flow",
                    "url": remote_flow_server,
                }
            },
            edges=[
                Edge(from_node="remote", to_node=None)
            ]
        )

        flow = await Flow.from_config(
            config={
                "id": config.flow_id,
                "name": config.name,
                "entry": config.entry,
                "nodes": config.nodes,
                "edges": config.edges
            },
            variables={},
            container=container,
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Hello remote"
        )
        result = await flow.run(state)

        assert result["response"] == "Processed: Hello remote"

    @pytest.mark.asyncio
    async def test_flow_with_inline_then_remote(self, remote_flow_server, container):
        """Agent: inline function → remote agent."""
        config = FlowConfig(
            flow_id="mixed_flow",
            name="Mixed Agent",
            entry="prepare",
            nodes={
                "prepare": {
                    "type": "code",
                    "code": """
async def run(state):
    state['content'] = state.get('content', '').upper()
    state['prepared'] = True
    return state
"""
                },
                "remote": {
                    "type": "remote_flow",
                    "url": remote_flow_server,
                }
            },
            edges=[
                Edge(from_node="prepare", to_node="remote"),
                Edge(from_node="remote", to_node=None)
            ]
        )

        flow = await Flow.from_config(
            config={
                "id": config.flow_id,
                "name": config.name,
                "entry": config.entry,
                "nodes": config.nodes,
                "edges": config.edges
            },
            variables={},
            container=container,
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="hello"
        )
        result = await flow.run(state)

        assert result["prepared"] is True
        assert result["response"] == "Processed: HELLO"

    @pytest.mark.asyncio
    async def test_flow_remote_then_inline(self, remote_flow_server, container):
        """Agent: remote agent → inline function."""
        config = FlowConfig(
            flow_id="remote_first_flow",
            name="Remote First",
            entry="remote",
            nodes={
                "remote": {
                    "type": "remote_flow",
                    "url": remote_flow_server,
                },
                "process": {
                    "type": "code",
                    "code": """
async def run(state):
    response = state.get('response', '')
    state['final'] = f"Final: {response}"
    return state
"""
                }
            },
            edges=[
                Edge(from_node="remote", to_node="process"),
                Edge(from_node="process", to_node=None)
            ]
        )

        flow = await Flow.from_config(
            config={
                "id": config.flow_id,
                "name": config.name,
                "entry": config.entry,
                "nodes": config.nodes,
                "edges": config.edges
            },
            variables={},
            container=container,
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="test"
        )
        result = await flow.run(state)

        assert result["final"] == "Final: Processed: test"


class TestRemoteAgentInputMapping:
    """Тесты input_mapping для RemoteFlowNode."""

    @pytest.fixture
    async def mock_a2a_server_with_logging(self):
        """A2A сервер который логирует что получил на вход."""
        received_messages = []
        public = {"base": "http://127.0.0.1:0"}

        async def handle_agent_card(request):
            return web.json_response({
                "name": "Input Logging Agent",
                "url": public["base"],
                "branches": [{"id": "default", "name": "Default"}],
            })

        async def handle_send_task(request):
            data = await request.json()
            content = data["params"]["message"]["parts"][0]["text"]
            received_messages.append(content)

            return web.json_response({
                "jsonrpc": "2.0",
                "id": data["id"],
                "result": {
                    "status": {"state": "completed"},
                    "artifacts": [
                        {"parts": [{"type": "text", "text": f"Received: {content}"}]}
                    ],
                },
            })

        app = web.Application()
        app.router.add_get("/.well-known/agent-card.json", handle_agent_card)
        app.router.add_post("/", handle_send_task)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = tcp_site_assigned_port(site)
        public["base"] = f"http://127.0.0.1:{port}"

        yield {"url": public["base"], "received": received_messages}

        await runner.cleanup()

    @pytest.mark.asyncio
    async def test_input_mapping_content_default(self, mock_a2a_server_with_logging, container):
        """По умолчанию берётся state['content']."""
        server = mock_a2a_server_with_logging
        node = RemoteFlowNode(
            node_id="remote",
            config={"url": server["url"]},
            container=container,
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="default content",
            other_field="ignored"
        )
        await node.run(state)

        assert len(server["received"]) == 1
        assert server["received"][0] == "default content"

    @pytest.mark.asyncio
    async def test_input_mapping_state_field(self, mock_a2a_server_with_logging, container):
        """input_mapping с @state:field берёт указанное поле."""
        server = mock_a2a_server_with_logging
        node = RemoteFlowNode(
            node_id="remote",
            config={
                "url": server["url"],
                "input_mapping": {"content": "@state:my_query"}
            },
            container=container,
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="ignored",
            my_query="custom field value"
        )
        await node.run(state)

        assert len(server["received"]) == 1
        assert server["received"][0] == "custom field value"

    @pytest.mark.asyncio
    async def test_input_mapping_state_field_json(self, mock_a2a_server_with_logging, container):
        """Если поле не строка - сериализуется в JSON."""
        server = mock_a2a_server_with_logging
        node = RemoteFlowNode(
            node_id="remote",
            config={
                "url": server["url"],
                "input_mapping": {"content": "@state:data"}
            },
            container=container,
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="ignored",
            data={"key": "value", "num": 42}
        )
        await node.run(state)

        assert len(server["received"]) == 1
        received_data = json.loads(server["received"][0])
        assert received_data == {"key": "value", "num": 42}

    @pytest.mark.asyncio
    async def test_flow_with_input_mapping(self, mock_a2a_server_with_logging, container):
        """Agent где function пишет в state, а remote_flow читает через input_mapping."""
        server = mock_a2a_server_with_logging

        config = FlowConfig(
            flow_id="input_mapping_flow",
            name="Input Mapping Test",
            entry="prepare",
            nodes={
                "prepare": {
                    "type": "code",
                    "code": """
async def run(state):
    state['prepared_query'] = 'Query from function node'
    return state
"""
                },
                "remote": {
                    "type": "remote_flow",
                    "url": server["url"],
                    "input_mapping": {
                        "content": "@state:prepared_query"
                    }
                }
            },
            edges=[
                Edge(from_node="prepare", to_node="remote"),
                Edge(from_node="remote", to_node=None)
            ]
        )

        flow = await Flow.from_config(
            config={
                "id": config.flow_id,
                "name": config.name,
                "entry": config.entry,
                "nodes": config.nodes,
                "edges": config.edges
            },
            variables={},
            container=container,
        )

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="original content"
        )
        result = await flow.run(state)

        # Проверяем что remote agent получил данные из prepared_query
        assert len(server["received"]) == 1
        assert server["received"][0] == "Query from function node"
        assert result["response"] == "Received: Query from function node"
