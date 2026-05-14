"""
Тесты Google Docs тулов.

TESTING=true — все тулы работают в mock режиме через mock_response из декоратора.
"""

import pytest

from apps.flows.tools import (
    gdocs_append_text,
    gdocs_create_document,
    gdocs_delete_range,
    gdocs_find_replace,
    gdocs_insert_text,
    gdocs_read_document,
    gdocs_share_document,
)
from core.state import ExecutionState


def _make_state() -> ExecutionState:
    return ExecutionState(
        task_id="test-task",
        context_id="test-context",
        user_id="test-user",
        session_id="test-gdocs:test-context",
    )


class TestGDocsCreateDocument:
    @pytest.mark.asyncio
    async def test_mock_returns_document_id(self):
        state = _make_state()
        result = await gdocs_create_document.run(
            {"title": "Отчёт Q1"}, state
        )
        assert result["success"] is True
        assert "document_id" in result
        assert result["title"] == "Отчёт Q1"
        assert "web_url" in result

    @pytest.mark.asyncio
    async def test_mock_with_file_id(self):
        state = _make_state()
        result = await gdocs_create_document.run(
            {"title": "From template", "file_id": "file_abc"}, state
        )
        assert result["success"] is True
        assert "document_id" in result


class TestGDocsReadDocument:
    @pytest.mark.asyncio
    async def test_mock_returns_text(self):
        state = _make_state()
        result = await gdocs_read_document.run(
            {"document_id": "doc123"}, state
        )
        assert result["success"] is True
        assert "text" in result
        assert result["document_id"] == "doc123"


class TestGDocsAppendText:
    @pytest.mark.asyncio
    async def test_mock_success(self):
        state = _make_state()
        result = await gdocs_append_text.run(
            {"document_id": "doc123", "text": "Новый абзац"}, state
        )
        assert result["success"] is True
        assert result["document_id"] == "doc123"


class TestGDocsInsertText:
    @pytest.mark.asyncio
    async def test_mock_success(self):
        state = _make_state()
        result = await gdocs_insert_text.run(
            {"document_id": "doc123", "text": "Вставка", "index": 5}, state
        )
        assert result["success"] is True


class TestGDocsFindReplace:
    @pytest.mark.asyncio
    async def test_mock_returns_occurrences(self):
        state = _make_state()
        result = await gdocs_find_replace.run(
            {"document_id": "doc123", "find": "старое", "replace": "новое"},
            state,
        )
        assert result["success"] is True
        assert "occurrences_changed" in result


class TestGDocsDeleteRange:
    @pytest.mark.asyncio
    async def test_mock_success(self):
        state = _make_state()
        result = await gdocs_delete_range.run(
            {"document_id": "doc123", "start_index": 1, "end_index": 10},
            state,
        )
        assert result["success"] is True


class TestGDocsShareDocument:
    @pytest.mark.asyncio
    async def test_mock_success(self):
        state = _make_state()
        result = await gdocs_share_document.run(
            {"document_id": "doc123", "email": "user@example.com"}, state
        )
        assert result["success"] is True


class TestGDocsToolSchemas:
    """Проверка OpenAI-схем тулов."""

    def test_all_tools_have_valid_schemas(self):
        tools = [
            gdocs_create_document,
            gdocs_read_document,
            gdocs_append_text,
            gdocs_insert_text,
            gdocs_find_replace,
            gdocs_delete_range,
            gdocs_share_document,
        ]
        for t in tools:
            schema = t.to_openai_schema()
            assert schema["type"] == "function"
            assert schema["function"]["name"].startswith("gdocs_")
            assert "parameters" in schema["function"]

    def test_create_document_schema_has_file_id(self):
        schema = gdocs_create_document.to_openai_schema()
        props = schema["function"]["parameters"]["properties"]
        assert "title" in props
        assert "file_id" in props


class TestGDocsClientInit:
    """Валидация конструктора GoogleDocsClient."""

    def test_no_args_raises(self):
        from core.clients.google_docs_client import GoogleDocsClient

        with pytest.raises(ValueError, match="credentials_json"):
            GoogleDocsClient()

    def test_both_args_raises(self):
        from core.clients.google_docs_client import GoogleDocsClient

        with pytest.raises(ValueError, match="не оба"):
            GoogleDocsClient(
                credentials_json='{"fake": true}',
                access_token="tok_abc",
            )

    def test_access_token_mode(self):
        from core.clients.google_docs_client import GoogleDocsClient

        client = GoogleDocsClient(access_token="tok_test_123")
        headers = client._auth_headers()
        assert headers["Authorization"] == "Bearer tok_test_123"

    def test_positional_args_rejected(self):
        from core.clients.google_docs_client import GoogleDocsClient

        with pytest.raises(TypeError):
            GoogleDocsClient('{"fake": true}')

    def test_subject_without_credentials_raises(self):
        from core.clients.google_docs_client import GoogleDocsClient

        with pytest.raises(ValueError, match="только с credentials_json"):
            GoogleDocsClient(access_token="tok_abc", subject="user@domain.ru")

    def test_subject_with_access_token_raises(self):
        from core.clients.google_docs_client import GoogleDocsClient

        with pytest.raises(ValueError, match="только с credentials_json"):
            GoogleDocsClient(access_token="tok_abc", subject="admin@corp.com")

    def test_subject_none_is_allowed(self):
        from core.clients.google_docs_client import GoogleDocsClient

        client = GoogleDocsClient(access_token="tok_abc", subject=None)
        assert client._static_token == "tok_abc"


class TestGDocsClientUnit:
    """Unit-тесты GoogleDocsClient (логика парсинга, без HTTP)."""

    def test_extract_text_from_doc_structure(self):
        from core.clients.google_docs_client import _extract_text

        doc = {
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "elements": [
                                {"textRun": {"content": "Привет, "}},
                                {"textRun": {"content": "мир!\n"}},
                            ]
                        }
                    },
                    {
                        "paragraph": {
                            "elements": [
                                {"textRun": {"content": "Второй абзац.\n"}},
                            ]
                        }
                    },
                ]
            }
        }
        text = _extract_text(doc)
        assert text == "Привет, мир!\nВторой абзац.\n"

    def test_extract_text_empty_doc(self):
        from core.clients.google_docs_client import _extract_text

        assert _extract_text({}) == ""
        assert _extract_text({"body": {}}) == ""
        assert _extract_text({"body": {"content": []}}) == ""

    def test_get_body_end_index(self):
        from core.clients.google_docs_client import _get_body_end_index

        doc = {
            "body": {
                "content": [
                    {"startIndex": 0, "endIndex": 15},
                    {"startIndex": 15, "endIndex": 42},
                ]
            }
        }
        assert _get_body_end_index(doc) == 41

    def test_get_body_end_index_empty(self):
        from core.clients.google_docs_client import _get_body_end_index

        assert _get_body_end_index({}) == 1
        assert _get_body_end_index({"body": {"content": []}}) == 1
