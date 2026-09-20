"""
Тесты A2A API.

СТРОГАЯ ПРОВЕРКА соответствия a2a-sdk:
- Все поля Task, TaskStatus, Message, Events проверяются
- Типы и значения валидируются
- БЕЗ моков для Redis/TaskIQ - только MockLLM
"""

import json
import uuid
from typing import Any, Dict, List

import pytest

from tests.flows._a2a_v1 import A2A_HEADERS


def _msg(text: str, task_id: str = None, context_id: str = None) -> Dict[str, Any]:
    """Создаёт A2A Message с ОБЯЗАТЕЛЬНЫМИ полями по спецификации."""
    m = {"messageId": str(uuid.uuid4()), "role": "ROLE_USER", "parts": [{"text": text}]}
    if task_id:
        m["taskId"] = task_id
    if context_id:
        m["contextId"] = context_id
    return m


def _parse_sse(text: str) -> List[Dict]:
    """Парсит SSE ответ."""
    events = []
    for line in text.strip().split("\n"):
        if line.startswith("data:"):
            try:
                data = json.loads(line[5:].strip())
                events.append(data)
            except json.JSONDecodeError:
                pass
    return events


def _validate_task(task: Dict, *, require_history: bool = False) -> None:
    """Строгая валидация Task по A2A SDK спецификации."""
    assert "id" in task, "Task MUST have 'id' field"
    assert isinstance(task["id"], str), "Task.id MUST be string"
    assert "contextId" in task, "Task MUST have 'contextId' field"
    assert isinstance(task["contextId"], str), "Task.contextId MUST be string"
    assert "status" in task, "Task MUST have 'status' field"
    _validate_task_status(task["status"])
    if require_history:
        assert "history" in task and task["history"] is not None, "Task MUST have history"
        assert isinstance(task["history"], list), "Task.history MUST be list"
        for msg in task["history"]:
            _validate_message(msg)


def _validate_task_status(status: Dict) -> None:
    """Строгая валидация TaskStatus по A2A SDK спецификации."""
    assert "state" in status, "TaskStatus MUST have 'state' field"
    valid_states = [
        "TASK_STATE_SUBMITTED",
        "TASK_STATE_WORKING",
        "TASK_STATE_INPUT_REQUIRED",
        "TASK_STATE_AUTH_REQUIRED",
        "TASK_STATE_COMPLETED",
        "TASK_STATE_FAILED",
        "TASK_STATE_REJECTED",
        "TASK_STATE_CANCELED",
        "unknown",
    ]
    assert status["state"] in valid_states, f"Invalid TaskState: {status['state']}"
    if "message" in status and status["message"] is not None:
        _validate_message(status["message"])


def _validate_message(msg: Dict) -> None:
    """Строгая валидация Message по A2A SDK спецификации."""
    assert "messageId" in msg, "Message MUST have 'messageId' field"
    assert isinstance(msg["messageId"], str), "Message.messageId MUST be string"
    assert "role" in msg, "Message MUST have 'role' field"
    assert msg["role"] in ["ROLE_USER", "ROLE_AGENT"], f"Invalid role: {msg['role']}"
    assert "parts" in msg, "Message MUST have 'parts' field"
    assert isinstance(msg["parts"], list), "Message.parts MUST be list"
    assert len(msg["parts"]) > 0, "Message.parts MUST NOT be empty"
    for part in msg["parts"]:
        _validate_part(part)


def _validate_part(part: Dict) -> None:
    """Строгая валидация Part по A2A Protocol 1.0 ProtoJSON."""
    has_text = "text" in part
    has_raw = "raw" in part
    has_url = "url" in part
    has_data = "data" in part
    assert has_text or has_raw or has_url or has_data, f"Part must have text/raw/url/data: {part}"
    if has_text:
        assert isinstance(part["text"], str), "Part.text MUST be string"
    if has_raw or has_url:
        assert "filename" in part, "File Part MUST have filename"


def _stream_payload(result: Dict) -> tuple[Dict, str]:
    """Unwrap StreamResponse ProtoJSON: statusUpdate / artifactUpdate."""
    if "statusUpdate" in result:
        body = result["statusUpdate"]
        assert isinstance(body, dict), "statusUpdate MUST be object"
        return body, "statusUpdate"
    if "artifactUpdate" in result:
        body = result["artifactUpdate"]
        assert isinstance(body, dict), "artifactUpdate MUST be object"
        return body, "artifactUpdate"
    raise AssertionError(f"StreamResponse MUST have statusUpdate or artifactUpdate, got keys={sorted(result.keys())}")


def _validate_status_update_event(event: Dict) -> None:
    """Строгая валидация StreamResponse.statusUpdate."""
    result = event.get("result", event)
    body, kind = _stream_payload(result)
    assert kind == "statusUpdate"
    assert "taskId" in body, "TaskStatusUpdateEvent MUST have 'taskId'"
    assert isinstance(body["taskId"], str), "taskId MUST be string"
    assert "contextId" in body, "TaskStatusUpdateEvent MUST have 'contextId'"
    assert isinstance(body["contextId"], str), "contextId MUST be string"
    assert "status" in body, "TaskStatusUpdateEvent MUST have 'status'"
    _validate_task_status(body["status"])


def _validate_artifact_update_event(event: Dict) -> None:
    """Строгая валидация StreamResponse.artifactUpdate."""
    result = event.get("result", event)
    body, kind = _stream_payload(result)
    assert kind == "artifactUpdate"
    assert "taskId" in body, "TaskArtifactUpdateEvent MUST have 'taskId'"
    assert "contextId" in body, "TaskArtifactUpdateEvent MUST have 'contextId'"
    assert "artifact" in body, "TaskArtifactUpdateEvent MUST have 'artifact'"


def _validate_jsonrpc_response(data: Dict) -> None:
    """Строгая валидация JSON-RPC 2.0 response."""
    assert "jsonrpc" in data, "JSON-RPC response MUST have 'jsonrpc' field"
    assert data["jsonrpc"] == "2.0", "jsonrpc MUST be '2.0'"
    assert "id" in data, "JSON-RPC response MUST have 'id' field"
    assert "result" in data or "error" in data, "JSON-RPC response MUST have 'result' or 'error'"
    if "error" in data:
        assert "code" in data["error"], "JSON-RPC error MUST have 'code'"
        assert "message" in data["error"], "JSON-RPC error MUST have 'message'"


class TestA2AAgentCard:
    """Тесты Agent Card - строгая проверка структуры."""

    @pytest.fixture
    async def flow_id(self, client):
        return "example_react"

    @pytest.mark.asyncio
    async def test_agent_card_exists(self, client, flow_id, auth_headers_system):
        """Agent Card доступен и имеет правильную структуру."""
        resp = await client.get(f"/flows/api/v1/{flow_id}", headers=auth_headers_system)
        assert resp.status_code == 200
        card = resp.json()
        assert "name" in card, "AgentCard MUST have 'name'"
        assert isinstance(card["name"], str), "AgentCard.name MUST be string"
        assert "supportedInterfaces" in card, "AgentCard MUST have 'supportedInterfaces'"
        interfaces = card["supportedInterfaces"]
        assert isinstance(interfaces, list) and len(interfaces) > 0
        primary = interfaces[0]
        assert "url" in primary, "AgentInterface MUST have 'url'"
        assert isinstance(primary["url"], str), f"AgentInterface.url MUST be string, got: {primary.get('url')}"
        assert primary.get("protocolBinding") == "JSONRPC"
        assert primary.get("protocolVersion") == "1.0"
        assert "version" in card, "AgentCard MUST have 'version'"
        assert isinstance(card["version"], str), "AgentCard.version MUST be string"
        assert "capabilities" in card, "AgentCard MUST have 'capabilities'"
        assert isinstance(card["capabilities"], dict), "AgentCard.capabilities MUST be object"
        caps = card["capabilities"]
        assert "streaming" in caps, "Capabilities MUST have 'streaming'"
        assert isinstance(caps["streaming"], bool), "streaming MUST be boolean"
        assert "pushNotifications" in caps, "Capabilities MUST have 'pushNotifications'"
        assert isinstance(caps["pushNotifications"], bool), "pushNotifications MUST be boolean"

    @pytest.mark.asyncio
    async def test_agent_card_403_unknown_flow(self, client):
        """Несуществующий flow: Check до existence → 403, не 404."""
        resp = await client.get("/flows/api/v1/nonexistent_flow_xyz")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_agent_card_branches(self, client, flow_id):
        """Agent Card: A2A skills + platform branches extension."""
        resp = await client.get(f"/flows/api/v1/{flow_id}")
        card = resp.json()
        assert "skills" in card
        assert isinstance(card["skills"], list), "skills MUST be a list"
        assert len(card["skills"]) >= 1
        assert "branches" in card
        assert card["branches"] == card["skills"]
        for skill_entry in card["skills"]:
            assert "id" in skill_entry, "skill entry MUST have 'id'"
            assert "name" in skill_entry, "skill entry MUST have 'name'"


class TestA2AMessageSend:
    """Тесты SendMessage - строгая проверка Task response."""

    @pytest.fixture
    async def flow_id(self, client):
        return "example_react"

    @pytest.mark.asyncio
    async def test_message_send_returns_valid_task(
        self, client, flow_id, mock_llm_with_queue, sync_tools
    ):
        """SendMessage возвращает валидный Task по A2A спецификации."""
        mock_llm_with_queue(["Test response"])
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "test-1",
                "method": "SendMessage",
                "params": {"message": _msg("Hello")},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        _validate_jsonrpc_response(data)
        assert "result" in data
        task = data["result"]
        _validate_task(task)
        assert task["status"]["state"] == "TASK_STATE_COMPLETED"

    @pytest.mark.asyncio
    async def test_message_send_with_context_id(
        self, client, flow_id, mock_llm_with_queue, sync_tools
    ):
        """SendMessage сохраняет переданный contextId."""
        mock_llm_with_queue(["Response"])
        context_id = str(uuid.uuid4())
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "test-2",
                "method": "SendMessage",
                "params": {"message": _msg("Test", context_id=context_id)},
            },
        )
        data = resp.json()
        _validate_jsonrpc_response(data)
        task = data["result"]
        _validate_task(task)
        assert task["contextId"] == context_id

    @pytest.mark.asyncio
    async def test_message_send_history(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """SendMessage сохраняет user Message в history; ответ агента — в status/artifacts."""
        mock_llm_with_queue(["Agent response"])
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "test-3",
                "method": "SendMessage",
                "params": {"message": _msg("User message")},
            },
        )
        data = resp.json()
        task = data["result"]
        _validate_task(task, require_history=True)
        roles = [msg["role"] for msg in task["history"]]
        assert "ROLE_USER" in roles, "History MUST contain user message"
        status_message = task["status"].get("message")
        artifacts = task.get("artifacts") or []
        response_artifacts = [
            artifact for artifact in artifacts if artifact.get("name") == "response"
        ]
        assert status_message is not None or response_artifacts, (
            "Agent reply must appear in status.message and/or response artifact"
        )

    @pytest.mark.asyncio
    async def test_unknown_flow_error(self, client):
        """Неизвестный flow: Check до existence → HTTP 403, без JSON-RPC existence leak."""
        resp = await client.post(
            "/flows/api/v1/unknown_flow_xyz",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "SendMessage",
                "params": {"message": _msg("Test")},
            },
        )
        assert resp.status_code == 403


class TestA2ATasksGet:
    """Тесты GetTask - строгая проверка."""

    @pytest.fixture
    async def flow_id(self, client):
        return "example_react"

    @pytest.mark.asyncio
    async def test_tasks_get_returns_valid_task(
        self, client, flow_id, mock_llm_with_queue, sync_tools
    ):
        """GetTask возвращает валидный Task."""
        mock_llm_with_queue(["Initial response"])
        context_id = str(uuid.uuid4())
        await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "SendMessage",
                "params": {"message": _msg("Create task", context_id=context_id)},
            },
        )
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={"jsonrpc": "2.0", "id": "2", "method": "GetTask", "params": {"id": context_id}},
        )
        data = resp.json()
        _validate_jsonrpc_response(data)
        task = data["result"]
        _validate_task(task)

    @pytest.mark.asyncio
    async def test_tasks_get_with_history_length(
        self, client, flow_id, mock_llm_with_queue, sync_tools
    ):
        """GetTask с historyLength ограничивает историю."""
        mock_llm_with_queue(["Response 1", "Response 2", "Response 3"])
        context_id = str(uuid.uuid4())
        for i in range(3):
            await client.post(
                f"/flows/api/v1/{flow_id}",
                headers=A2A_HEADERS,
                json={
                    "jsonrpc": "2.0",
                    "id": str(i),
                    "method": "SendMessage",
                    "params": {"message": _msg(f"Message {i}", context_id=context_id)},
                },
            )
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "get",
                "method": "GetTask",
                "params": {"id": context_id, "historyLength": 2},
            },
        )
        data = resp.json()
        task = data["result"]
        if task and task.get("history"):
            assert len(task["history"]) <= 2

    @pytest.mark.asyncio
    async def test_tasks_get_not_found(self, client, flow_id):
        """GetTask для несуществующей задачи возвращает TASK_NOT_FOUND."""
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "GetTask",
                "params": {"id": str(uuid.uuid4())},
            },
        )
        data = resp.json()
        _validate_jsonrpc_response(data)
        assert "error" in data
        assert data["error"]["code"] == -32001


class TestA2ATasksCancel:
    """Тесты CancelTask - строгая проверка."""

    @pytest.fixture
    async def flow_id(self, client):
        return "example_react"

    @pytest.mark.asyncio
    async def test_tasks_cancel_returns_canceled_task(
        self, client, flow_id, mock_llm_with_queue, sync_tools
    ):
        """CancelTask возвращает Task со статусом canceled (из input-required)."""
        mock_llm_with_queue(
            [{"type": "tool_call", "tool": "ask_user", "args": {"question": "Name?"}}]
        )
        context_id = str(uuid.uuid4())
        create_resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "SendMessage",
                "params": {"message": _msg("Create", context_id=context_id)},
            },
        )
        create_data = create_resp.json()
        _validate_jsonrpc_response(create_data)
        assert create_data["result"]["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "2",
                "method": "CancelTask",
                "params": {"id": context_id},
            },
        )
        data = resp.json()
        _validate_jsonrpc_response(data)
        task = data["result"]
        _validate_task(task)
        assert task["status"]["state"] == "TASK_STATE_CANCELED"


class TestA2AMessageStream:
    """Тесты SendStreamingMessage - строгая проверка SSE событий."""

    @pytest.fixture
    async def flow_id(self, client):
        return "example_react"

    @pytest.mark.asyncio
    async def test_stream_returns_sse(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """SendStreamingMessage возвращает SSE формат."""
        mock_llm_with_queue(["Streaming response"])
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "SendStreamingMessage",
                "params": {"message": _msg("Stream test")},
            },
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_stream_events_are_valid(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """Все события в stream соответствуют A2A спецификации."""
        mock_llm_with_queue(["Valid events"])
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "SendStreamingMessage",
                "params": {"message": _msg("Test events")},
            },
        )
        events = _parse_sse(resp.text)
        assert len(events) > 0, "Stream MUST contain events"
        for event in events:
            _validate_jsonrpc_response(event)
            result = event.get("result", {})
            if "statusUpdate" in result:
                _validate_status_update_event(event)
            elif "artifactUpdate" in result:
                _validate_artifact_update_event(event)
            elif "task" in result:
                _validate_task(result["task"])

    @pytest.mark.asyncio
    async def test_stream_has_final_event(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """Stream содержит терминальный statusUpdate (COMPLETED/FAILED/...)."""
        mock_llm_with_queue(["Final test"])
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "SendStreamingMessage",
                "params": {"message": _msg("Test final")},
            },
        )
        events = _parse_sse(resp.text)
        final_events = [
            e
            for e in events
            if e.get("result", {}).get("statusUpdate", {}).get("status", {}).get("state")
            in (
                "TASK_STATE_COMPLETED",
                "TASK_STATE_FAILED",
                "TASK_STATE_CANCELED",
                "TASK_STATE_INPUT_REQUIRED",
            )
        ]
        assert len(final_events) > 0, "Stream MUST contain terminal statusUpdate"

    @pytest.mark.asyncio
    async def test_stream_opens_with_submitted_task_snapshot(
        self, client, flow_id, mock_llm_with_queue, sync_tools, unique_id
    ):
        """Первый кадр — Task (SUBMITTED, history с ходом пользователя, без артефактов);
        дальше только status/artifact события, текст ответа собирается без дублей."""
        user_text = f"Snapshot first {unique_id}"
        reply = f"Reply {unique_id}"
        mock_llm_with_queue([reply])
        message = _msg(user_text)
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "SendStreamingMessage",
                "params": {"message": message},
            },
        )
        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        assert len(events) >= 2
        first = events[0]["result"]
        assert set(first.keys()) == {"task"}, f"first frame MUST be Task, got {sorted(first)}"
        snapshot = first["task"]
        _validate_task(snapshot, require_history=True)
        assert snapshot["status"]["state"] == "TASK_STATE_SUBMITTED"
        assert snapshot.get("artifacts", []) == []
        user_messages = [m for m in snapshot["history"] if m["role"] == "ROLE_USER"]
        assert [m["messageId"] for m in user_messages] == [message["messageId"]]
        assert user_messages[0]["taskId"] == snapshot["id"]
        assert user_messages[0]["parts"] == [{"text": user_text}]
        for event in events[1:]:
            result = event["result"]
            assert "task" not in result, "Task snapshot MUST be sent exactly once"
            _, kind = _stream_payload(result)
            assert (result[kind]["taskId"], result[kind]["contextId"]) == (
                snapshot["id"],
                snapshot["contextId"],
            )
        response_text = "".join(
            part["text"]
            for event in events[1:]
            if "artifactUpdate" in event["result"]
            and event["result"]["artifactUpdate"]["artifact"].get("name") == "response"
            for part in event["result"]["artifactUpdate"]["artifact"]["parts"]
            if "text" in part
        )
        assert response_text == reply


class TestA2AInterrupt:
    """Тесты interrupt (input-required) - строгая проверка."""

    @pytest.fixture
    async def flow_id(self, client):
        return "example_react"

    @pytest.mark.asyncio
    async def test_interrupt_returns_input_required(
        self, client, flow_id, mock_llm_with_queue, sync_tools
    ):
        """ask_user возвращает Task со статусом input-required."""
        mock_llm_with_queue(
            [{"type": "tool_call", "tool": "ask_user", "args": {"question": "Your name?"}}]
        )
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "SendMessage",
                "params": {"message": _msg("Start")},
            },
        )
        data = resp.json()
        _validate_jsonrpc_response(data)
        task = data["result"]
        _validate_task(task)
        assert task["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
        assert task["status"]["message"] is not None
        _validate_message(task["status"]["message"])

    @pytest.mark.asyncio
    async def test_resume_after_interrupt(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """Resume после interrupt возвращает completed."""
        mock_llm_with_queue(
            [
                {"type": "tool_call", "tool": "ask_user", "args": {"question": "Name?"}},
                "Hello, John!",
            ]
        )
        context_id = str(uuid.uuid4())
        r1 = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "SendMessage",
                "params": {"message": _msg("Start", context_id=context_id)},
            },
        )
        data1 = r1.json()
        assert data1["result"]["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
        r2 = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "2",
                "method": "SendMessage",
                "params": {"message": _msg("John", context_id=context_id)},
            },
        )
        data2 = r2.json()
        _validate_jsonrpc_response(data2)
        task2 = data2["result"]
        _validate_task(task2)
        assert task2["status"]["state"] == "TASK_STATE_COMPLETED"

    @pytest.mark.asyncio
    async def test_tasks_get_shows_input_required(
        self, client, flow_id, mock_llm_with_queue, sync_tools
    ):
        """GetTask показывает input-required состояние."""
        mock_llm_with_queue(
            [{"type": "tool_call", "tool": "ask_user", "args": {"question": "Age?"}}]
        )
        context_id = str(uuid.uuid4())
        await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "SendMessage",
                "params": {"message": _msg("Start", context_id=context_id)},
            },
        )
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={"jsonrpc": "2.0", "id": "2", "method": "GetTask", "params": {"id": context_id}},
        )
        data = resp.json()
        task = data["result"]
        assert task["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"

    @pytest.mark.asyncio
    async def test_stream_interrupt_has_input_required_event(
        self, client, flow_id, mock_llm_with_queue, sync_tools
    ):
        """Stream с interrupt содержит событие input-required."""
        mock_llm_with_queue(
            [{"type": "tool_call", "tool": "ask_user", "args": {"question": "Question?"}}]
        )
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "SendStreamingMessage",
                "params": {"message": _msg("Stream interrupt")},
            },
        )
        events = _parse_sse(resp.text)
        input_required = [
            e
            for e in events
            if e.get("result", {}).get("statusUpdate", {}).get("status", {}).get("state") == "TASK_STATE_INPUT_REQUIRED"
        ]
        assert len(input_required) > 0, "Stream MUST contain input-required event"

    @pytest.mark.asyncio
    async def test_resume_preserves_task_id_and_receives_response(
        self, client, flow_id, mock_llm_with_queue, sync_tools
    ):
        """
        СТРОГАЯ ПРОВЕРКА: при resume клиент получает ответ.

        Проверяем что:
        1. Первый запрос возвращает input-required с task_id
        2. При resume используется тот же task_id
        3. Клиент получает финальный ответ (completed)
        4. Ответ содержит текст от LLM
        """
        mock_llm_with_queue(
            [
                {
                    "type": "tool_call",
                    "tool": "ask_user",
                    "args": {"question": "What is your name?"},
                },
                "Hello, TestUser! Nice to meet you.",
            ]
        )
        context_id = str(uuid.uuid4())
        r1 = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "SendMessage",
                "params": {"message": _msg("Hello", context_id=context_id)},
            },
        )
        data1 = r1.json()
        _validate_jsonrpc_response(data1)
        task1 = data1["result"]
        _validate_task(task1)
        assert task1["status"]["state"] == "TASK_STATE_INPUT_REQUIRED", (
            f"First request MUST return input-required, got: {task1['status']['state']}"
        )
        first_task_id = task1["id"]
        assert first_task_id, "Task MUST have id"
        assert task1["status"]["message"] is not None, "input-required MUST have message"
        question_parts = task1["status"]["message"]["parts"]
        question_text = "".join(
            (p.get("text", "") for p in question_parts if "text" in p)
        )
        assert "name" in question_text.lower(), (
            f"Question should ask about name, got: {question_text}"
        )
        r2 = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "2",
                "method": "SendMessage",
                "params": {"message": _msg("TestUser", context_id=context_id)},
            },
        )
        data2 = r2.json()
        _validate_jsonrpc_response(data2)
        task2 = data2["result"]
        _validate_task(task2)
        assert task2["status"]["state"] == "TASK_STATE_COMPLETED", (
            f"Resume MUST return completed, got: {task2['status']['state']}"
        )
        assert task2["id"] == first_task_id, (
            f"Task ID MUST be preserved across interrupt/resume. First: {first_task_id}, Resume: {task2['id']}"
        )
        assert task2["status"]["message"] is not None, "completed MUST have message"
        response_parts = task2["status"]["message"]["parts"]
        response_text = "".join(
            (p.get("text", "") for p in response_parts if "text" in p)
        )
        assert "TestUser" in response_text, (
            f"Response should contain user name, got: {response_text}"
        )
        assert "Hello" in response_text or "Nice" in response_text, (
            f"Response should contain greeting, got: {response_text}"
        )

    @pytest.mark.asyncio
    async def test_stream_resume_receives_events(
        self, client, flow_id, mock_llm_with_queue, sync_tools
    ):
        """
        СТРОГАЯ ПРОВЕРКА: при resume через stream клиент получает события.

        Проверяем что:
        1. Первый stream возвращает input-required
        2. При resume stream возвращает completed событие
        """
        mock_llm_with_queue(
            [
                {"type": "tool_call", "tool": "ask_user", "args": {"question": "City?"}},
                "Moscow is a great city!",
            ]
        )
        context_id = str(uuid.uuid4())
        r1 = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "SendStreamingMessage",
                "params": {"message": _msg("Start", context_id=context_id)},
            },
        )
        events1 = _parse_sse(r1.text)
        input_required_events = [
            e
            for e in events1
            if e.get("result", {}).get("statusUpdate", {}).get("status", {}).get("state") == "TASK_STATE_INPUT_REQUIRED"
        ]
        assert len(input_required_events) > 0, "First stream MUST contain input-required event"
        r2 = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "2",
                "method": "SendStreamingMessage",
                "params": {"message": _msg("Moscow", context_id=context_id)},
            },
        )
        events2 = _parse_sse(r2.text)
        completed_events = [
            e for e in events2 if e.get("result", {}).get("statusUpdate", {}).get("status", {}).get("state") == "TASK_STATE_COMPLETED"
        ]
        assert len(completed_events) > 0, (
            f"Resume stream MUST contain completed event. Got events: {[e.get('result', {}).get('status', {}).get('state') for e in events2]}"
        )
        completed = completed_events[-1]
        msg = completed.get("result", {}).get("statusUpdate", {}).get("status", {}).get("message", {})
        if msg:
            parts = msg.get("parts", [])
            text = "".join((p.get("text", "") for p in parts if "text" in p))
            assert "Moscow" in text, f"Response should mention Moscow, got: {text}"


class TestA2APushNotificationConfig:
    """Тесты Push Notification Config - строгая проверка."""

    @pytest.fixture
    async def flow_id(self, client):
        return "example_react"

    @pytest.mark.asyncio
    async def test_set_config_valid_response(self, client, flow_id):
        """CreateTaskPushNotificationConfig возвращает валидный конфиг."""
        task_id = str(uuid.uuid4())
        config_id = str(uuid.uuid4())
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "CreateTaskPushNotificationConfig",
                "params": {
                    "taskId": task_id,
                    "id": config_id, "url": "http://example.com/webhook",
                },
            },
        )
        data = resp.json()
        _validate_jsonrpc_response(data)
        result = data["result"]
        assert result["id"] == config_id
        assert "url" in result
        assert result.get("taskId")

    @pytest.mark.asyncio
    async def test_get_config_valid_response(self, client, flow_id):
        """GetTaskPushNotificationConfig возвращает конфиг или null."""
        task_id = str(uuid.uuid4())
        config_id = str(uuid.uuid4())
        await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "CreateTaskPushNotificationConfig",
                "params": {
                    "taskId": task_id,
                    "id": config_id, "url": "http://example.com",
                },
            },
        )
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "2",
                "method": "GetTaskPushNotificationConfig",
                "params": {"taskId": task_id, "id": config_id},
            },
        )
        data = resp.json()
        _validate_jsonrpc_response(data)
        if data["result"] is not None:
            assert "id" in data["result"] and "url" in data["result"]

    @pytest.mark.asyncio
    async def test_list_configs_valid_response(self, client, flow_id):
        """ListTaskPushNotificationConfigs возвращает список."""
        task_id = str(uuid.uuid4())
        for i in range(3):
            await client.post(
                f"/flows/api/v1/{flow_id}",
                headers=A2A_HEADERS,
                json={
                    "jsonrpc": "2.0",
                    "id": str(i),
                    "method": "CreateTaskPushNotificationConfig",
                    "params": {
                        "taskId": task_id,
                        "id": f"cfg-{i}",
                        "url": f"http://example.com/{i}",
                    },
                },
            )
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "list",
                "method": "ListTaskPushNotificationConfigs",
                "params": {"taskId": task_id},
            },
        )
        data = resp.json()
        _validate_jsonrpc_response(data)
        configs = data["result"].get("configs") if isinstance(data["result"], dict) else data["result"]
        assert isinstance(configs, list)
        assert len(configs) == 3

    @pytest.mark.asyncio
    async def test_delete_config_valid_response(self, client, flow_id):
        """DeleteTaskPushNotificationConfig возвращает null."""
        task_id = str(uuid.uuid4())
        config_id = str(uuid.uuid4())
        await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "CreateTaskPushNotificationConfig",
                "params": {
                    "taskId": task_id,
                    "id": config_id, "url": "http://example.com",
                },
            },
        )
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "2",
                "method": "DeleteTaskPushNotificationConfig",
                "params": {"taskId": task_id, "id": config_id},
            },
        )
        data = resp.json()
        _validate_jsonrpc_response(data)
        assert data["result"] is None


class TestA2ABranches:
    """CRUD веток — тот же `op_*`, что и WS. Чтение — GET flow."""

    @pytest.fixture
    async def flow_id(self, client):
        return "example_react"

    @pytest.mark.asyncio
    async def test_create_branch_valid(self, client, mutable_flow_id, unique_id):
        """POST /flows/{id}/branches создаёт новую ветку."""
        branch_id = f"test_branch_{unique_id}"
        resp = await client.post(
            f"/flows/api/v1/{mutable_flow_id}/branches",
            headers=A2A_HEADERS,
            json={
                "branch_id": branch_id,
                "name": "Test Branch",
                "description": "Test description",
                "tags": ["test"],
                "entry": "main",
                "variables": {"test_var": "test_value"},
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "success"
        assert data["branch_id"] == branch_id
        get_resp = await client.get(f"/flows/api/v1/flows/{mutable_flow_id}")
        assert get_resp.status_code == 200
        branch = get_resp.json()["branches"][branch_id]
        assert branch["name"] == "Test Branch"
        await client.delete(f"/flows/api/v1/{mutable_flow_id}/branches/{branch_id}")

    @pytest.mark.asyncio
    async def test_create_branch_duplicate(self, client, mutable_flow_id, unique_id):
        """POST /flows/{id}/branches возвращает 409 для существующей ветки."""
        branch_id = f"test_branch_dup_{unique_id}"
        resp1 = await client.post(
            f"/flows/api/v1/{mutable_flow_id}/branches",
            headers=A2A_HEADERS,
            json={"branch_id": branch_id, "name": "Test Branch"},
        )
        assert resp1.status_code == 201
        resp2 = await client.post(
            f"/flows/api/v1/{mutable_flow_id}/branches",
            headers=A2A_HEADERS,
            json={"branch_id": branch_id, "name": "Test Branch"},
        )
        assert resp2.status_code == 409
        await client.delete(f"/flows/api/v1/{mutable_flow_id}/branches/{branch_id}")

    @pytest.mark.asyncio
    async def test_create_branch_missing_branch_id(self, client, flow_id):
        """POST /flows/{id}/branches отклоняет payload без branch_id."""
        resp = await client.post(f"/flows/api/v1/{flow_id}/branches", json={"name": "Test Branch"})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_branch_forbidden_without_flow_edit(self, client, unique_id):
        """POST /branches без FGA can_edit (нет flow / нет tuples) — 403."""
        resp = await client.post(
            "/flows/api/v1/nonexistent_flow/branches",
            headers=A2A_HEADERS,
            json={"branch_id": f"test_branch_{unique_id}", "name": "Test Branch"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_update_branch_valid(self, client, mutable_flow_id, unique_id):
        """PUT /flows/{id}/branches/{branch_id} обновляет существующую ветку."""
        branch_id = f"test_branch_update_{unique_id}"
        create_resp = await client.post(
            f"/flows/api/v1/{mutable_flow_id}/branches",
            headers=A2A_HEADERS,
            json={
                "branch_id": branch_id,
                "name": "Original Name",
                "description": "Original description",
            },
        )
        assert create_resp.status_code == 201
        update_resp = await client.put(
            f"/flows/api/v1/{mutable_flow_id}/branches/{branch_id}",
            json={
                "name": "Updated Name",
                "description": "Updated description",
                "tags": ["updated"],
                "variables": {"updated_var": "updated_value"},
            },
        )
        assert update_resp.status_code == 200
        data = update_resp.json()
        assert data["status"] == "success"
        assert data["branch_id"] == branch_id
        get_resp = await client.get(f"/flows/api/v1/flows/{mutable_flow_id}")
        assert get_resp.status_code == 200
        branch = get_resp.json()["branches"][branch_id]
        assert branch["name"] == "Updated Name"
        assert branch["description"] == "Updated description"
        assert "updated" in branch["tags"]
        await client.delete(f"/flows/api/v1/{mutable_flow_id}/branches/{branch_id}")

    @pytest.mark.asyncio
    async def test_update_branch_404_for_nonexistent_branch(self, client, flow_id, unique_id):
        """PUT /flows/{id}/branches/{branch_id} возвращает 404 для несуществующей ветки."""
        resp = await client.put(
            f"/flows/api/v1/{flow_id}/branches/nonexistent_branch_{unique_id}",
            json={"name": "Test Branch"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_branch_forbidden_without_flow_edit(self, client, unique_id):
        """PUT /branches без FGA can_edit (нет flow / нет tuples) — 403."""
        resp = await client.put(
            f"/flows/api/v1/nonexistent_flow/branches/test_branch_{unique_id}",
            json={"name": "Test Branch"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_branch_valid(self, client, mutable_flow_id, unique_id):
        """DELETE /flows/{id}/branches/{branch_id} удаляет ветку."""
        branch_id = f"test_branch_delete_{unique_id}"
        create_resp = await client.post(
            f"/flows/api/v1/{mutable_flow_id}/branches",
            headers=A2A_HEADERS,
            json={"branch_id": branch_id, "name": "To Delete"},
        )
        assert create_resp.status_code == 201
        delete_resp = await client.delete(f"/flows/api/v1/{mutable_flow_id}/branches/{branch_id}")
        assert delete_resp.status_code == 200
        data = delete_resp.json()
        assert data["status"] == "success"
        assert data["branch_id"] == branch_id
        get_resp = await client.get(f"/flows/api/v1/flows/{mutable_flow_id}")
        assert get_resp.status_code == 200
        assert branch_id not in get_resp.json()["branches"]

    @pytest.mark.asyncio
    async def test_delete_branch_404_for_nonexistent_branch(self, client, flow_id, unique_id):
        """DELETE /flows/{id}/branches/{branch_id} возвращает 404 для несуществующей ветки."""
        resp = await client.delete(
            f"/flows/api/v1/{flow_id}/branches/nonexistent_branch_{unique_id}"
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_branch_forbidden_without_flow_edit(self, client, unique_id):
        """DELETE /branches без FGA can_edit (нет flow / нет tuples) — 403."""
        resp = await client.delete(
            f"/flows/api/v1/nonexistent_flow/branches/test_branch_{unique_id}"
        )
        assert resp.status_code == 403

    @pytest.fixture
    async def mutable_flow_id(self, container, unique_id):
        """Уникальный flow для тестов, мутирующих branches (изоляция от xdist)."""
        from apps.flows.src.models import FlowConfig
        from core.context import require_context

        fid = f"branch_test_{unique_id}"
        fc = FlowConfig(
            flow_id=fid,
            name="Branch mutation test",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Test"}},
            edges=[{"from_node": "main", "to_node": None}],
        )
        await container.flow_repository.set(fc)
        ctx = require_context()
        if ctx.active_company is None:
            raise AssertionError("active company required for flow authz sync")
        await container.flow_access_service.sync_flow_saved(
            fc,
            company_id=ctx.active_company.company_id,
            owner_user_id=ctx.user.user_id,
        )
        yield fid
        await container.flow_access_service.sync_flow_deleted(
            fid, company_id=ctx.active_company.company_id, branch_ids=[]
        )
        await container.flow_repository.delete(fid)

    @pytest.mark.asyncio
    async def test_create_branch_with_edges(self, client, mutable_flow_id, unique_id):
        """POST /flows/{id}/branches создаёт branch с edges."""
        branch_id = f"test_branch_edges_{unique_id}"
        resp = await client.post(
            f"/flows/api/v1/{mutable_flow_id}/branches",
            headers=A2A_HEADERS,
            json={
                "branch_id": branch_id,
                "name": "Test Branch with Edges",
                "entry": "node1",
                "nodes": {
                    "node1": {"type": "llm_node", "prompt": "Test prompt"},
                    "node2": {
                        "type": "code",
                        "code": "async def run(args, state):\n    state['result'] = 'ok'\n    return state",
                    },
                },
                "edges": [
                    {"from_node": "node1", "to_node": "node2"},
                    {"from_node": "node2", "to_node": None},
                ],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "success"
        get_resp = await client.get(f"/flows/api/v1/flows/{mutable_flow_id}")
        assert get_resp.status_code == 200
        assert branch_id in get_resp.json()["branches"]
        await client.delete(f"/flows/api/v1/{mutable_flow_id}/branches/{branch_id}")


class TestA2AConversation:
    """Тесты multi-turn conversation."""

    @pytest.fixture
    async def flow_id(self, client):
        return "example_react"

    @pytest.mark.asyncio
    async def test_multi_turn_preserves_context(
        self, client, flow_id, mock_llm_with_queue, sync_tools
    ):
        """Несколько Submit в одном contextId: отдельные Tasks, общий context."""
        mock_llm_with_queue(["First response", "Second response", "Third response"])
        context_id = str(uuid.uuid4())
        task_ids: list[str] = []
        for i in range(3):
            resp = await client.post(
                f"/flows/api/v1/{flow_id}",
                headers=A2A_HEADERS,
                json={
                    "jsonrpc": "2.0",
                    "id": str(i),
                    "method": "SendMessage",
                    "params": {"message": _msg(f"Message {i}", context_id=context_id)},
                },
            )
            data = resp.json()
            _validate_jsonrpc_response(data)
            task = data["result"]
            _validate_task(task)
            assert task["contextId"] == context_id
            task_ids.append(task["id"])
        assert len(set(task_ids)) == 3, "Each Submit creates a new task_id"

        list_resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "list",
                "method": "ListTasks",
                "params": {"contextId": context_id},
            },
        )
        list_data = list_resp.json()
        _validate_jsonrpc_response(list_data)
        listed = list_data["result"]["tasks"]
        assert len(listed) == 3
        assert {item["contextId"] for item in listed} == {context_id}

        get_resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "get",
                "method": "GetTask",
                "params": {"id": context_id},
            },
        )
        get_data = get_resp.json()
        _validate_jsonrpc_response(get_data)
        latest = get_data["result"]
        assert latest["contextId"] == context_id
        assert latest["id"] in task_ids
        history = latest.get("history") or []
        user_texts = [
            part.get("text")
            for message in history
            if message.get("role") == "ROLE_USER"
            for part in message.get("parts") or []
            if "text" in part
        ]
        assert "Message 0" in user_texts
        assert "Message 1" in user_texts
        assert "Message 2" in user_texts


class TestA2AJSONRPCErrors:
    """Тесты JSON-RPC ошибок."""

    @pytest.fixture
    async def flow_id(self, client):
        return "example_react"

    @pytest.mark.asyncio
    async def test_unknown_method_error(self, client, flow_id):
        """Неизвестный метод возвращает -32601."""
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={"jsonrpc": "2.0", "id": "1", "method": "unknown/method", "params": {}},
        )
        data = resp.json()
        _validate_jsonrpc_response(data)
        assert "error" in data
        assert data["error"]["code"] == -32601

    @pytest.mark.asyncio
    async def test_missing_params_error(self, client, flow_id):
        """Отсутствующие params для SendMessage."""
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={"jsonrpc": "2.0", "id": "1", "method": "SendMessage"},
        )
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == -32602

    @pytest.mark.asyncio
    async def test_invalid_message_format_error(self, client, flow_id):
        """Невалидный формат message."""
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "SendMessage",
                "params": {"message": "not_an_object"},
            },
        )
        data = resp.json()
        assert "error" in data


class TestA2AEdgeCases:
    """Edge cases."""

    @pytest.fixture
    async def flow_id(self, client):
        return "example_react"

    @pytest.mark.asyncio
    async def test_empty_message_handled(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """Пустое сообщение обрабатывается."""
        mock_llm_with_queue(["Handled empty"])
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "SendMessage",
                "params": {"message": _msg("")},
            },
        )
        data = resp.json()
        assert "result" in data or "error" in data

    @pytest.mark.asyncio
    async def test_special_characters_handled(
        self, client, flow_id, mock_llm_with_queue, sync_tools
    ):
        """Специальные символы обрабатываются."""
        mock_llm_with_queue(["Special handled"])
        special = "ураааа"
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "SendMessage",
                "params": {"message": _msg(special)},
            },
        )
        data = resp.json()
        _validate_jsonrpc_response(data)


class TestA2ARealisticStreaming:
    """
    Реалистичные тесты стриминга.

    Проверяем что MockLLM стримит контент несколькими artifact-чанками:
    - Контент приходит по частям (не одним куском)
    - Tool calls корректно обрабатываются
    - Все чанки одного ответа имеют одинаковый artifactId
    - События приходят в правильном порядке
    """

    pytestmark = pytest.mark.timeout(15, func_only=True)

    @pytest.fixture
    async def flow_id(self, client):
        return "example_react"

    @pytest.mark.asyncio
    async def test_stream_content_arrives_in_chunks(
        self, client, flow_id, mock_llm_with_queue, sync_tools
    ):
        """
        Контент приходит по частям через Redis Pub/Sub (in-memory в тестах).
        """
        long_response = (
            "This is a long response that should be streamed in multiple chunks by the mock LLM."
        )
        mock_llm_with_queue([{"type": "text", "content": long_response}])
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "stream-chunks",
                "method": "SendStreamingMessage",
                "params": {"message": _msg("Test streaming")},
            },
        )
        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        assert len(events) > 0, "Should receive events from Redis"
        # Flow UI also streams ui.document; LLM text is only name=response.
        response_events = [
            e
            for e in events
            if "artifactUpdate" in e.get("result", {})
            and (e.get("result", {}).get("artifactUpdate", {}).get("artifact") or {}).get("name")
            == "response"
        ]
        assert len(response_events) >= 2, (
            f"Expected multiple response artifact chunks, got {len(response_events)}"
        )
        full_text = ""
        for event in response_events:
            result = event.get("result", {}).get("artifactUpdate", {})
            parts = result.get("artifact", {}).get("parts", [])
            for part in parts:
                if "text" in part:
                    full_text += part.get("text", "")
        assert full_text == long_response

    @pytest.mark.asyncio
    async def test_stream_chunks_same_artifact_id(
        self, client, flow_id, mock_llm_with_queue, sync_tools
    ):
        """Все чанки LLM response имеют одинаковый artifactId."""
        mock_llm_with_queue(["Multiple chunks with same artifact ID test."])
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "artifact-id-test",
                "method": "SendStreamingMessage",
                "params": {"message": _msg("Test artifact ID consistency")},
            },
        )
        events = _parse_sse(resp.text)
        text_stream_events = [
            e
            for e in events
            if "artifactUpdate" in e.get("result", {})
            and (e.get("result", {}).get("artifactUpdate", {}).get("artifact") or {}).get("name")
            == "response"
        ]
        assert len(text_stream_events) >= 2, "Should have multiple text artifact chunks"
        artifact_ids = set()
        for event in text_stream_events:
            artifact_update = event.get("result", {}).get("artifactUpdate", {})
            artifact_id = artifact_update.get("artifact", {}).get("artifactId")
            if artifact_id:
                artifact_ids.add(artifact_id)
        assert len(artifact_ids) == 1, (
            f"All chunks should have same artifactId, got: {artifact_ids}"
        )

    @pytest.mark.asyncio
    async def test_stream_last_chunk_marked(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """Последний чанк LLM response помечен last_chunk=True."""
        mock_llm_with_queue(["Content with last chunk marker"])
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "last-chunk-test",
                "method": "SendStreamingMessage",
                "params": {"message": _msg("Check last chunk")},
            },
        )
        events = _parse_sse(resp.text)
        content_artifacts = [
            e
            for e in events
            if "artifactUpdate" in e.get("result", {})
            and (e.get("result", {}).get("artifactUpdate", {}).get("artifact") or {}).get("name")
            == "response"
        ]
        assert len(content_artifacts) >= 1, "Должен быть хотя бы один response artifact chunk"
        last_result = content_artifacts[-1].get("result", {}).get("artifactUpdate", {})
        assert last_result.get("lastChunk") is True, (
            "Last content artifact chunk should have lastChunk=True"
        )
        for event in content_artifacts[:-1]:
            result = event.get("result", {}).get("artifactUpdate", {})
            assert result.get("lastChunk") is not True, (
                "Intermediate content chunks should not have lastChunk=True"
            )

    @pytest.mark.asyncio
    async def test_stream_status_events(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """Stream содержит statusUpdate frames; boundary = TASK_STATE_*."""
        mock_llm_with_queue(["Test response"])
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "status-events",
                "method": "SendStreamingMessage",
                "params": {"message": _msg("Test status events")},
            },
        )
        events = _parse_sse(resp.text)
        status_events = [e for e in events if "statusUpdate" in e.get("result", {})]
        assert len(status_events) >= 1, "Should have at least one status event"
        final_events = [
            e for e in status_events
            if e.get("result", {}).get("statusUpdate", {}).get("status", {}).get("state")
            in ("TASK_STATE_COMPLETED", "TASK_STATE_FAILED", "TASK_STATE_CANCELED", "TASK_STATE_INPUT_REQUIRED")
        ]
        assert len(final_events) >= 1, "Should have final status event"

    @pytest.mark.asyncio
    async def test_stream_events_order(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """События приходят в правильном порядке: artifact chunks, затем final status."""
        mock_llm_with_queue(["Testing event order in stream"])
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "event-order",
                "method": "SendStreamingMessage",
                "params": {"message": _msg("Test order")},
            },
        )
        events = _parse_sse(resp.text)
        assert len(events) > 0, "Should receive events"
        last_result = events[-1].get("result", {})
        if "statusUpdate" in last_result:
            state = last_result.get("statusUpdate", {}).get("status", {}).get("state")
            assert state in (
                "TASK_STATE_COMPLETED",
                "TASK_STATE_FAILED",
                "TASK_STATE_CANCELED",
                "TASK_STATE_INPUT_REQUIRED",
            ), f"Last statusUpdate should be terminal/interrupt, got {state}"
        artifact_indices = [
            i
            for (i, e) in enumerate(events)
            if "artifactUpdate" in e.get("result", {})
        ]
        if artifact_indices:
            final_index = len(events) - 1
            for idx in artifact_indices:
                assert idx < final_index, "Artifact events should come before final event"

    @pytest.mark.asyncio
    async def test_stream_multi_turn_preserves_streaming(
        self, client, flow_id, mock_llm_with_queue, sync_tools
    ):
        """Multi-turn: каждый ответ стримится по частям."""
        context_id = str(uuid.uuid4())
        mock_llm_with_queue(
            ["First response with multiple tokens", "Second response also streams properly"]
        )
        resp1 = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "turn1",
                "method": "SendStreamingMessage",
                "params": {"message": _msg("First message", context_id=context_id)},
            },
        )
        events1 = _parse_sse(resp1.text)
        assert len(events1) > 0, "First turn should produce events"
        resp2 = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "turn2",
                "method": "SendStreamingMessage",
                "params": {"message": _msg("Second message", context_id=context_id)},
            },
        )
        events2 = _parse_sse(resp2.text)
        assert len(events2) > 0, "Second turn should also produce events"

    @pytest.mark.asyncio
    async def test_stream_task_context_ids_consistent(
        self, client, flow_id, mock_llm_with_queue, sync_tools
    ):
        """Все события имеют одинаковые taskId и contextId."""
        context_id = str(uuid.uuid4())
        mock_llm_with_queue(["Testing ID consistency across events"])
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            headers=A2A_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "id-consistency",
                "method": "SendStreamingMessage",
                "params": {"message": _msg("Check IDs", context_id=context_id)},
            },
        )
        events = _parse_sse(resp.text)
        assert len(events) > 0, "Should receive events"
        task_ids = set()
        context_ids = set()
        for event in events:
            result = event.get("result", {})
            if result.get("taskId"):
                task_ids.add(result["taskId"])
            if result.get("contextId"):
                context_ids.add(result["contextId"])
        if task_ids:
            assert len(task_ids) == 1, f"All events should have same taskId, got: {task_ids}"
        if context_ids:
            assert context_id in context_ids, f"Events should have requested contextId {context_id}"
