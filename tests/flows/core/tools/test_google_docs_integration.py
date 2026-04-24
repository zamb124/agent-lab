"""
Интеграционные тесты Google Docs — каждый тул через LlmNode + MockLLM.

ПРАВИЛО: мок только LLM. Tools, state, flow — реальные. Google API — реальный.

Для тулов, которым нужен document_id (read, append, insert, find_replace,
delete_range, share), документ создаётся ПЕРЕД flow через GoogleDocsClient напрямую,
чтобы document_id был известен для MockLLM очереди.

Требует:
  - файл google_service_account.json в корне проекта (gitignored)
  - env GOOGLE_IMPERSONATE_EMAIL — email пользователя Google Workspace
    для domain-wide delegation (SA работает от его имени)

Без файла `google_service_account.json` и `GOOGLE_IMPERSONATE_EMAIL` тесты пропускаются (`pytest.skip`).

Запуск:
    GOOGLE_IMPERSONATE_EMAIL=user@domain.ru \\
      uv run pytest tests/flows/core/tools/test_google_docs_integration.py -v -s
"""

import os
from pathlib import Path

import pytest

from apps.flows.src.container import get_container
from apps.flows.src.models import FlowConfig
from apps.flows.tools import (
    gdocs_append_text,
    gdocs_create_document,
    gdocs_delete_range,
    gdocs_find_replace,
    gdocs_insert_text,
    gdocs_read_document,
    gdocs_share_document,
)
from core.clients.google_docs_client import GoogleDocsClient
from core.state import ExecutionState

_CREDS_PATH = Path(__file__).resolve().parents[4] / "google_service_account.json"

_creds_json: str | None = None
if _CREDS_PATH.exists():
    _creds_json = _CREDS_PATH.read_text(encoding="utf-8")

_impersonate_email: str | None = os.environ.get("GOOGLE_IMPERSONATE_EMAIL")

_ALL_GDOCS_TOOLS = [
    gdocs_create_document,
    gdocs_read_document,
    gdocs_append_text,
    gdocs_insert_text,
    gdocs_find_replace,
    gdocs_delete_range,
    gdocs_share_document,
]

_skip_reason_parts: list[str] = []
if _creds_json is None:
    _skip_reason_parts.append(f"файл {_CREDS_PATH} не найден")
if _impersonate_email is None:
    _skip_reason_parts.append("env GOOGLE_IMPERSONATE_EMAIL не задан")


@pytest.fixture(autouse=True)
def _require_google_docs_credentials() -> None:
    if _skip_reason_parts:
        pytest.skip("; ".join(_skip_reason_parts))


@pytest.fixture()
def gdocs_real_mode():
    """Временно снимает mock_response с gdocs тулов — TESTING=true не мешает."""
    saved = {}
    for t in _ALL_GDOCS_TOOLS:
        saved[t.name] = t._mock_response
        t._mock_response = None
    yield
    for t in _ALL_GDOCS_TOOLS:
        t._mock_response = saved[t.name]


@pytest.fixture()
def gdocs_client() -> GoogleDocsClient:
    """Клиент для pre-setup документов перед flow (с delegation)."""
    return GoogleDocsClient(
        credentials_json=_creds_json,
        subject=_impersonate_email,
    )


def _make_state(unique_id: str, flow_id: str, content: str = "Выполни") -> ExecutionState:
    context_id = f"ctx-gdocs-{unique_id}"
    return ExecutionState(
        task_id=f"task-gdocs-{unique_id}",
        context_id=context_id,
        user_id=f"user-gdocs-{unique_id}",
        session_id=f"{flow_id}:{context_id}",
        content=content,
        variables={
            "google_service_account": _creds_json,
            "google_impersonate_email": _impersonate_email,
        },
    )


def _tool_results_from_state(state: ExecutionState) -> list[str]:
    """Извлекает content всех tool-результатов из state.messages."""
    return [
        m.get("content", "") for m in state.messages if m.get("role") == "tool"
    ]


async def _run_single_tool_flow(
    unique_id: str,
    flow_suffix: str,
    tool_ids: list[str],
    tool_call_name: str,
    tool_call_args: dict,
    mock_llm_with_queue,
) -> tuple[dict, ExecutionState]:
    """Создаёт flow с одной llm_node, подаёт один tool_call, возвращает (result, state)."""
    flow_id = f"gdocs_{flow_suffix}_{unique_id}"
    container = get_container()

    flow_config = FlowConfig(
        flow_id=flow_id,
        name=f"GDocs {flow_suffix}",
        entry="agent",
        nodes={
            "agent": {
                "type": "llm_node",
                "prompt": "Ты агент для Google Docs.",
                "tools": [{"tool_id": tid} for tid in tool_ids],
            }
        },
        edges=[],
    )
    await container.flow_repository.set(flow_config)

    mock_llm_with_queue([
        {"type": "tool_call", "tool": tool_call_name, "args": tool_call_args},
        {"type": "text", "content": "Готово."},
    ])

    flow = await container.flow_factory.get_flow(flow_id)
    state = _make_state(unique_id, flow_id)
    result = await flow.run(state)

    await container.flow_repository.delete(flow_id)
    return result, state


# ── Тесты ─────────────────────────────────────────────────────────


class TestGDocsCreateViaAgent:
    """gdocs_create_document через LlmNode — создание пустого документа."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_create_document(
        self, app, unique_id, mock_llm_with_queue, gdocs_real_mode
    ):
        result, state = await _run_single_tool_flow(
            unique_id,
            flow_suffix="create",
            tool_ids=["gdocs_create_document"],
            tool_call_name="gdocs_create_document",
            tool_call_args={"title": f"Agent Create {unique_id}"},
            mock_llm_with_queue=mock_llm_with_queue,
        )
        assert result["response"] == "Готово."

        tool_contents = _tool_results_from_state(state)
        assert len(tool_contents) == 1
        assert "success" in tool_contents[0]
        assert "document_id" in tool_contents[0]


class TestGDocsReadViaAgent:
    """gdocs_read_document через LlmNode — чтение реального документа."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_read_document(
        self, app, unique_id, mock_llm_with_queue, gdocs_real_mode, gdocs_client
    ):
        doc = await gdocs_client.create_document(f"Read Target {unique_id}")
        doc_id = doc["documentId"]
        await gdocs_client.append_text(doc_id, "Контент для чтения.")

        result, state = await _run_single_tool_flow(
            unique_id,
            flow_suffix="read",
            tool_ids=["gdocs_read_document"],
            tool_call_name="gdocs_read_document",
            tool_call_args={"document_id": doc_id},
            mock_llm_with_queue=mock_llm_with_queue,
        )
        assert result["response"] == "Готово."

        tool_contents = _tool_results_from_state(state)
        assert len(tool_contents) == 1
        assert "Контент для чтения" in tool_contents[0]


class TestGDocsAppendViaAgent:
    """gdocs_append_text через LlmNode — добавление текста в конец."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_append_text(
        self, app, unique_id, mock_llm_with_queue, gdocs_real_mode, gdocs_client
    ):
        doc = await gdocs_client.create_document(f"Append Target {unique_id}")
        doc_id = doc["documentId"]

        result, state = await _run_single_tool_flow(
            unique_id,
            flow_suffix="append",
            tool_ids=["gdocs_append_text"],
            tool_call_name="gdocs_append_text",
            tool_call_args={
                "document_id": doc_id,
                "text": "Добавленный текст из агента.\n",
            },
            mock_llm_with_queue=mock_llm_with_queue,
        )
        assert result["response"] == "Готово."

        text = await gdocs_client.read_as_text(doc_id)
        assert "Добавленный текст из агента." in text


class TestGDocsInsertViaAgent:
    """gdocs_insert_text через LlmNode — вставка в начало."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_insert_text(
        self, app, unique_id, mock_llm_with_queue, gdocs_real_mode, gdocs_client
    ):
        doc = await gdocs_client.create_document(f"Insert Target {unique_id}")
        doc_id = doc["documentId"]
        await gdocs_client.append_text(doc_id, "Второй.\n")

        result, state = await _run_single_tool_flow(
            unique_id,
            flow_suffix="insert",
            tool_ids=["gdocs_insert_text"],
            tool_call_name="gdocs_insert_text",
            tool_call_args={
                "document_id": doc_id,
                "text": "Первый.\n",
                "index": 1,
            },
            mock_llm_with_queue=mock_llm_with_queue,
        )
        assert result["response"] == "Готово."

        text = await gdocs_client.read_as_text(doc_id)
        assert text.startswith("Первый.")
        assert "Второй." in text


class TestGDocsFindReplaceViaAgent:
    """gdocs_find_replace через LlmNode — поиск и замена."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_find_replace(
        self, app, unique_id, mock_llm_with_queue, gdocs_real_mode, gdocs_client
    ):
        doc = await gdocs_client.create_document(f"FR Target {unique_id}")
        doc_id = doc["documentId"]
        await gdocs_client.append_text(doc_id, "Старая версия документа.\n")

        result, state = await _run_single_tool_flow(
            unique_id,
            flow_suffix="fr",
            tool_ids=["gdocs_find_replace"],
            tool_call_name="gdocs_find_replace",
            tool_call_args={
                "document_id": doc_id,
                "find": "Старая",
                "replace": "Новая",
            },
            mock_llm_with_queue=mock_llm_with_queue,
        )
        assert result["response"] == "Готово."

        tool_contents = _tool_results_from_state(state)
        assert "occurrences_changed" in tool_contents[0]

        text = await gdocs_client.read_as_text(doc_id)
        assert "Новая версия" in text
        assert "Старая" not in text


class TestGDocsDeleteRangeViaAgent:
    """gdocs_delete_range через LlmNode — удаление диапазона."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_delete_range(
        self, app, unique_id, mock_llm_with_queue, gdocs_real_mode, gdocs_client
    ):
        doc = await gdocs_client.create_document(f"Del Target {unique_id}")
        doc_id = doc["documentId"]
        await gdocs_client.append_text(doc_id, "ABCDEFGHIJ")

        result, state = await _run_single_tool_flow(
            unique_id,
            flow_suffix="delrange",
            tool_ids=["gdocs_delete_range"],
            tool_call_name="gdocs_delete_range",
            tool_call_args={
                "document_id": doc_id,
                "start_index": 1,
                "end_index": 4,
            },
            mock_llm_with_queue=mock_llm_with_queue,
        )
        assert result["response"] == "Готово."

        text = await gdocs_client.read_as_text(doc_id)
        assert not text.startswith("ABC")


class TestGDocsShareViaAgent:
    """gdocs_share_document через LlmNode — расшаривание по ссылке."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_share_anyone(
        self, app, unique_id, mock_llm_with_queue, gdocs_real_mode, gdocs_client
    ):
        doc = await gdocs_client.create_document(f"Share Target {unique_id}")
        doc_id = doc["documentId"]

        result, state = await _run_single_tool_flow(
            unique_id,
            flow_suffix="share",
            tool_ids=["gdocs_share_document"],
            tool_call_name="gdocs_share_document",
            tool_call_args={
                "document_id": doc_id,
                "anyone": True,
                "role": "reader",
            },
            mock_llm_with_queue=mock_llm_with_queue,
        )
        assert result["response"] == "Готово."

        tool_contents = _tool_results_from_state(state)
        assert "success" in tool_contents[0]
