"""
Тесты Google Docs тулов.

Google Docs tools требуют явную авторизацию через state.variables или OAuth interrupt.
"""

import uuid

import pytest

from apps.flows.di import FlowsDi
from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.services.google_workspace_client import GoogleWorkspaceClient
from apps.flows.src.tools.base import ToolArguments
from apps.flows.src.tools.decorator import FunctionTool
from apps.flows.tools.google_docs.google_docs import (
    gdocs_append_text,
    gdocs_create_document,
    gdocs_delete_range,
    gdocs_find_replace,
    gdocs_insert_text,
    gdocs_read_document,
    gdocs_share_document,
)
from core.config import get_settings
from core.config.models import AuthConfig, AuthProviderConfig
from core.state import ExecutionState
from core.state.interrupt import InterruptKind, OAuthInterrupt


def _make_state() -> ExecutionState:
    uid = uuid.uuid4().hex[:12]
    return ExecutionState(
        task_id=f"test-task-{uid}",
        context_id=f"test-context-{uid}",
        user_id="test_user",
        session_id=f"test-gdocs:test-context-{uid}",
    )


def _workspace_client(di: FlowsDi) -> GoogleWorkspaceClient:
    return GoogleWorkspaceClient(
        oauth_service=di.oauth_service,
        company_credentials=di.company_integration_credential_service,
    )


def _enable_google_oauth(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(
        settings,
        "auth",
        AuthConfig(
            jwt_secret_key="test-secret-key-32-bytes-minimum-!",
            providers={
                "google": AuthProviderConfig(
                    client_id="cid",
                    client_secret="csec",
                    auth_url="https://accounts.google.com/o/oauth2/v2/auth",
                    token_url="https://oauth2.googleapis.com/token",
                ),
            },
        ),
    )


async def _assert_requires_google_docs_oauth(
    di: FlowsDi,
    tool: FunctionTool,
    args: ToolArguments,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_google_oauth(monkeypatch)
    state = _make_state()
    bound = tool.with_dependencies([_workspace_client(di)])
    with pytest.raises(FlowInterrupt) as exc_info:
        _ = await bound.run(args, state)
    interrupt = exc_info.value.body
    assert interrupt.kind == InterruptKind.OAUTH_REQUIRED
    assert isinstance(interrupt, OAuthInterrupt)
    assert interrupt.provider == "google"
    assert interrupt.service == "workspace"


class TestGDocsCreateDocument:
    @pytest.mark.asyncio
    async def test_requires_oauth_without_credentials(
        self, di: FlowsDi, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _assert_requires_google_docs_oauth(
            di, gdocs_create_document, {"title": "Отчёт Q1"}, monkeypatch
        )

    @pytest.mark.asyncio
    async def test_requires_oauth_with_file_id_without_credentials(
        self, di: FlowsDi, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _assert_requires_google_docs_oauth(
            di,
            gdocs_create_document,
            {"title": "From template", "file_id": "file_abc"},
            monkeypatch,
        )


class TestGDocsReadDocument:
    @pytest.mark.asyncio
    async def test_requires_oauth_without_credentials(
        self, di: FlowsDi, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _assert_requires_google_docs_oauth(
            di, gdocs_read_document, {"document_id": "doc123"}, monkeypatch
        )


class TestGDocsAppendText:
    @pytest.mark.asyncio
    async def test_requires_oauth_without_credentials(
        self, di: FlowsDi, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _assert_requires_google_docs_oauth(
            di,
            gdocs_append_text,
            {"document_id": "doc123", "text": "Новый абзац"},
            monkeypatch,
        )


class TestGDocsInsertText:
    @pytest.mark.asyncio
    async def test_requires_oauth_without_credentials(
        self, di: FlowsDi, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _assert_requires_google_docs_oauth(
            di,
            gdocs_insert_text,
            {"document_id": "doc123", "text": "Вставка", "index": 5},
            monkeypatch,
        )


class TestGDocsFindReplace:
    @pytest.mark.asyncio
    async def test_requires_oauth_without_credentials(
        self, di: FlowsDi, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _assert_requires_google_docs_oauth(
            di,
            gdocs_find_replace,
            {"document_id": "doc123", "find": "старое", "replace": "новое"},
            monkeypatch,
        )


class TestGDocsDeleteRange:
    @pytest.mark.asyncio
    async def test_requires_oauth_without_credentials(
        self, di: FlowsDi, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _assert_requires_google_docs_oauth(
            di,
            gdocs_delete_range,
            {"document_id": "doc123", "start_index": 1, "end_index": 10},
            monkeypatch,
        )


class TestGDocsShareDocument:
    @pytest.mark.asyncio
    async def test_requires_oauth_without_credentials(
        self, di: FlowsDi, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _assert_requires_google_docs_oauth(
            di,
            gdocs_share_document,
            {"document_id": "doc123", "email": "user@example.com"},
            monkeypatch,
        )


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

        with pytest.raises(ValueError, match="not both"):
            GoogleDocsClient(
                credentials_json='{"fake": true}',
                access_token="tok_abc",
            )

    @pytest.mark.asyncio
    async def test_access_token_mode(self):
        from core.clients.google_docs_client import GoogleDocsClient

        client = GoogleDocsClient(access_token="tok_test_123")
        headers = await client._auth_headers()
        assert headers["Authorization"] == "Bearer tok_test_123"

    def test_positional_args_rejected(self):
        from core.clients.google_docs_client import GoogleDocsClient

        with pytest.raises(TypeError):
            GoogleDocsClient('{"fake": true}')

    def test_subject_without_credentials_raises(self):
        from core.clients.google_docs_client import GoogleDocsClient

        with pytest.raises(ValueError, match="only with credentials_json"):
            GoogleDocsClient(access_token="tok_abc", subject="user@domain.ru")

    def test_subject_with_access_token_raises(self):
        from core.clients.google_docs_client import GoogleDocsClient

        with pytest.raises(ValueError, match="only with credentials_json"):
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
