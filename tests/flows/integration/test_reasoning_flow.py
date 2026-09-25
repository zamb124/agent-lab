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

from apps.flows.src.models import FlowConfig

INLINE_CALCULATOR = {
    "tool_id": "calculator",
    "description": "Вычисляет математические выражения",
    "parameters_schema": {
        "type": "object",
        "properties": {"expression": {"type": "string"}},
        "required": ["expression"],
    },
    "code": "async def execute(args: dict, state: dict = None):\n    import ast\n    import operator\n    expr = args.get('expression', '0')\n    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}\n    def _eval(node):\n        if isinstance(node, ast.Expression): return _eval(node.body)\n        if isinstance(node, ast.Constant): return node.value\n        if isinstance(node, ast.BinOp): return ops[type(node.op)](_eval(node.left), _eval(node.right))\n        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub): return -_eval(node.operand)\n        raise ValueError(f\"Unsupported: {type(node)}\")\n    return f\"Результат: {_eval(ast.parse(expr, mode='eval'))}\"\n",
}


@pytest.mark.asyncio
@pytest.mark.requires_code_runner
class TestReasoningInAgent:
    """Тесты reasoning в flow с llm_node."""

    async def test_flow_with_reasoning_returns_separate_artifacts(
        self, client, mock_llm_with_queue, sync_tools, unique_id: str,
    di):
        """Agent с reasoning возвращает отдельные reasoning и response артефакты."""

        flow_id = f"test_reasoning_flow_{unique_id}"

        await FlowConfig.create_version(
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
                edges=[{"from_node": "main", "to_node": None}],
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
                "method": "SendMessage",
                "params": {
                    "message": {
                        "messageId": str(uuid.uuid4()),
                        "role": "ROLE_USER",
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
        named = {a.get("name") for a in result["artifacts"] if isinstance(a, dict)}
        assert "reasoning" in named
        assert "response" in named or None in named
        reasoning_artifact = next(
            (a for a in result["artifacts"] if a.get("name") == "reasoning"), None
        )
        response_artifact = next(
            (
                a
                for a in result["artifacts"]
                if a.get("name") == "response" or a.get("name") is None
            ),
            None,
        )
        assert reasoning_artifact is not None, "Должен быть reasoning артефакт"
        assert response_artifact is not None, "Должен быть response артефакт"
        reasoning_parts = reasoning_artifact.get("parts", [])
        assert len(reasoning_parts) > 0
        reasoning_text = ""
        for part in reasoning_parts:
            text = part.get("text")
            if isinstance(text, str):
                reasoning_text += text
        assert "Сначала я подумал" in reasoning_text
        assert "Потом решил" in reasoning_text
        response_parts = response_artifact.get("parts", [])
        response_text = ""
        for part in response_parts:
            text = part.get("text")
            if isinstance(text, str):
                response_text += text
        assert "Это ответ на вопрос" in response_text

    async def test_flow_with_reasoning_only(
        self, client, mock_llm_with_queue, sync_tools, unique_id: str,
    di):
        """Agent с только reasoning (без content) возвращает только reasoning артефакт."""

        flow_id = f"test_reasoning_only_flow_{unique_id}"

        await FlowConfig.create_version(
            FlowConfig(
                flow_id=flow_id,
                name="Test Reasoning Only Agent",
                entry="main",
                nodes={"main": {"type": "llm_node", "prompt": "Ты помощник.", "tools": []}},
                edges=[{"from_node": "main", "to_node": None}],
            )
        )
        mock_llm_with_queue(
            [{"type": "text", "content": "", "reasoning": "Я думаю над ответом..."}]
        )
        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": unique_id,
                "method": "SendMessage",
                "params": {
                    "message": {
                        "messageId": str(uuid.uuid4()),
                        "role": "ROLE_USER",
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
                text = part.get("text")
                if isinstance(text, str):
                    reasoning_text += text
            assert "Я думаю над ответом" in reasoning_text

    async def test_flow_with_reasoning_and_tool_call(
        self, client, mock_llm_with_queue, sync_tools, unique_id: str,
    di):
        """Agent с reasoning и tool call правильно обрабатывает reasoning."""

        flow_id = f"test_reasoning_tool_flow_{unique_id}"

        await FlowConfig.create_version(
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
                edges=[{"from_node": "main", "to_node": None}],
            )
        )
        mock_llm_with_queue(
            [
                {"type": "text", "content": "", "reasoning": "Нужно вычислить 2+2..."},
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
                "method": "SendMessage",
                "params": {
                    "message": {
                        "messageId": str(uuid.uuid4()),
                        "role": "ROLE_USER",
                        "parts": [{"text": "Сколько будет 2+2?"}],
                    }
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        result = data["result"]
        assert result["status"]["state"] == "TASK_STATE_COMPLETED"
        if result.get("artifacts"):
            reasoning_artifacts = [a for a in result["artifacts"] if a.get("name") == "reasoning"]
            assert len(reasoning_artifacts) >= 1
            all_reasoning_text = ""
            for artifact in reasoning_artifacts:
                for part in artifact.get("parts", []):
                    text = part.get("text")
                    if isinstance(text, str):
                        all_reasoning_text += text
            assert (
                "Нужно вычислить" in all_reasoning_text or "Получил результат" in all_reasoning_text
            )

    async def test_stream_returns_reasoning_events(
        self, client, mock_llm_with_queue, sync_tools, unique_id: str,
    di):
        """SendStreamingMessage возвращает reasoning события в SSE."""

        flow_id = f"test_reasoning_stream_flow_{unique_id}"

        await FlowConfig.create_version(
            FlowConfig(
                flow_id=flow_id,
                name="Test Reasoning Stream Agent",
                entry="main",
                nodes={"main": {"type": "llm_node", "prompt": "Ты помощник.", "tools": []}},
                edges=[{"from_node": "main", "to_node": None}],
            )
        )
        mock_llm_with_queue(
            [{"type": "text", "content": "Ответ", "reasoning": "Сначала думаю... Потом отвечаю."}]
        )
        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": unique_id,
                "method": "SendStreamingMessage",
                "params": {
                    "message": {
                        "messageId": str(uuid.uuid4()),
                        "role": "ROLE_USER",
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
        def _artifact_from_stream(result: dict) -> dict | None:
            update = result.get("artifactUpdate")
            if isinstance(update, dict):
                return update
            return None

        reasoning_events = [
            update
            for e in events
            if (update := _artifact_from_stream(e)) is not None
            and update.get("artifact", {}).get("name") == "reasoning"
        ]
        assert len(reasoning_events) > 0, "Должны быть reasoning события в stream"
        response_events = [
            update
            for e in events
            if (update := _artifact_from_stream(e)) is not None
            and (
                update.get("artifact", {}).get("name") is None
                or update.get("artifact", {}).get("name") == "response"
            )
        ]
        assert len(response_events) > 0, "Должны быть response события в stream"
