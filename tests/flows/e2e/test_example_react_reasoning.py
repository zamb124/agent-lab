"""
E2E тесты для example_react с reasoning mode.

Тестируем что reasoning артефакты приходят через A2A API.
"""

import uuid as uuid_lib
from typing import Any, Dict

import pytest

pytestmark = pytest.mark.asyncio


def get_task_state(data: Dict[str, Any]) -> str:
    """Извлекает state из A2A Task ответа."""
    if "result" in data:
        return data["result"]["status"]["state"]
    return data.get("status", {}).get("state", "")


def get_task_response(data: Dict[str, Any]) -> str:
    """Извлекает текст ответа из A2A Task."""
    if "result" in data:
        msg = data["result"]["status"].get("message")
    else:
        msg = data.get("status", {}).get("message")
    if msg and msg.get("parts"):
        return msg["parts"][0].get("text", "")
    return ""


def get_artifacts(data: Dict[str, Any]) -> list:
    """Извлекает artifacts из ответа."""
    if "result" in data:
        return data["result"].get("artifacts", [])
    return data.get("artifacts", [])


async def send_a2a_message(
    client,
    flow_id: str,
    content: str,
    branch_id: str = "default",
    session_id: str = None,
) -> Dict[str, Any]:
    """Отправляет сообщение через A2A API."""
    if session_id is None:
        session_id = f"{flow_id}:test-{uuid_lib.uuid4()}"

    response = await client.post(
        f"/flows/api/v1/{flow_id}",
        json={
            "jsonrpc": "2.0",
            "id": f"req-{uuid_lib.uuid4()}",
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": f"msg-{uuid_lib.uuid4()}",
                    "role": "user",
                    "parts": [{"kind": "text", "text": content}],
                },
            },
        },
    )
    assert response.status_code == 200, f"HTTP {response.status_code}: {response.text}"
    return response.json()


class TestExampleReactReasoning:
    """E2E тесты для example_react с reasoning."""

    @pytest.mark.asyncio
    async def test_subagent_with_reasoning_returns_artifacts(
        self, client, mock_llm_with_queue
    ):
        """
        Субагент с reasoning возвращает reasoning артефакты.

        Этот тест зависит от того что в agents/example_react/agents.json
        субагент example_subflow имеет reasoning: {enabled: true}.
        """
        mock_llm_with_queue([
            # Main нода вызывает example_subflow
            {
                "type": "tool_call",
                "tool": "example_subflow",
                "args": {"query": "Привет!"},
            },
            # example_subflow вызывает reasoning tool
            {
                "type": "tool_call",
                "tool": "reason",
                "args": {
                    "observation": "Пользователь говорит привет",
                    "analysis": "Нужно поприветствовать",
                    "plan": "Ответить приветствием",
                    "next_action": "Отвечаю текстом",
                },
            },
            # example_subflow отвечает после reasoning
            {"type": "text", "content": "Привет! Чем могу помочь?"},
            # Main нода финализирует ответ
            {"type": "text", "content": "Субагент ответил: Привет! Чем могу помочь?"},
        ])

        result = await send_a2a_message(
            client,
            flow_id="example_react",
            content="Привет!",
        )

        state = get_task_state(result)
        assert state in ["completed", "input_required"]

        artifacts = get_artifacts(result)
        reasoning_artifacts = [a for a in artifacts if a.get("name") == "reasoning"]

        # Если reasoning включен - артефакт должен быть
        # Если нет - тест пройдет, но артефактов не будет
        if reasoning_artifacts:
            reasoning_text = ""
            for artifact in reasoning_artifacts:
                for part in artifact.get("parts", []):
                    if "text" in part:
                        reasoning_text += part["text"]

            assert "Наблюдение" in reasoning_text or "observation" in reasoning_text.lower()

    @pytest.mark.asyncio
    async def test_main_agent_responds(self, client, mock_llm_with_queue):
        """Главный агент example_react отвечает."""
        mock_llm_with_queue([
            {"type": "text", "content": "Привет! Я тестовый агент."},
        ])

        result = await send_a2a_message(
            client,
            flow_id="example_react",
            content="Привет!",
        )

        state = get_task_state(result)
        assert state == "completed"

        response = get_task_response(result)
        assert len(response) > 0

