"""
Интеграционные тесты reasoning событий в flow с агентами и tools.

Проверяет, что reasoning события правильно транслируются через весь стек:
- LLMClient.stream() генерирует reasoning артефакты
- LlmNodeRunner передает reasoning события
- _build_task_from_events разделяет reasoning и response
- API возвращает reasoning артефакты в Task
"""

import uuid

import pytest
from httpx import AsyncClient, ASGITransport


INLINE_CALCULATOR = {
    "tool_id": "calculator",
    "description": "Вычисляет математические выражения",
    "args_schema": {"expression": {"type": "string"}},
    "code": """async def execute(args: dict, state: dict = None):
    import ast
    import operator
    expr = args.get('expression', '0')
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
    def _eval(node):
        if isinstance(node, ast.Expression): return _eval(node.body)
        if isinstance(node, ast.Constant): return node.value
        if isinstance(node, ast.BinOp): return ops[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub): return -_eval(node.operand)
        raise ValueError(f"Unsupported: {type(node)}")
    return f"Результат: {_eval(ast.parse(expr, mode='eval'))}"
"""
}


@pytest.mark.asyncio
class TestReasoningInAgent:
    """Тесты reasoning в flow с llm_node."""

    async def test_flow_with_reasoning_returns_separate_artifacts(
        self, client, mock_llm_with_queue, sync_tools, unique_id: str
    ):
        """Agent с reasoning возвращает отдельные reasoning и response артефакты."""
        from apps.flows.src.container import get_container

        flow_id = f"test_reasoning_flow_{unique_id}"

        from apps.flows.src.models import FlowConfig

        container = get_container()
        await container.flow_repository.set(
            FlowConfig(
                flow_id=flow_id,
                name="Test Reasoning Agent",
                entry="main",
                nodes={
                    "main": {
                        "type": "llm_node",
                        "prompt": "Ты помощник. Отвечай на вопросы.",
                        "tools": [],
                    }
                },
                edges=[{"from": "main", "to": None}],
            )
        )

        mock_llm_with_queue(
            [
                {
                    "type": "text",
                    "content": "Это ответ на вопрос",
                    "reasoning": "Сначала я подумал... Потом решил...",
                }
            ]
        )

        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": unique_id,
                "method": "message/send",
                "params": {
                    "message": {
                        "messageId": str(uuid.uuid4()),
                        "role": "user",
                        "parts": [{"text": "Тестовый вопрос"}],
                    }
                },
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        result = data["result"]

        assert "artifacts" in result
        assert result["artifacts"] is not None
        assert len(result["artifacts"]) == 2

        reasoning_artifact = next(
            (a for a in result["artifacts"] if a.get("name") == "reasoning"), None
        )
        response_artifact = next(
            (a for a in result["artifacts"] if a.get("name") == "response" or a.get("name") is None),
            None,
        )

        assert reasoning_artifact is not None, "Должен быть reasoning артефакт"
        assert response_artifact is not None, "Должен быть response артефакт"

        reasoning_parts = reasoning_artifact.get("parts", [])
        assert len(reasoning_parts) > 0

        reasoning_text = ""
        for part in reasoning_parts:
            if part.get("kind") == "text" or "text" in part:
                reasoning_text += part.get("text", "")
            elif "root" in part and "text" in part.get("root", {}):
                reasoning_text += part["root"]["text"]

        assert "Сначала я подумал" in reasoning_text
        assert "Потом решил" in reasoning_text

        response_parts = response_artifact.get("parts", [])
        response_text = ""
        for part in response_parts:
            if part.get("kind") == "text" or "text" in part:
                response_text += part.get("text", "")
            elif "root" in part and "text" in part.get("root", {}):
                response_text += part["root"]["text"]

        assert "Это ответ на вопрос" in response_text

    async def test_flow_with_reasoning_only(
        self, client, mock_llm_with_queue, sync_tools, unique_id: str
    ):
        """Agent с только reasoning (без content) возвращает только reasoning артефакт."""
        from apps.flows.src.container import get_container

        flow_id = f"test_reasoning_only_flow_{unique_id}"

        from apps.flows.src.models import FlowConfig

        container = get_container()
        await container.flow_repository.set(
            FlowConfig(
                flow_id=flow_id,
                name="Test Reasoning Only Agent",
                entry="main",
                nodes={
                    "main": {
                        "type": "llm_node",
                        "prompt": "Ты помощник.",
                        "tools": [],
                    }
                },
                edges=[{"from": "main", "to": None}],
            )
        )

        mock_llm_with_queue(
            [
                {
                    "type": "text",
                    "content": "",
                    "reasoning": "Я думаю над ответом...",
                }
            ]
        )

        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": unique_id,
                "method": "message/send",
                "params": {
                    "message": {
                        "messageId": str(uuid.uuid4()),
                        "role": "user",
                        "parts": [{"text": "Вопрос"}],
                    }
                },
            },
        )

        assert response.status_code == 200
        data = response.json()
        result = data["result"]

        if result.get("artifacts"):
            reasoning_artifact = next(
                (a for a in result["artifacts"] if a.get("name") == "reasoning"), None
            )
            assert reasoning_artifact is not None

            reasoning_parts = reasoning_artifact.get("parts", [])
            reasoning_text = ""
            for part in reasoning_parts:
                if part.get("kind") == "text" or "text" in part:
                    reasoning_text += part.get("text", "")
                elif "root" in part and "text" in part.get("root", {}):
                    reasoning_text += part["root"]["text"]

            assert "Я думаю над ответом" in reasoning_text

    async def test_flow_with_reasoning_and_tool_call(
        self, client, mock_llm_with_queue, sync_tools, unique_id: str
    ):
        """Agent с reasoning и tool call правильно обрабатывает reasoning."""
        from apps.flows.src.container import get_container

        flow_id = f"test_reasoning_tool_flow_{unique_id}"

        from apps.flows.src.models import FlowConfig

        container = get_container()
        await container.flow_repository.set(
            FlowConfig(
                flow_id=flow_id,
                name="Test Reasoning Tool Agent",
                entry="main",
                nodes={
                    "main": {
                        "type": "llm_node",
                        "prompt": "Ты помощник. Используй calculator для вычислений.",
                        "tools": [INLINE_CALCULATOR],
                    }
                },
                edges=[{"from": "main", "to": None}],
            )
        )

        mock_llm_with_queue(
            [
                {
                    "type": "text",
                    "content": "",
                    "reasoning": "Нужно вычислить 2+2...",
                },
                {"type": "tool_call", "tool": "calculator", "args": {"expression": "2+2"}},
                {
                    "type": "text",
                    "content": "Результат: 4",
                    "reasoning": "Получил результат, теперь формирую ответ...",
                },
            ]
        )

        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": unique_id,
                "method": "message/send",
                "params": {
                    "message": {
                        "messageId": str(uuid.uuid4()),
                        "role": "user",
                        "parts": [{"text": "Сколько будет 2+2?"}],
                    }
                },
            },
        )

        assert response.status_code == 200
        data = response.json()
        result = data["result"]

        assert result["status"]["state"] == "completed"

        if result.get("artifacts"):
            reasoning_artifacts = [
                a for a in result["artifacts"] if a.get("name") == "reasoning"
            ]
            assert len(reasoning_artifacts) >= 1

            all_reasoning_text = ""
            for artifact in reasoning_artifacts:
                for part in artifact.get("parts", []):
                    if part.get("kind") == "text" or "text" in part:
                        all_reasoning_text += part.get("text", "")
                    elif "root" in part and "text" in part.get("root", {}):
                        all_reasoning_text += part["root"]["text"]

            assert "Нужно вычислить" in all_reasoning_text or "Получил результат" in all_reasoning_text

    async def test_stream_returns_reasoning_events(
        self, client, mock_llm_with_queue, sync_tools, unique_id: str
    ):
        """message/stream возвращает reasoning события в SSE."""
        from apps.flows.src.container import get_container

        flow_id = f"test_reasoning_stream_flow_{unique_id}"

        from apps.flows.src.models import FlowConfig

        container = get_container()
        await container.flow_repository.set(
            FlowConfig(
                flow_id=flow_id,
                name="Test Reasoning Stream Agent",
                entry="main",
                nodes={
                    "main": {
                        "type": "llm_node",
                        "prompt": "Ты помощник.",
                        "tools": [],
                    }
                },
                edges=[{"from": "main", "to": None}],
            )
        )

        mock_llm_with_queue(
            [
                {
                    "type": "text",
                    "content": "Ответ",
                    "reasoning": "Сначала думаю... Потом отвечаю.",
                }
            ]
        )

        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": unique_id,
                "method": "message/stream",
                "params": {
                    "message": {
                        "messageId": str(uuid.uuid4()),
                        "role": "user",
                        "parts": [{"text": "Вопрос"}],
                    }
                },
            },
        )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

        text = response.text
        lines = text.split("\n")
        events = []
        for line in lines:
            if line.startswith("data: "):
                try:
                    import json

                    event_data = json.loads(line[6:])
                    if "result" in event_data:
                        events.append(event_data["result"])
                except Exception:
                    pass

        reasoning_events = [
            e for e in events if e.get("kind") == "artifact-update" and e.get("artifact", {}).get("name") == "reasoning"
        ]

        assert len(reasoning_events) > 0, "Должны быть reasoning события в stream"

        response_events = [
            e
            for e in events
            if e.get("kind") == "artifact-update"
            and (e.get("artifact", {}).get("name") is None or e.get("artifact", {}).get("name") == "response")
        ]

        assert len(response_events) > 0, "Должны быть response события в stream"
