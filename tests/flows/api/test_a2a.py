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


def _msg(text: str, task_id: str = None, context_id: str = None) -> Dict[str, Any]:
    """Создаёт A2A Message с ОБЯЗАТЕЛЬНЫМИ полями по спецификации."""
    m = {
        "messageId": str(uuid.uuid4()),
        "role": "user",
        "parts": [{"kind": "text", "text": text}],
    }
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
    # Обязательные поля
    assert "id" in task, "Task MUST have 'id' field"
    assert isinstance(task["id"], str), "Task.id MUST be string"

    assert "contextId" in task, "Task MUST have 'contextId' field"
    assert isinstance(task["contextId"], str), "Task.contextId MUST be string"

    assert "status" in task, "Task MUST have 'status' field"
    _validate_task_status(task["status"])

    # kind должен быть 'task' если присутствует
    if "kind" in task:
        assert task["kind"] == "task", f"Task.kind MUST be 'task', got {task['kind']}"

    # history если требуется
    if require_history:
        assert "history" in task and task["history"] is not None, "Task MUST have history"
        assert isinstance(task["history"], list), "Task.history MUST be list"
        for msg in task["history"]:
            _validate_message(msg)


def _validate_task_status(status: Dict) -> None:
    """Строгая валидация TaskStatus по A2A SDK спецификации."""
    assert "state" in status, "TaskStatus MUST have 'state' field"

    valid_states = [
        "submitted", "working", "input-required", "auth-required",
        "completed", "failed", "rejected", "canceled", "unknown"
    ]
    assert status["state"] in valid_states, f"Invalid TaskState: {status['state']}"

    # message опционально, но если есть - должен быть валидным
    if "message" in status and status["message"] is not None:
        _validate_message(status["message"])


def _validate_message(msg: Dict) -> None:
    """Строгая валидация Message по A2A SDK спецификации."""
    assert "messageId" in msg, "Message MUST have 'messageId' field"
    assert isinstance(msg["messageId"], str), "Message.messageId MUST be string"

    assert "role" in msg, "Message MUST have 'role' field"
    assert msg["role"] in ["user", "agent"], f"Invalid role: {msg['role']}"

    assert "parts" in msg, "Message MUST have 'parts' field"
    assert isinstance(msg["parts"], list), "Message.parts MUST be list"
    assert len(msg["parts"]) > 0, "Message.parts MUST NOT be empty"

    for part in msg["parts"]:
        _validate_part(part)


def _validate_part(part: Dict) -> None:
    """Строгая валидация Part по A2A SDK спецификации."""
    # Part должен иметь kind или быть TextPart/FilePart/DataPart
    if "kind" in part:
        assert part["kind"] in ["text", "file", "data"], f"Invalid Part.kind: {part['kind']}"
        if part["kind"] == "text":
            assert "text" in part, "TextPart MUST have 'text' field"


def _validate_status_update_event(event: Dict) -> None:
    """Строгая валидация TaskStatusUpdateEvent по A2A SDK спецификации."""
    result = event.get("result", event)

    assert result.get("kind") == "status-update", "Event.kind MUST be 'status-update'"

    assert "taskId" in result, "TaskStatusUpdateEvent MUST have 'taskId'"
    assert isinstance(result["taskId"], str), "taskId MUST be string"

    assert "contextId" in result, "TaskStatusUpdateEvent MUST have 'contextId'"
    assert isinstance(result["contextId"], str), "contextId MUST be string"

    assert "final" in result, "TaskStatusUpdateEvent MUST have 'final'"
    assert isinstance(result["final"], bool), "final MUST be boolean"

    assert "status" in result, "TaskStatusUpdateEvent MUST have 'status'"
    _validate_task_status(result["status"])


def _validate_artifact_update_event(event: Dict) -> None:
    """Строгая валидация TaskArtifactUpdateEvent по A2A SDK спецификации."""
    result = event.get("result", event)

    assert result.get("kind") == "artifact-update", "Event.kind MUST be 'artifact-update'"

    assert "taskId" in result, "TaskArtifactUpdateEvent MUST have 'taskId'"
    assert "contextId" in result, "TaskArtifactUpdateEvent MUST have 'contextId'"
    assert "artifact" in result, "TaskArtifactUpdateEvent MUST have 'artifact'"


def _validate_jsonrpc_response(data: Dict) -> None:
    """Строгая валидация JSON-RPC 2.0 response."""
    assert "jsonrpc" in data, "JSON-RPC response MUST have 'jsonrpc' field"
    assert data["jsonrpc"] == "2.0", "jsonrpc MUST be '2.0'"

    assert "id" in data, "JSON-RPC response MUST have 'id' field"

    # Либо result, либо error
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

        # Обязательные поля по A2A спецификации
        assert "name" in card, "AgentCard MUST have 'name'"
        assert isinstance(card["name"], str), "AgentCard.name MUST be string"

        assert "url" in card, "AgentCard MUST have 'url'"
        assert isinstance(card["url"], str), f"AgentCard.url MUST be string, got: {card.get('url')}"

        assert "version" in card, "AgentCard MUST have 'version'"
        assert isinstance(card["version"], str), "AgentCard.version MUST be string"

        assert "capabilities" in card, "AgentCard MUST have 'capabilities'"
        assert isinstance(card["capabilities"], dict), "AgentCard.capabilities MUST be object"

        # Capabilities должны иметь определённые поля
        caps = card["capabilities"]
        assert "streaming" in caps, "Capabilities MUST have 'streaming'"
        assert isinstance(caps["streaming"], bool), "streaming MUST be boolean"

        assert "pushNotifications" in caps, "Capabilities MUST have 'pushNotifications'"
        assert isinstance(caps["pushNotifications"], bool), "pushNotifications MUST be boolean"

    @pytest.mark.asyncio
    async def test_agent_card_404(self, client):
        """Несуществующий flow возвращает 404."""
        resp = await client.get("/flows/api/v1/nonexistent_flow_xyz")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_agent_card_branches(self, client, flow_id):
        """Agent Card содержит branches в правильном формате."""
        resp = await client.get(f"/flows/api/v1/{flow_id}")
        card = resp.json()

        assert "branches" in card
        assert isinstance(card["branches"], list), "branches MUST be a list"
        for branch_entry in card["branches"]:
            assert "id" in branch_entry, "branch entry MUST have 'id'"
            assert "name" in branch_entry, "branch entry MUST have 'name'"


class TestA2AMessageSend:
    """Тесты message/send - строгая проверка Task response."""

    @pytest.fixture
    async def flow_id(self, client):
        return "example_react"

    @pytest.mark.asyncio
    async def test_message_send_returns_valid_task(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """message/send возвращает валидный Task по A2A спецификации."""
        mock_llm_with_queue(["Test response"])

        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "test-1",
                "method": "message/send",
                "params": {"message": _msg("Hello")},
            },
        )

        assert resp.status_code == 200

        data = resp.json()
        _validate_jsonrpc_response(data)

        assert "result" in data
        task = data["result"]
        _validate_task(task)

        # Проверяем что состояние completed
        assert task["status"]["state"] == "completed"

    @pytest.mark.asyncio
    async def test_message_send_with_context_id(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """message/send сохраняет переданный contextId."""
        mock_llm_with_queue(["Response"])

        context_id = str(uuid.uuid4())

        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "test-2",
                "method": "message/send",
                "params": {"message": _msg("Test", context_id=context_id)},
            },
        )

        data = resp.json()
        _validate_jsonrpc_response(data)

        task = data["result"]
        _validate_task(task)

        # contextId должен совпадать с переданным
        assert task["contextId"] == context_id

    @pytest.mark.asyncio
    async def test_message_send_history(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """message/send возвращает history с валидными Messages."""
        mock_llm_with_queue(["Agent response"])

        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "test-3",
                "method": "message/send",
                "params": {"message": _msg("User message")},
            },
        )

        data = resp.json()
        task = data["result"]
        _validate_task(task, require_history=True)

        # History должен содержать user и agent сообщения
        assert len(task["history"]) >= 2

        roles = [msg["role"] for msg in task["history"]]
        assert "user" in roles, "History MUST contain user message"
        assert "agent" in roles, "History MUST contain agent message"

    @pytest.mark.asyncio
    async def test_unknown_flow_error(self, client):
        """Неизвестный flow возвращает JSON-RPC ошибку."""
        resp = await client.post(
            "/flows/api/v1/unknown_flow_xyz",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/send",
                "params": {"message": _msg("Test")},
            },
        )

        # JSON-RPC возвращает ошибку в теле ответа, не через HTTP status
        assert resp.status_code == 200

        data = resp.json()
        _validate_jsonrpc_response(data)

        assert "error" in data, "Unknown flow MUST return JSON-RPC error"
        assert data["error"]["code"] == -32000  # Application error


class TestA2ATasksGet:
    """Тесты tasks/get - строгая проверка."""

    @pytest.fixture
    async def flow_id(self, client):
        return "example_react"

    @pytest.mark.asyncio
    async def test_tasks_get_returns_valid_task(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """tasks/get возвращает валидный Task."""
        mock_llm_with_queue(["Initial response"])

        context_id = str(uuid.uuid4())

        # Создаём задачу
        await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/send",
                "params": {"message": _msg("Create task", context_id=context_id)},
            },
        )

        # Получаем задачу
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "2",
                "method": "tasks/get",
                "params": {"id": context_id},
            },
        )

        data = resp.json()
        _validate_jsonrpc_response(data)

        task = data["result"]
        _validate_task(task)

    @pytest.mark.asyncio
    async def test_tasks_get_with_history_length(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """tasks/get с historyLength ограничивает историю."""
        mock_llm_with_queue([
            "Response 1",
            "Response 2",
            "Response 3",
        ])

        context_id = str(uuid.uuid4())

        # Несколько сообщений
        for i in range(3):
            await client.post(
                f"/flows/api/v1/{flow_id}",
                json={
                    "jsonrpc": "2.0",
                    "id": str(i),
                    "method": "message/send",
                    "params": {"message": _msg(f"Message {i}", context_id=context_id)},
                },
            )

        # Запрашиваем с historyLength=2
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "get",
                "method": "tasks/get",
                "params": {"id": context_id, "historyLength": 2},
            },
        )

        data = resp.json()
        task = data["result"]

        if task and task.get("history"):
            assert len(task["history"]) <= 2

    @pytest.mark.asyncio
    async def test_tasks_get_not_found(self, client, flow_id):
        """tasks/get для несуществующей задачи возвращает null."""
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tasks/get",
                "params": {"id": str(uuid.uuid4())},
            },
        )

        data = resp.json()
        _validate_jsonrpc_response(data)

        # result должен быть null для несуществующей задачи
        assert data["result"] is None


class TestA2ATasksCancel:
    """Тесты tasks/cancel - строгая проверка."""

    @pytest.fixture
    async def flow_id(self, client):
        return "example_react"

    @pytest.mark.asyncio
    async def test_tasks_cancel_returns_canceled_task(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """tasks/cancel возвращает Task со статусом canceled."""
        mock_llm_with_queue(["Response"])

        context_id = str(uuid.uuid4())

        await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/send",
                "params": {"message": _msg("Create", context_id=context_id)},
            },
        )

        # Cancel
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "2",
                "method": "tasks/cancel",
                "params": {"id": context_id},
            },
        )

        data = resp.json()
        _validate_jsonrpc_response(data)

        task = data["result"]
        _validate_task(task)

        # Статус должен быть canceled
        assert task["status"]["state"] == "canceled"


class TestA2AMessageStream:
    """Тесты message/stream - строгая проверка SSE событий."""

    @pytest.fixture
    async def flow_id(self, client):
        return "example_react"

    @pytest.mark.asyncio
    async def test_stream_returns_sse(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """message/stream возвращает SSE формат."""
        mock_llm_with_queue(["Streaming response"])

        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/stream",
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
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/stream",
                "params": {"message": _msg("Test events")},
            },
        )

        events = _parse_sse(resp.text)
        assert len(events) > 0, "Stream MUST contain events"

        for event in events:
            _validate_jsonrpc_response(event)

            result = event.get("result", {})
            kind = result.get("kind")

            if kind == "status-update":
                _validate_status_update_event(event)
            elif kind == "artifact-update":
                _validate_artifact_update_event(event)
            elif kind == "task":
                _validate_task(result)

    @pytest.mark.asyncio
    async def test_stream_has_final_event(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """Stream содержит финальное событие с final=true."""
        mock_llm_with_queue(["Final test"])

        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/stream",
                "params": {"message": _msg("Test final")},
            },
        )

        events = _parse_sse(resp.text)

        # Должно быть хотя бы одно событие с final=true
        final_events = [
            e for e in events
            if e.get("result", {}).get("final") is True
        ]
        assert len(final_events) > 0, "Stream MUST contain event with final=true"


class TestA2AInterrupt:
    """Тесты interrupt (input-required) - строгая проверка."""

    @pytest.fixture
    async def flow_id(self, client):
        # Используем example_react - у него есть ask_user tool
        return "example_react"

    @pytest.mark.asyncio
    async def test_interrupt_returns_input_required(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """ask_user возвращает Task со статусом input-required."""
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "Your name?"}},
        ])

        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/send",
                "params": {"message": _msg("Start")},
            },
        )

        data = resp.json()
        _validate_jsonrpc_response(data)

        task = data["result"]
        _validate_task(task)

        # Статус MUST быть input-required
        assert task["status"]["state"] == "input-required"

        # status.message должен содержать вопрос
        assert task["status"]["message"] is not None
        _validate_message(task["status"]["message"])

    @pytest.mark.asyncio
    async def test_resume_after_interrupt(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """Resume после interrupt возвращает completed."""
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "Name?"}},
            "Hello, John!",
        ])

        context_id = str(uuid.uuid4())

        # Первый запрос - interrupt
        r1 = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/send",
                "params": {"message": _msg("Start", context_id=context_id)},
            },
        )

        data1 = r1.json()
        assert data1["result"]["status"]["state"] == "input-required"

        # Resume
        r2 = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "2",
                "method": "message/send",
                "params": {"message": _msg("John", context_id=context_id)},
            },
        )

        data2 = r2.json()
        _validate_jsonrpc_response(data2)

        task2 = data2["result"]
        _validate_task(task2)

        # После resume - completed
        assert task2["status"]["state"] == "completed"

    @pytest.mark.asyncio
    async def test_tasks_get_shows_input_required(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """tasks/get показывает input-required состояние."""
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "Age?"}},
        ])

        context_id = str(uuid.uuid4())

        await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/send",
                "params": {"message": _msg("Start", context_id=context_id)},
            },
        )

        # tasks/get должен вернуть input-required
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "2",
                "method": "tasks/get",
                "params": {"id": context_id},
            },
        )

        data = resp.json()
        task = data["result"]

        assert task["status"]["state"] == "input-required"

    @pytest.mark.asyncio
    async def test_stream_interrupt_has_input_required_event(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """Stream с interrupt содержит событие input-required."""
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "Question?"}},
        ])

        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/stream",
                "params": {"message": _msg("Stream interrupt")},
            },
        )

        events = _parse_sse(resp.text)

        # Должно быть событие с input-required
        input_required = [
            e for e in events
            if e.get("result", {}).get("status", {}).get("state") == "input-required"
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
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "What is your name?"}},
            "Hello, TestUser! Nice to meet you.",
        ])

        context_id = str(uuid.uuid4())

        # ШАГ 1: Первый запрос - должен вернуть input-required
        r1 = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/send",
                "params": {"message": _msg("Hello", context_id=context_id)},
            },
        )

        data1 = r1.json()
        _validate_jsonrpc_response(data1)

        task1 = data1["result"]
        _validate_task(task1)

        # ПРОВЕРКА 1: Статус MUST быть input-required
        assert task1["status"]["state"] == "input-required", \
            f"First request MUST return input-required, got: {task1['status']['state']}"

        # ПРОВЕРКА 2: Должен быть task_id
        first_task_id = task1["id"]
        assert first_task_id, "Task MUST have id"

        # ПРОВЕРКА 3: Вопрос должен быть в message
        assert task1["status"]["message"] is not None, "input-required MUST have message"
        question_parts = task1["status"]["message"]["parts"]
        question_text = "".join(
            p.get("text", "") for p in question_parts if p.get("kind") == "text"
        )
        assert "name" in question_text.lower(), \
            f"Question should ask about name, got: {question_text}"

        # ШАГ 2: Resume - отвечаем на вопрос
        r2 = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "2",
                "method": "message/send",
                "params": {"message": _msg("TestUser", context_id=context_id)},
            },
        )

        data2 = r2.json()
        _validate_jsonrpc_response(data2)

        task2 = data2["result"]
        _validate_task(task2)

        # ПРОВЕРКА 4: После resume статус MUST быть completed
        assert task2["status"]["state"] == "completed", \
            f"Resume MUST return completed, got: {task2['status']['state']}"

        # ПРОВЕРКА 5: task_id должен быть тот же самый
        assert task2["id"] == first_task_id, \
            f"Task ID MUST be preserved across interrupt/resume. First: {first_task_id}, Resume: {task2['id']}"

        # ПРОВЕРКА 6: Ответ должен содержать текст от LLM
        assert task2["status"]["message"] is not None, "completed MUST have message"
        response_parts = task2["status"]["message"]["parts"]
        response_text = "".join(
            p.get("text", "") for p in response_parts if p.get("kind") == "text"
        )
        assert "TestUser" in response_text, \
            f"Response should contain user name, got: {response_text}"
        assert "Hello" in response_text or "Nice" in response_text, \
            f"Response should contain greeting, got: {response_text}"

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
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "City?"}},
            "Moscow is a great city!",
        ])

        context_id = str(uuid.uuid4())

        # ШАГ 1: Первый stream - interrupt
        r1 = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/stream",
                "params": {"message": _msg("Start", context_id=context_id)},
            },
        )

        events1 = _parse_sse(r1.text)

        # ПРОВЕРКА 1: Должно быть input-required событие
        input_required_events = [
            e for e in events1
            if e.get("result", {}).get("status", {}).get("state") == "input-required"
        ]
        assert len(input_required_events) > 0, \
            "First stream MUST contain input-required event"

        # ШАГ 2: Resume stream
        r2 = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "2",
                "method": "message/stream",
                "params": {"message": _msg("Moscow", context_id=context_id)},
            },
        )

        events2 = _parse_sse(r2.text)

        # ПРОВЕРКА 2: Должно быть completed событие
        completed_events = [
            e for e in events2
            if e.get("result", {}).get("status", {}).get("state") == "completed"
        ]
        assert len(completed_events) > 0, \
            f"Resume stream MUST contain completed event. Got events: {[e.get('result', {}).get('status', {}).get('state') for e in events2]}"

        # ПРОВЕРКА 3: Ответ должен содержать "Moscow"
        completed = completed_events[-1]
        msg = completed.get("result", {}).get("status", {}).get("message", {})
        if msg:
            parts = msg.get("parts", [])
            text = "".join(p.get("text", "") for p in parts if p.get("kind") == "text")
            assert "Moscow" in text, \
                f"Response should mention Moscow, got: {text}"


class TestA2APushNotificationConfig:
    """Тесты Push Notification Config - строгая проверка."""

    @pytest.fixture
    async def flow_id(self, client):
        return "example_react"

    @pytest.mark.asyncio
    async def test_set_config_valid_response(self, client, flow_id):
        """tasks/pushNotificationConfig/set возвращает валидный конфиг."""
        task_id = str(uuid.uuid4())
        config_id = str(uuid.uuid4())

        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tasks/pushNotificationConfig/set",
                "params": {
                    "taskId": task_id,
                    "pushNotificationConfig": {
                        "id": config_id,
                        "url": "http://example.com/webhook",
                    },
                },
            },
        )

        data = resp.json()
        _validate_jsonrpc_response(data)

        result = data["result"]
        assert "pushNotificationConfig" in result

        config = result["pushNotificationConfig"]
        assert config["id"] == config_id
        assert "url" in config

    @pytest.mark.asyncio
    async def test_get_config_valid_response(self, client, flow_id):
        """tasks/pushNotificationConfig/get возвращает конфиг или null."""
        task_id = str(uuid.uuid4())
        config_id = str(uuid.uuid4())

        # Сначала создаём
        await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tasks/pushNotificationConfig/set",
                "params": {
                    "taskId": task_id,
                    "pushNotificationConfig": {"id": config_id, "url": "http://example.com"},
                },
            },
        )

        # Получаем
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "2",
                "method": "tasks/pushNotificationConfig/get",
                "params": {"id": task_id, "pushNotificationConfigId": config_id},
            },
        )

        data = resp.json()
        _validate_jsonrpc_response(data)

        # result может быть конфигом или null
        if data["result"] is not None:
            assert "pushNotificationConfig" in data["result"]

    @pytest.mark.asyncio
    async def test_list_configs_valid_response(self, client, flow_id):
        """tasks/pushNotificationConfig/list возвращает список."""
        task_id = str(uuid.uuid4())

        # Создаём несколько конфигов
        for i in range(3):
            await client.post(
                f"/flows/api/v1/{flow_id}",
                json={
                    "jsonrpc": "2.0",
                    "id": str(i),
                    "method": "tasks/pushNotificationConfig/set",
                    "params": {
                        "taskId": task_id,
                        "pushNotificationConfig": {"id": f"cfg-{i}", "url": f"http://example.com/{i}"},
                    },
                },
            )

        # Получаем список
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "list",
                "method": "tasks/pushNotificationConfig/list",
                "params": {"id": task_id},
            },
        )

        data = resp.json()
        _validate_jsonrpc_response(data)

        assert isinstance(data["result"], list)
        assert len(data["result"]) == 3

    @pytest.mark.asyncio
    async def test_delete_config_valid_response(self, client, flow_id):
        """tasks/pushNotificationConfig/delete возвращает null."""
        task_id = str(uuid.uuid4())
        config_id = str(uuid.uuid4())

        # Создаём
        await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tasks/pushNotificationConfig/set",
                "params": {
                    "taskId": task_id,
                    "pushNotificationConfig": {"id": config_id, "url": "http://example.com"},
                },
            },
        )

        # Удаляем
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "2",
                "method": "tasks/pushNotificationConfig/delete",
                "params": {"id": task_id, "pushNotificationConfigId": config_id},
            },
        )

        data = resp.json()
        _validate_jsonrpc_response(data)

        # DELETE возвращает null
        assert data["result"] is None


class TestA2ASkills:
    """Тесты skills endpoints."""

    @pytest.fixture
    async def flow_id(self, client):
        # Используем example_react - у него есть полноценная поддержка skills
        return "example_react"

    @pytest.mark.asyncio
    async def test_list_skills_valid_response(self, client, flow_id):
        """GET /flows/{id}/skills возвращает список skills."""
        resp = await client.get(f"/flows/api/v1/{flow_id}/branches")
        assert resp.status_code == 200

        skills = resp.json()
        assert isinstance(skills, list)
        assert len(skills) > 0, "Agent MUST have at least one skill"

        for skill in skills:
            assert "id" in skill, "Skill MUST have 'id'"
            assert "name" in skill, "Skill MUST have 'name'"

    @pytest.mark.asyncio
    async def test_get_skill_valid_response(self, client, flow_id):
        """GET /flows/{id}/branches/{branch_id} возвращает skill."""
        # Сначала получаем список skills
        list_resp = await client.get(f"/flows/api/v1/{flow_id}/branches")
        skills = list_resp.json()
        assert len(skills) > 0, "Agent MUST have at least one skill"

        # Берём первый skill
        branch_id = skills[0]["id"]

        resp = await client.get(f"/flows/api/v1/{flow_id}/branches/{branch_id}")
        assert resp.status_code == 200

        skill = resp.json()
        assert "id" in skill, "Skill MUST have 'id'"
        assert "name" in skill, "Skill MUST have 'name'"
        assert skill["id"] == branch_id

    @pytest.mark.asyncio
    async def test_get_skill_tools_react_flow(self, client):
        """GET /flows/{id}/branches/{branch_id}/tools для react flow возвращает tools."""
        flow_id = "example_react"
        branch_id = "concise"

        resp = await client.get(f"/flows/api/v1/{flow_id}/branches/{branch_id}/tools")
        assert resp.status_code == 200

        tools = resp.json()
        assert isinstance(tools, list), "Tools MUST be a list"
        assert len(tools) > 0, "React flow MUST have tools"

        # Проверяем формат registry API
        for tool in tools:
            assert "name" in tool, "Tool MUST have 'name'"
            assert "type" in tool, "Tool MUST have 'type'"
            assert "attributes" in tool, "Tool MUST have 'attributes'"
            assert "description" in tool["attributes"], "Tool attributes MUST have 'description'"
            assert tool["type"] == "function", "React flow tools MUST be 'function' type"

    @pytest.mark.asyncio
    async def test_get_skill_tools_graph_flow(self, client):
        """GET /flows/{id}/branches/{branch_id}/tools для графового flow возвращает tools, nodes и edges."""
        flow_id = "example_graph"
        branch_id = "fast_track"

        resp = await client.get(f"/flows/api/v1/{flow_id}/branches/{branch_id}/tools")
        assert resp.status_code == 200

        items = resp.json()
        assert isinstance(items, list), "Tools MUST be a list"
        assert len(items) > 0, "Graph flow MUST have items"

        # Проверяем наличие nodes и edges (графовый агент может не иметь function tools)
        types = {item["type"] for item in items}
        assert "node" in types, "Graph flow MUST have nodes"
        assert "edge" in types, "Graph flow MUST have edges"

        # Проверяем формат nodes
        nodes = [item for item in items if item["type"] == "node"]
        assert len(nodes) > 0, "Graph flow MUST have nodes"
        for node in nodes:
            assert "name" in node, "Node MUST have 'name'"
            assert "attributes" in node, "Node MUST have 'attributes'"
            assert "node_type" in node["attributes"], "Node attributes MUST have 'node_type'"
            assert "node_name" in node["attributes"], "Node attributes MUST have 'node_name'"

        # Проверяем формат edges
        edges = [item for item in items if item["type"] == "edge"]
        assert len(edges) > 0, "Graph flow MUST have edges"
        for edge in edges:
            assert "name" in edge, "Edge MUST have 'name'"
            assert "attributes" in edge, "Edge MUST have 'attributes'"
            assert "from_node" in edge["attributes"], "Edge attributes MUST have 'from_node'"
            assert "to_node" in edge["attributes"], "Edge attributes MUST have 'to_node'"
            assert "->" in edge["name"], "Edge name MUST contain '->'"

    @pytest.mark.asyncio
    async def test_get_skill_tools_includes_all_llm_node_nodes(self, client):
        """Проверяет, что tools собираются из всех llm_node нод."""
        flow_id = "example_graph"
        branch_id = "fast_track"

        resp = await client.get(f"/flows/api/v1/{flow_id}/branches/{branch_id}/tools")
        assert resp.status_code == 200

        items = resp.json()

        # Проверяем что возвращаются items (nodes, edges, и возможно function tools)
        assert len(items) > 0, "MUST have items"

        # Должны быть все ноды графа
        nodes = [item for item in items if item["type"] == "node"]
        assert len(nodes) > 0, "MUST have nodes"

        # Проверяем что есть edges
        edges = [item for item in items if item["type"] == "edge"]
        assert len(edges) > 0, "MUST have edges"

    @pytest.mark.asyncio
    async def test_get_skill_tools_404_for_nonexistent_flow(self, client):
        """GET /flows/{id}/branches/{branch_id}/tools возвращает 404 для несуществующего flow."""
        resp = await client.get("/flows/api/v1/nonexistent_flow/branches/default/tools")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_skill_tools_404_for_nonexistent_skill(self, client):
        """GET /flows/{id}/branches/{branch_id}/tools возвращает 404 для несуществующего skill."""
        flow_id = "example_react"
        resp = await client.get(f"/flows/api/v1/{flow_id}/branches/nonexistent_skill/tools")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_skill_schema_valid_response(self, client):
        """GET /flows/{id}/schema возвращает JSON Schema в формате ISchema."""
        flow_id = "example_react"

        resp = await client.get(f"/flows/api/v1/{flow_id}/schema")
        assert resp.status_code == 200

        schema = resp.json()

        # Проверяем все обязательные поля ISchema
        assert "type" in schema, "Schema MUST have 'type' field"
        assert schema["type"] == "object", "Schema type MUST be 'object'"

        assert "title" in schema, "Schema MUST have 'title' field"
        assert isinstance(schema["title"], str), "Schema title MUST be string"

        assert "$schema" in schema, "Schema MUST have '$schema' field"
        assert isinstance(schema["$schema"], str), "Schema $schema MUST be string"

        assert "properties" in schema, "Schema MUST have 'properties' field"
        assert isinstance(schema["properties"], dict), "Schema properties MUST be dict"

        assert "required" in schema, "Schema MUST have 'required' field"
        assert isinstance(schema["required"], list), "Schema required MUST be list"

        assert "additionalProperties" in schema, "Schema MUST have 'additionalProperties' field"
        assert isinstance(schema["additionalProperties"], bool), "Schema additionalProperties MUST be boolean"

    @pytest.mark.asyncio
    async def test_get_skill_schema_404_for_nonexistent_flow(self, client):
        """GET /flows/{id}/schema возвращает 404 для несуществующего flow."""
        resp = await client.get("/flows/api/v1/nonexistent_flow/schema")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_skill_valid(self, client, mutable_flow_id, unique_id):
        """POST /flows/{id}/skills создаёт новый skill."""
        branch_id = f"test_skill_{unique_id}"

        resp = await client.post(
            f"/flows/api/v1/{mutable_flow_id}/branches",
            json={
                "branch_id": branch_id,
                "name": "Test Skill",
                "description": "Test description",
                "tags": ["test"],
                "skill_body": {
                    "entry": "main",
                    "variables": {"test_var": "test_value"},
                },
            },
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "success"
        assert data["branch_id"] == branch_id

        get_resp = await client.get(f"/flows/api/v1/{mutable_flow_id}/branches/{branch_id}")
        assert get_resp.status_code == 200
        skill = get_resp.json()
        assert skill["id"] == branch_id
        assert skill["name"] == "Test Skill"

        await client.delete(f"/flows/api/v1/{mutable_flow_id}/branches/{branch_id}")

    @pytest.mark.asyncio
    async def test_create_skill_duplicate(self, client, mutable_flow_id, unique_id):
        """POST /flows/{id}/skills возвращает 409 для существующего skill."""
        branch_id = f"test_skill_dup_{unique_id}"

        resp1 = await client.post(
            f"/flows/api/v1/{mutable_flow_id}/branches",
            json={
                "branch_id": branch_id,
                "name": "Test Skill",
            },
        )
        assert resp1.status_code == 201

        resp2 = await client.post(
            f"/flows/api/v1/{mutable_flow_id}/branches",
            json={
                "branch_id": branch_id,
                "name": "Test Skill",
            },
        )
        assert resp2.status_code == 409

        await client.delete(f"/flows/api/v1/{mutable_flow_id}/branches/{branch_id}")

    @pytest.mark.asyncio
    async def test_create_skill_missing_skill_id(self, client, flow_id):
        """POST /flows/{id}/skills возвращает 400 без branch_id."""
        resp = await client.post(
            f"/flows/api/v1/{flow_id}/branches",
            json={
                "name": "Test Skill",
            },
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_create_skill_404_for_nonexistent_flow(self, client, unique_id):
        """POST /flows/{id}/skills возвращает 404 для несуществующего flow."""
        resp = await client.post(
            "/flows/api/v1/nonexistent_flow/branches",
            json={
                "branch_id": f"test_skill_{unique_id}",
                "name": "Test Skill",
            },
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_skill_valid(self, client, mutable_flow_id, unique_id):
        """PUT /flows/{id}/branches/{branch_id} обновляет существующий skill."""
        branch_id = f"test_skill_update_{unique_id}"

        create_resp = await client.post(
            f"/flows/api/v1/{mutable_flow_id}/branches",
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
                "branch_id": branch_id,
                "name": "Updated Name",
                "description": "Updated description",
                "tags": ["updated"],
                "skill_body": {
                    "variables": {"updated_var": "updated_value"},
                },
            },
        )
        assert update_resp.status_code == 200
        data = update_resp.json()
        assert data["status"] == "success"
        assert data["branch_id"] == branch_id

        get_resp = await client.get(f"/flows/api/v1/{mutable_flow_id}/branches/{branch_id}")
        assert get_resp.status_code == 200
        skill = get_resp.json()
        assert skill["name"] == "Updated Name"
        assert skill["description"] == "Updated description"
        assert "updated" in skill["tags"]

        await client.delete(f"/flows/api/v1/{mutable_flow_id}/branches/{branch_id}")

    @pytest.mark.asyncio
    async def test_update_skill_404_for_nonexistent_skill(self, client, flow_id, unique_id):
        """PUT /flows/{id}/branches/{branch_id} возвращает 404 для несуществующего skill."""
        resp = await client.put(
            f"/flows/api/v1/{flow_id}/branches/nonexistent_skill_{unique_id}",
            json={
                "branch_id": f"nonexistent_skill_{unique_id}",
                "name": "Test Skill",
            },
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_skill_404_for_nonexistent_flow(self, client, unique_id):
        """PUT /flows/{id}/branches/{branch_id} возвращает 404 для несуществующего flow."""
        resp = await client.put(
            f"/flows/api/v1/nonexistent_flow/branches/test_skill_{unique_id}",
            json={
                "branch_id": f"test_skill_{unique_id}",
                "name": "Test Skill",
            },
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_skill_valid(self, client, mutable_flow_id, unique_id):
        """DELETE /flows/{id}/branches/{branch_id} удаляет skill."""
        branch_id = f"test_skill_delete_{unique_id}"

        create_resp = await client.post(
            f"/flows/api/v1/{mutable_flow_id}/branches",
            json={
                "branch_id": branch_id,
                "name": "To Delete",
            },
        )
        assert create_resp.status_code == 201

        delete_resp = await client.delete(f"/flows/api/v1/{mutable_flow_id}/branches/{branch_id}")
        assert delete_resp.status_code == 200
        data = delete_resp.json()
        assert data["status"] == "success"
        assert data["branch_id"] == branch_id

        get_resp = await client.get(f"/flows/api/v1/{mutable_flow_id}/branches/{branch_id}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_skill_404_for_nonexistent_skill(self, client, flow_id, unique_id):
        """DELETE /flows/{id}/branches/{branch_id} возвращает 404 для несуществующего skill."""
        resp = await client.delete(f"/flows/api/v1/{flow_id}/branches/nonexistent_skill_{unique_id}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_skill_404_for_nonexistent_flow(self, client, unique_id):
        """DELETE /flows/{id}/branches/{branch_id} возвращает 404 для несуществующего flow."""
        resp = await client.delete(f"/flows/api/v1/nonexistent_flow/branches/test_skill_{unique_id}")
        assert resp.status_code == 404

    @pytest.fixture
    async def mutable_flow_id(self, container, unique_id):
        """Уникальный flow для тестов, мутирующих skills (изоляция от xdist)."""
        from apps.flows.src.models import FlowConfig
        fid = f"skill_test_{unique_id}"
        fc = FlowConfig(
            flow_id=fid,
            name="Skill mutation test",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Test"}},
            edges=[{"from": "main", "to": None}],
        )
        await container.flow_repository.set(fc)
        yield fid
        await container.flow_repository.delete(fid)

    @pytest.mark.asyncio
    async def test_create_skill_with_edges(self, client, mutable_flow_id, unique_id):
        """POST /flows/{id}/skills создаёт skill с edges."""
        branch_id = f"test_skill_edges_{unique_id}"

        resp = await client.post(
            f"/flows/api/v1/{mutable_flow_id}/branches",
            json={
                "branch_id": branch_id,
                "name": "Test Skill with Edges",
                "skill_body": {
                    "entry": "node1",
                    "nodes": {
                        "node1": {"type": "llm_node", "prompt": "Test prompt"},
                        "node2": {"type": "code", "code": "async def run(state):\n    state['result'] = 'ok'\n    return state"},
                    },
                    "edges": [
                        {"from": "node1", "to": "node2"},
                        {"from": "node2", "to": None},
                    ],
                },
            },
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "success"

        get_resp = await client.get(f"/flows/api/v1/{mutable_flow_id}/branches/{branch_id}")
        assert get_resp.status_code == 200

        await client.delete(f"/flows/api/v1/{mutable_flow_id}/branches/{branch_id}")


class TestA2AConversation:
    """Тесты multi-turn conversation."""

    @pytest.fixture
    async def flow_id(self, client):
        return "example_react"

    @pytest.mark.asyncio
    async def test_multi_turn_preserves_context(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """Несколько сообщений в одном contextId сохраняют историю."""
        mock_llm_with_queue([
            "First response",
            "Second response",
            "Third response",
        ])

        context_id = str(uuid.uuid4())

        for i in range(3):
            resp = await client.post(
                f"/flows/api/v1/{flow_id}",
                json={
                    "jsonrpc": "2.0",
                    "id": str(i),
                    "method": "message/send",
                    "params": {"message": _msg(f"Message {i}", context_id=context_id)},
                },
            )

            data = resp.json()
            _validate_jsonrpc_response(data)
            _validate_task(data["result"])

        # Проверяем историю через tasks/get
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "get",
                "method": "tasks/get",
                "params": {"id": context_id},
            },
        )

        data = resp.json()
        task = data["result"]

        if task and task.get("history"):
            # История должна содержать все сообщения
            assert len(task["history"]) >= 6  # 3 user + 3 agent


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
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "unknown/method",
                "params": {},
            },
        )

        data = resp.json()
        _validate_jsonrpc_response(data)

        assert "error" in data
        assert data["error"]["code"] == -32601  # Method not found

    @pytest.mark.asyncio
    async def test_missing_params_error(self, client, flow_id):
        """Отсутствующие params для message/send."""
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/send",
            },
        )

        data = resp.json()
        assert "error" in data

    @pytest.mark.asyncio
    async def test_invalid_message_format_error(self, client, flow_id):
        """Невалидный формат message."""
        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/send",
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
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/send",
                "params": {"message": _msg("")},
            },
        )

        data = resp.json()
        # Должен быть либо result, либо error - но не crash
        assert "result" in data or "error" in data

    @pytest.mark.asyncio
    async def test_special_characters_handled(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """Специальные символы обрабатываются."""
        mock_llm_with_queue(["Special handled"])

        special = "ураааа"

        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/send",
                "params": {"message": _msg(special)},
            },
        )

        data = resp.json()
        _validate_jsonrpc_response(data)


class TestA2ARealisticStreaming:
    """
    Реалистичные тесты стриминга.

    Проверяем что MockLLM стримит по токенам как настоящая LLM:
    - Контент приходит по частям (не одним куском)
    - Tool calls корректно обрабатываются
    - Все чанки одного ответа имеют одинаковый artifactId
    - События приходят в правильном порядке
    """

    pytestmark = pytest.mark.timeout(15, func_only=True)

    @pytest.fixture
    async def flow_id(self, client):
        # Используем фиксированный агент для стабильности тестов
        return "example_react"

    @pytest.mark.asyncio
    async def test_stream_content_arrives_in_chunks(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """
        Контент приходит по частям через Redis Pub/Sub (in-memory в тестах).
        """
        long_response = "This is a long response that should be streamed in multiple chunks by the mock LLM."
        mock_llm_with_queue([{"type": "text", "content": long_response}])

        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "stream-chunks",
                "method": "message/stream",
                "params": {"message": _msg("Test streaming")},
            },
        )

        assert resp.status_code == 200
        events = _parse_sse(resp.text)

        # Должны получить события
        assert len(events) > 0, "Should receive events from Redis"

        # Фильтруем artifact-update события
        artifact_events = [e for e in events if e.get("result", {}).get("kind") == "artifact-update"]

        # Должны быть чанки текста (MockLLM стримит по 3 символа)
        assert len(artifact_events) >= 5, f"Expected multiple artifact chunks, got {len(artifact_events)}"

        # Собираем полный текст из чанков
        full_text = ""
        for event in artifact_events:
            result = event.get("result", {})
            parts = result.get("artifact", {}).get("parts", [])
            for part in parts:
                if part.get("kind") == "text":
                    full_text += part.get("text", "")

        # Полный текст должен совпадать
        assert full_text == long_response

    @pytest.mark.asyncio
    async def test_stream_chunks_same_artifact_id(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """Все чанки одного ответа имеют одинаковый artifactId."""
        mock_llm_with_queue(["Multiple chunks with same artifact ID test."])

        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "artifact-id-test",
                "method": "message/stream",
                "params": {"message": _msg("Test artifact ID consistency")},
            },
        )

        events = _parse_sse(resp.text)
        artifact_events = [e for e in events if e.get("result", {}).get("kind") == "artifact-update"]
        text_stream_events = [
            e
            for e in artifact_events
            if not str((e.get("result", {}).get("artifact") or {}).get("name") or "").startswith(
                "node_"
            )
            and any(
                p.get("kind") == "text"
                for p in (e.get("result", {}).get("artifact") or {}).get("parts", [])
            )
        ]

        assert len(text_stream_events) >= 2, "Should have multiple text artifact chunks"

        artifact_ids = set()
        for event in text_stream_events:
            result = event.get("result", {})
            artifact_id = result.get("artifact", {}).get("artifactId")
            if artifact_id:
                artifact_ids.add(artifact_id)

        assert len(artifact_ids) == 1, f"All chunks should have same artifactId, got: {artifact_ids}"

    @pytest.mark.asyncio
    async def test_stream_last_chunk_marked(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """Последний чанк контента помечен last_chunk=True."""
        mock_llm_with_queue(["Content with last chunk marker"])

        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "last-chunk-test",
                "method": "message/stream",
                "params": {"message": _msg("Check last chunk")},
            },
        )

        events = _parse_sse(resp.text)
        artifact_events = [e for e in events if e.get("result", {}).get("kind") == "artifact-update"]
        content_artifacts = [
            e
            for e in artifact_events
            if not str((e.get("result", {}).get("artifact") or {}).get("name") or "").startswith(
                "node_"
            )
        ]

        assert len(content_artifacts) >= 1, "Должен быть хотя бы один контентный artifact chunk"

        last_result = content_artifacts[-1].get("result", {})
        assert last_result.get("lastChunk") is True, "Last content artifact chunk should have lastChunk=True"

        for event in content_artifacts[:-1]:
            result = event.get("result", {})
            assert result.get("lastChunk") is not True, "Intermediate content chunks should not have lastChunk=True"

    @pytest.mark.asyncio
    async def test_stream_status_events(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """Stream содержит status-update события с финальным final=True."""
        mock_llm_with_queue(["Test response"])

        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "status-events",
                "method": "message/stream",
                "params": {"message": _msg("Test status events")},
            },
        )

        events = _parse_sse(resp.text)

        # Должны быть status-update события
        status_events = [e for e in events if e.get("result", {}).get("kind") == "status-update"]
        assert len(status_events) >= 1, "Should have at least one status event"

        # Финальное событие должно быть с final=True
        final_events = [e for e in status_events if e.get("result", {}).get("final") is True]
        assert len(final_events) >= 1, "Should have final status event"

    @pytest.mark.asyncio
    async def test_stream_events_order(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """События приходят в правильном порядке: artifact chunks, затем final status."""
        mock_llm_with_queue(["Testing event order in stream"])

        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "event-order",
                "method": "message/stream",
                "params": {"message": _msg("Test order")},
            },
        )

        events = _parse_sse(resp.text)
        assert len(events) > 0, "Should receive events"

        # Последнее событие должно быть status-update с final=True или task
        last_result = events[-1].get("result", {})
        last_kind = last_result.get("kind")

        # Может быть task или status-update
        if last_kind == "status-update":
            assert last_result.get("final") is True, "Last status-update should be final"

        # artifact events должны быть до финального события
        artifact_indices = [i for i, e in enumerate(events) if e.get("result", {}).get("kind") == "artifact-update"]
        if artifact_indices:
            final_index = len(events) - 1
            for idx in artifact_indices:
                assert idx < final_index, "Artifact events should come before final event"

    @pytest.mark.asyncio
    async def test_stream_multi_turn_preserves_streaming(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """Multi-turn: каждый ответ стримится по частям."""
        context_id = str(uuid.uuid4())

        mock_llm_with_queue([
            "First response with multiple tokens",
            "Second response also streams properly",
        ])

        resp1 = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "turn1",
                "method": "message/stream",
                "params": {"message": _msg("First message", context_id=context_id)},
            },
        )

        events1 = _parse_sse(resp1.text)
        assert len(events1) > 0, "First turn should produce events"

        # Второй запрос в той же сессии
        resp2 = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "turn2",
                "method": "message/stream",
                "params": {"message": _msg("Second message", context_id=context_id)},
            },
        )

        events2 = _parse_sse(resp2.text)
        assert len(events2) > 0, "Second turn should also produce events"

    @pytest.mark.asyncio
    async def test_stream_task_context_ids_consistent(self, client, flow_id, mock_llm_with_queue, sync_tools):
        """Все события имеют одинаковые taskId и contextId."""
        context_id = str(uuid.uuid4())
        mock_llm_with_queue(["Testing ID consistency across events"])

        resp = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": "id-consistency",
                "method": "message/stream",
                "params": {"message": _msg("Check IDs", context_id=context_id)},
            },
        )

        events = _parse_sse(resp.text)
        assert len(events) > 0, "Should receive events"

        # Все события должны иметь taskId и contextId
        task_ids = set()
        context_ids = set()

        for event in events:
            result = event.get("result", {})
            if result.get("taskId"):
                task_ids.add(result["taskId"])
            if result.get("contextId"):
                context_ids.add(result["contextId"])

        # Все taskId должны быть одинаковыми
        if task_ids:
            assert len(task_ids) == 1, f"All events should have same taskId, got: {task_ids}"

        # contextId должен соответствовать запросу
        if context_ids:
            assert context_id in context_ids, f"Events should have requested contextId {context_id}"
