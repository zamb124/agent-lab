"""
Интеграционные тесты для RemoteFlowNode (submit + park + webhook resume).

Remote-вызов каноничен: SendMessage(returnImmediately=true) с
taskPushNotificationConfig → RemoteTaskParked → durable activity ждёт
`record_activity_completed` от continuation `flows_remote_task_finished`
→ replay ноды забирает persisted result. Тесты гоняют обе фазы на
реальном HTTP сервере и реальной БД — без моков.
"""

import json

import pytest
from aiohttp import web

from apps.flows.src.models import Edge, FlowConfig
from apps.flows.src.runtime.exceptions import RemoteTaskParked
from apps.flows.src.runtime.execution_context import execution_context_for
from apps.flows.src.runtime.flow import Flow
from apps.flows.src.runtime.nodes import RemoteFlowNode, create_node
from core.a2a.pending_call import PlatformA2APendingCall
from tests.fixtures.aiohttp_ephemeral import ephemeral_web_server
from tests.flows.durable_runtime_harness import run_flow, run_node, workflow_state


def _remote_outcome(content: str, *, prefix: str) -> dict:
    """Outcome в формате `flows_remote_task_finished` (result_json.result)."""
    return {
        "response": f"{prefix}: {content}",
        "status": "completed",
        "artifacts": [
            {
                "artifactId": "remote-artifact-1",
                "name": "response",
                "parts": [{"text": f"{prefix}: {content}"}],
            }
        ],
        "error": None,
    }


async def _complete_remote_activity(di, activity_id: str, outcome: dict) -> None:
    """Симулирует webhook-continuation — то же, что `flows_remote_task_finished`."""
    completed = await di.workflow_runtime.record_activity_completed(
        activity_id=activity_id,
        result_json={"result": outcome},
    )
    assert completed, f"activity {activity_id} not completed"


def _make_remote_node(di, url: str, node_config_extra: dict | None = None) -> RemoteFlowNode:
    config = {"type": "remote_flow", "url": url}
    if node_config_extra:
        config.update(node_config_extra)
    return RemoteFlowNode(
        node_id="remote",
        config=config,
        execution=execution_context_for(di.node_constructor.workflow_runtime),
        redis_client=di.node_constructor.redis_client,
        a2a_client=di.node_constructor.a2a_client,
        emitter_factory=di.node_constructor.emitter_factory,
        billing_service=di.node_constructor.billing_service,
    )


class TestRemoteFlowNode:
    """RemoteFlowNode: submit → RemoteTaskParked → resume по completed activity."""

    @pytest.fixture
    async def remote_flow_server(self):
        """Каноничный A2A-агент: принимает client taskId, возвращает SUBMITTED."""
        public = {"base": "http://127.0.0.1:0"}
        received: list[dict] = []

        async def handle_agent_card(request):
            return web.json_response({
                "name": "Remote Test Agent",
                "url": public["base"],
                "branches": [{"id": "default", "name": "Default"}],
            })

        async def handle_send_task(request):
            data = await request.json()
            assert data["method"] == "SendMessage"
            received.append(data)
            task_id = data["params"]["message"]["taskId"]
            context_id = data["params"]["message"]["contextId"]
            return web.json_response({
                "jsonrpc": "2.0",
                "id": data["id"],
                "result": {
                    "id": task_id,
                    "contextId": context_id,
                    "status": {"state": "TASK_STATE_SUBMITTED"},
                    "artifacts": [],
                },
            })

        app = web.Application()
        app.router.add_get("/.well-known/agent-card.json", handle_agent_card)
        app.router.add_post("/", handle_send_task)

        async with ephemeral_web_server(app) as base_url:
            public["base"] = base_url
            yield {"url": base_url, "received": received}

    @pytest.mark.asyncio
    async def test_create_remote_flow_node(self, di):
        """Создание RemoteFlowNode через create_node."""
        node_config = {
            "type": "remote_flow",
            "url": "http://example.com:8080",
            "branch_id": "custom",
        }
        node = await create_node("remote_test", node_config, node_constructor=di.node_constructor, tool_registry=di.tool_registry, flow_factory=di.flow_factory)

        assert isinstance(node, RemoteFlowNode)
        assert node.url == "http://example.com:8080"
        assert node.branch_id == "custom"

    @pytest.mark.asyncio
    async def test_create_remote_flow_node_default_skill(self, di):
        """branch_id по умолчанию = 'default'."""
        node_config = {
            "type": "remote_flow",
            "url": "http://example.com:8080",
        }
        node = await create_node("remote_test", node_config, node_constructor=di.node_constructor, tool_registry=di.tool_registry, flow_factory=di.flow_factory)

        assert node.branch_id == "default"

    @pytest.mark.asyncio
    async def test_remote_flow_node_parks_on_submit(self, remote_flow_server, di, unique_id):
        """Submit: SendMessage с returnImmediately + push config, парк, pending-ряд."""
        node = _make_remote_node(di, remote_flow_server["url"])
        state = workflow_state(
            flow_id="remote_node",
            unique_id=f"remote-node-{unique_id}",
            content="Hello from flow",
        )

        with pytest.raises(RemoteTaskParked) as exc_info:
            await run_node(di=di, node=node, state=state)

        parked = exc_info.value
        assert parked.node_id == "remote"
        assert parked.base_url == remote_flow_server["url"]

        # SendMessage реально ушёл с каноничной конфигурацией.
        assert len(remote_flow_server["received"]) == 1
        configuration = remote_flow_server["received"][0]["params"]["configuration"]
        assert configuration["returnImmediately"] is True
        push_config = configuration["taskPushNotificationConfig"]
        assert push_config["url"].endswith("/flows/api/v1/internal/a2a/push")
        assert isinstance(push_config["token"], str) and push_config["token"]

        # Pending-ряд зарегистрирован и ждёт webhook.
        row = await PlatformA2APendingCall.pending_by_id(parked.a2a_task_id)
        assert row is not None
        assert row.status == "pending"
        assert row.continuation_task == "flows_remote_task_finished"

    @pytest.mark.asyncio
    async def test_remote_flow_node_resume_completed(self, remote_flow_server, di, unique_id):
        """Replay: completed activity → результат из webhook без повторного submit."""
        node = _make_remote_node(di, remote_flow_server["url"])
        state = workflow_state(
            flow_id="remote_node",
            unique_id=f"remote-node-resume-{unique_id}",
            content="Hello from flow",
        )
        with pytest.raises(RemoteTaskParked) as exc_info:
            await run_node(di=di, node=node, state=state)

        await _complete_remote_activity(
            di,
            exc_info.value.activity_id,
            _remote_outcome("Hello from flow", prefix="Remote says"),
        )

        result = await node.run(state)

        assert result["response"] == "Remote says: Hello from flow"
        assert result["remote_status"] == "completed"
        assert len(result["remote_artifacts"]) == 1
        # Повторного SendMessage не было — replay взял persisted result.
        assert len(remote_flow_server["received"]) == 1

    @pytest.mark.asyncio
    async def test_remote_flow_node_resume_failed(self, remote_flow_server, di, unique_id):
        """Failed-терминал webhook'а → replay поднимает A2AClientError."""
        from core.clients.a2a_client import A2AClientError

        node = _make_remote_node(di, remote_flow_server["url"])
        state = workflow_state(
            flow_id="remote_node",
            unique_id=f"remote-node-failed-{unique_id}",
            content="Boom",
        )
        with pytest.raises(RemoteTaskParked) as exc_info:
            await run_node(di=di, node=node, state=state)

        await _complete_remote_activity(
            di,
            exc_info.value.activity_id,
            {
                "response": "",
                "status": "failed",
                "artifacts": [],
                "error": "remote exploded",
            },
        )

        with pytest.raises(A2AClientError, match="remote exploded"):
            await node.run(state)

    @pytest.mark.asyncio
    async def test_remote_flow_node_preserves_state(self, remote_flow_server, di, unique_id):
        """Replay сохраняет существующие поля state."""
        node = _make_remote_node(di, remote_flow_server["url"])
        state = workflow_state(
            flow_id="remote_node_preserve",
            unique_id=f"remote-node-preserve-{unique_id}",
            content="Test",
            existing_field="preserved",
            counter=42,
        )
        with pytest.raises(RemoteTaskParked) as exc_info:
            await run_node(di=di, node=node, state=state)

        await _complete_remote_activity(
            di,
            exc_info.value.activity_id,
            _remote_outcome("Test", prefix="Remote says"),
        )
        result = await node.run(state)

        assert result["existing_field"] == "preserved"
        assert result["counter"] == 42
        assert "response" in result


class TestFlowWithRemoteAgent:
    """Flow с RemoteFlowNode: run loop паркует state.remote_wait и резюмит."""

    @pytest.fixture
    async def remote_flow_server(self):
        public = {"base": "http://127.0.0.1:0"}

        async def handle_agent_card(request):
            return web.json_response({
                "name": "Agent Remote Agent",
                "url": public["base"],
                "branches": [{"id": "default", "name": "Default"}],
            })

        async def handle_send_task(request):
            data = await request.json()
            task_id = data["params"]["message"]["taskId"]
            context_id = data["params"]["message"]["contextId"]
            return web.json_response({
                "jsonrpc": "2.0",
                "id": data["id"],
                "result": {
                    "id": task_id,
                    "contextId": context_id,
                    "status": {"state": "TASK_STATE_SUBMITTED"},
                    "artifacts": [],
                },
            })

        app = web.Application()
        app.router.add_get("/.well-known/agent-card.json", handle_agent_card)
        app.router.add_post("/", handle_send_task)

        async with ephemeral_web_server(app) as base_url:
            public["base"] = base_url
            yield base_url

    @pytest.mark.asyncio
    async def test_flow_with_single_remote_node(self, remote_flow_server, di, unique_id):
        """Flow паркуется на remote ноде и резюмит после webhook-continuation."""
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
            config=config.model_dump(mode="json"),
            variables={},
            node_constructor=di.node_constructor, tool_registry=di.tool_registry, flow_factory=di.flow_factory,
        )

        state = workflow_state(
            flow_id=config.flow_id,
            unique_id=f"remote-single-{unique_id}",
            content="Hello remote",
        )
        parked_state = await run_flow(di=di, flow=flow, state=state)

        # Run loop не бросил — вернул состояние с маркером ожидания.
        assert parked_state.remote_wait is not None
        assert parked_state.remote_wait["node_id"] == "remote"
        assert parked_state.current_nodes == ["remote"]

        await _complete_remote_activity(
            di,
            parked_state.remote_wait["activity_id"],
            _remote_outcome("Hello remote", prefix="Processed"),
        )

        result = await run_flow(di=di, flow=flow, state=parked_state)

        assert result["response"] == "Processed: Hello remote"
        assert result.remote_wait is None

    @pytest.mark.asyncio
    async def test_flow_with_inline_then_remote(self, remote_flow_server, di, unique_id):
        """Agent: inline function → remote agent (park + resume)."""
        config = FlowConfig(
            flow_id="mixed_flow",
            name="Mixed Agent",
            entry="prepare",
            nodes={
                "prepare": {
                    "type": "code",
                    "code": """
async def run(args, state):
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
            config=config.model_dump(mode="json"),
            variables={},
            node_constructor=di.node_constructor, tool_registry=di.tool_registry, flow_factory=di.flow_factory,
        )

        state = workflow_state(
            flow_id=config.flow_id,
            unique_id=f"remote-inline-{unique_id}",
            content="hello",
        )
        parked_state = await run_flow(di=di, flow=flow, state=state)
        assert parked_state.remote_wait is not None

        await _complete_remote_activity(
            di,
            parked_state.remote_wait["activity_id"],
            _remote_outcome("HELLO", prefix="Processed"),
        )
        result = await run_flow(di=di, flow=flow, state=parked_state)

        assert result["prepared"] is True
        assert result["response"] == "Processed: HELLO"

    @pytest.mark.asyncio
    async def test_flow_remote_then_inline(self, remote_flow_server, di, unique_id):
        """Agent: remote agent (park + resume) → inline function."""
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
async def run(args, state):
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
            config=config.model_dump(mode="json"),
            variables={},
            node_constructor=di.node_constructor, tool_registry=di.tool_registry, flow_factory=di.flow_factory,
        )

        state = workflow_state(
            flow_id=config.flow_id,
            unique_id=f"remote-first-{unique_id}",
            content="test",
        )
        parked_state = await run_flow(di=di, flow=flow, state=state)
        assert parked_state.remote_wait is not None

        await _complete_remote_activity(
            di,
            parked_state.remote_wait["activity_id"],
            _remote_outcome("test", prefix="Processed"),
        )
        result = await run_flow(di=di, flow=flow, state=parked_state)

        assert result["final"] == "Final: Processed: test"


class TestRemoteAgentInputMapping:
    """input_mapping для RemoteFlowNode — разрешается до submit."""

    @pytest.fixture
    async def mock_a2a_server_with_logging(self):
        """A2A сервер, логирующий что получил на вход."""
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
            task_id = data["params"]["message"]["taskId"]
            context_id = data["params"]["message"]["contextId"]
            return web.json_response({
                "jsonrpc": "2.0",
                "id": data["id"],
                "result": {
                    "id": task_id,
                    "contextId": context_id,
                    "status": {"state": "TASK_STATE_SUBMITTED"},
                    "artifacts": [],
                },
            })

        app = web.Application()
        app.router.add_get("/.well-known/agent-card.json", handle_agent_card)
        app.router.add_post("/", handle_send_task)

        async with ephemeral_web_server(app) as base_url:
            public["base"] = base_url
            yield {"url": base_url, "received": received_messages}

    @pytest.mark.asyncio
    async def test_input_mapping_content_default(
        self, mock_a2a_server_with_logging, di, unique_id
    ):
        """По умолчанию берётся state['content']."""
        server = mock_a2a_server_with_logging
        node = _make_remote_node(di, server["url"])
        state = workflow_state(
            flow_id="remote_input_default",
            unique_id=f"remote-input-default-{unique_id}",
            content="default content",
            other_field="ignored",
        )
        with pytest.raises(RemoteTaskParked):
            await run_node(di=di, node=node, state=state)

        assert len(server["received"]) == 1
        assert server["received"][0] == "default content"

    @pytest.mark.asyncio
    async def test_input_mapping_state_field(
        self, mock_a2a_server_with_logging, di, unique_id
    ):
        """input_mapping с @state:field берёт указанное поле."""
        server = mock_a2a_server_with_logging
        node = _make_remote_node(
            di,
            server["url"],
            {"input_mapping": {"content": "@state:my_query"}},
        )
        state = workflow_state(
            flow_id="remote_input_field",
            unique_id=f"remote-input-field-{unique_id}",
            content="ignored",
            my_query="custom field value",
        )
        with pytest.raises(RemoteTaskParked):
            await run_node(di=di, node=node, state=state)

        assert len(server["received"]) == 1
        assert server["received"][0] == "custom field value"

    @pytest.mark.asyncio
    async def test_input_mapping_state_field_json(
        self, mock_a2a_server_with_logging, di, unique_id
    ):
        """Если поле не строка - сериализуется в JSON."""
        server = mock_a2a_server_with_logging
        node = _make_remote_node(
            di,
            server["url"],
            {"input_mapping": {"content": "@state:data"}},
        )
        state = workflow_state(
            flow_id="remote_input_json",
            unique_id=f"remote-input-json-{unique_id}",
            content="ignored",
            data={"key": "value", "num": 42},
        )
        with pytest.raises(RemoteTaskParked):
            await run_node(di=di, node=node, state=state)

        assert len(server["received"]) == 1
        received_data = json.loads(server["received"][0])
        assert received_data == {"key": "value", "num": 42}

    @pytest.mark.asyncio
    async def test_flow_with_input_mapping(
        self, mock_a2a_server_with_logging, di, unique_id
    ):
        """Flow: function пишет в state, remote_flow читает через input_mapping."""
        server = mock_a2a_server_with_logging

        config = FlowConfig(
            flow_id="input_mapping_flow",
            name="Input Mapping Test",
            entry="prepare",
            nodes={
                "prepare": {
                    "type": "code",
                    "code": """
async def run(args, state):
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
            config=config.model_dump(mode="json"),
            variables={},
            node_constructor=di.node_constructor, tool_registry=di.tool_registry, flow_factory=di.flow_factory,
        )

        state = workflow_state(
            flow_id=config.flow_id,
            unique_id=f"remote-input-flow-{unique_id}",
            content="original content",
        )
        parked_state = await run_flow(di=di, flow=flow, state=state)

        # Remote agent получил данные из prepared_query.
        assert len(server["received"]) == 1
        assert server["received"][0] == "Query from function node"
        assert parked_state.remote_wait is not None

        await _complete_remote_activity(
            di,
            parked_state.remote_wait["activity_id"],
            _remote_outcome("Query from function node", prefix="Received"),
        )
        result = await run_flow(di=di, flow=flow, state=parked_state)

        assert result["response"] == "Received: Query from function node"
