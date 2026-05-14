"""
Тесты на артефакты в A2A API.
"""

import pytest

from apps.flows.src.utils import extract_json_from_response


class TestExtractJsonFromResponse:
    """Тесты функции извлечения JSON из ответа."""

    def test_extract_from_markdown_block(self):
        """JSON в markdown блоке."""
        text = '```json\n{"key": "value"}\n```'
        result = extract_json_from_response(text)
        assert result == {"key": "value"}

    def test_extract_from_markdown_with_text_before(self):
        """JSON в markdown блоке с текстом до."""
        text = 'Some text before\n```json\n{"key": "value"}\n```'
        result = extract_json_from_response(text)
        assert result == {"key": "value"}

    def test_extract_direct_json_object(self):
        """Прямой JSON объект."""
        text = '{"key": "value"}'
        result = extract_json_from_response(text)
        assert result == {"key": "value"}

    def test_extract_direct_json_array(self):
        """Прямой JSON массив."""
        text = '[{"a": 1}, {"b": 2}]'
        result = extract_json_from_response(text)
        assert result == [{"a": 1}, {"b": 2}]

    def test_no_json_returns_none(self):
        """Текст без JSON возвращает None."""
        text = "Just some plain text without JSON"
        result = extract_json_from_response(text)
        assert result is None

    def test_empty_text_returns_none(self):
        """Пустой текст возвращает None."""
        result = extract_json_from_response("")
        assert result is None

    def test_invalid_json_returns_none(self):
        """Невалидный JSON возвращает None."""
        text = '{"key": value}'  # без кавычек у value
        result = extract_json_from_response(text)
        assert result is None


@pytest.mark.asyncio
class TestA2AArtifacts:
    """Тесты артефактов в A2A ответе."""

    async def test_message_send_returns_artifact_for_json(self, client, mock_llm_with_queue, sync_tools, unique_id: str):
        """message/send возвращает artifact когда ответ содержит JSON."""
        # Мок ответ с JSON
        json_response = '```json\n{"document_type": "other", "fields": {}}\n```'
        mock_llm_with_queue([{"type": "text", "content": json_response}])

        response = await client.post(
            "/flows/api/v1/example_react",
            json={
                "jsonrpc": "2.0",
                "id": unique_id,
                "method": "message/send",
                "params": {
                    "message": {
                        "messageId": unique_id,
                        "role": "user",
                        "parts": [{"text": "Проанализируй документ"}],
                    }
                },
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert "result" in data
        result = data["result"]

        # Проверяем что есть artifacts
        assert "artifacts" in result
        assert result["artifacts"] is not None
        assert len(result["artifacts"]) > 0

        artifact = result["artifacts"][0]
        assert artifact["name"] == "response"
        assert "parts" in artifact
        assert len(artifact["parts"]) > 0

        part = artifact["parts"][0]
        assert part["kind"] == "data"
        assert "data" in part
        assert "res" in part["data"]

        # Когда есть artifacts, status.message НЕ дублирует ответ
        assert result["status"].get("message") is None

        # Должен быть timestamp
        assert "timestamp" in result["status"]

        # taskId должен быть в user message
        assert result["history"][0].get("taskId") is not None

    async def test_message_send_no_artifact_for_plain_text(self, client, mock_llm_with_queue, sync_tools, unique_id: str):
        """message/send не возвращает artifact для простого текста."""
        # Мок ответ без JSON
        mock_llm_with_queue([{"type": "text", "content": "Просто текстовый ответ без JSON"}])

        response = await client.post(
            "/flows/api/v1/example_react",
            json={
                "jsonrpc": "2.0",
                "id": unique_id,
                "method": "message/send",
                "params": {
                    "message": {
                        "messageId": unique_id,
                        "role": "user",
                        "parts": [{"text": "Привет"}],
                    }
                },
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert "result" in data
        result = data["result"]

        # artifacts должен быть None или отсутствовать
        assert result.get("artifacts") is None

