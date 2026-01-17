"""
Интеграционные тесты для RemoteAgentNode.
Используется реальный HTTP сервер.
"""

import pytest
from aiohttp import web

from apps.agents.src.agent import Agent
from apps.agents.src.agent.nodes import create_node, RemoteAgentNode
from apps.agents.src.models import AgentConfig, Edge
from core.state import ExecutionState


class TestRemoteAgentNode:
    """Тесты RemoteAgentNode."""

    @pytest.fixture
    async def remote_agent_server(self):
        """Тестовый A2A сервер."""

        async def handle_agent_card(request):
            return web.json_response({
                "name": "Remote Test Agent",
                "url": "http://localhost:9997",
                "skills": [{"id": "default", "name": "Default"}],
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
        site = web.TCPSite(runner, "localhost", 9997)
        await site.start()

        yield "http://localhost:9997"

        await runner.cleanup()

    @pytest.mark.asyncio
    async def test_create_remote_agent_node(self):
        """Создание RemoteAgentNode через create_node."""
        node_config = {
            "type": "remote_agent",
            "url": "http://example.com:8080",
            "skill_id": "custom",
        }
        node = await create_node("remote_test", node_config)

        assert isinstance(node, RemoteAgentNode)
        assert node.url == "http://example.com:8080"
        assert node.skill_id == "custom"

    @pytest.mark.asyncio
    async def test_create_remote_agent_node_default_skill(self):
        """skill_id по умолчанию = 'default'."""
        node_config = {
            "type": "remote_agent",
            "url": "http://example.com:8080",
        }
        node = await create_node("remote_test", node_config)

        assert node.skill_id == "default"

    @pytest.mark.asyncio
    async def test_remote_agent_node_execution(self, remote_agent_server):
        """Выполнение RemoteAgentNode."""
        node = RemoteAgentNode(
            node_id="remote",
            config={"url": remote_agent_server},
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
    async def test_remote_agent_node_preserves_state(self, remote_agent_server):
        """RemoteAgentNode сохраняет существующие поля state."""
        node = RemoteAgentNode(
            node_id="remote",
            config={"url": remote_agent_server},
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
    """Тесты Agent с RemoteAgentNode."""

    @pytest.fixture
    async def remote_agent_server(self):
        """Тестовый A2A сервер."""

        async def handle_agent_card(request):
            return web.json_response({
                "name": "Agent Remote Agent",
                "url": "http://localhost:9996",
                "skills": [{"id": "default", "name": "Default"}],
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
        site = web.TCPSite(runner, "localhost", 9996)
        await site.start()

        yield "http://localhost:9996"

        await runner.cleanup()

    @pytest.mark.asyncio
    async def test_flow_with_single_remote_node(self, remote_agent_server):
        """Agent с одной remote нодой."""
        config = AgentConfig(
            agent_id="remote_flow",
            name="Remote Agent",
            entry="remote",
            nodes={
                "remote": {
                    "type": "remote_agent",
                    "url": remote_agent_server,
                }
            },
            edges=[
                Edge(from_node="remote", to_node=None)
            ]
        )

        flow = await Agent.from_config(
            config={
                "id": config.agent_id,
                "name": config.name,
                "entry": config.entry,
                "nodes": config.nodes,
                "edges": config.edges
            },
            variables={}
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
    async def test_flow_with_inline_then_remote(self, remote_agent_server):
        """Agent: inline function → remote agent."""
        config = AgentConfig(
            agent_id="mixed_flow",
            name="Mixed Agent",
            entry="prepare",
            nodes={
                "prepare": {
                    "type": "code",
                    "code": """
def run(state):
    state['content'] = state.get('content', '').upper()
    state['prepared'] = True
    return state
"""
                },
                "remote": {
                    "type": "remote_agent",
                    "url": remote_agent_server,
                }
            },
            edges=[
                Edge(from_node="prepare", to_node="remote"),
                Edge(from_node="remote", to_node=None)
            ]
        )

        flow = await Agent.from_config(
            config={
                "id": config.agent_id,
                "name": config.name,
                "entry": config.entry,
                "nodes": config.nodes,
                "edges": config.edges
            },
            variables={}
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
    async def test_flow_remote_then_inline(self, remote_agent_server):
        """Agent: remote agent → inline function."""
        config = AgentConfig(
            agent_id="remote_first_flow",
            name="Remote First",
            entry="remote",
            nodes={
                "remote": {
                    "type": "remote_agent",
                    "url": remote_agent_server,
                },
                "process": {
                    "type": "code",
                    "code": """
def run(state):
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

        flow = await Agent.from_config(
            config={
                "id": config.agent_id,
                "name": config.name,
                "entry": config.entry,
                "nodes": config.nodes,
                "edges": config.edges
            },
            variables={}
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
    """Тесты input_mapping для RemoteAgentNode."""

    @pytest.fixture
    async def mock_a2a_server_with_logging(self):
        """A2A сервер который логирует что получил на вход."""
        received_messages = []

        async def handle_agent_card(request):
            return web.json_response({
                "name": "Input Logging Agent",
                "url": "http://localhost:9995",
                "skills": [{"id": "default", "name": "Default"}],
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
        site = web.TCPSite(runner, "localhost", 9995)
        await site.start()

        yield {"url": "http://localhost:9995", "received": received_messages}

        await runner.cleanup()

    @pytest.mark.asyncio
    async def test_input_mapping_content_default(self, mock_a2a_server_with_logging):
        """По умолчанию берётся state['content']."""
        server = mock_a2a_server_with_logging
        node = RemoteAgentNode(
            node_id="remote",
            config={"url": server["url"]},
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
    async def test_input_mapping_state_field(self, mock_a2a_server_with_logging):
        """input_mapping с @state:field берёт указанное поле."""
        server = mock_a2a_server_with_logging
        node = RemoteAgentNode(
            node_id="remote",
            config={
                "url": server["url"],
                "input_mapping": {"content": "@state:my_query"}
            }
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
    async def test_input_mapping_state_field_json(self, mock_a2a_server_with_logging):
        """Если поле не строка - сериализуется в JSON."""
        server = mock_a2a_server_with_logging
        node = RemoteAgentNode(
            node_id="remote",
            config={
                "url": server["url"],
                "input_mapping": {"content": "@state:data"}
            }
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
        import json
        received_data = json.loads(server["received"][0])
        assert received_data == {"key": "value", "num": 42}

    @pytest.mark.asyncio
    async def test_flow_with_input_mapping(self, mock_a2a_server_with_logging):
        """Agent где function пишет в state, а remote_agent читает через input_mapping."""
        server = mock_a2a_server_with_logging

        config = AgentConfig(
            agent_id="input_mapping_flow",
            name="Input Mapping Test",
            entry="prepare",
            nodes={
                "prepare": {
                    "type": "code",
                    "code": """
def run(state):
    state['prepared_query'] = 'Query from function node'
    return state
"""
                },
                "remote": {
                    "type": "remote_agent",
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

        flow = await Agent.from_config(
            config={
                "id": config.agent_id,
                "name": config.name,
                "entry": config.entry,
                "nodes": config.nodes,
                "edges": config.edges
            },
            variables={}
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

