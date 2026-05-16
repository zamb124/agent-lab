"""
Платформенные тулы Google Docs: создание, чтение, редактирование, шаринг.

Переменные агента (state.variables) для авторизации:
  google_service_account   — JSON ключ Service Account
  google_access_token      — статичный OAuth2 Bearer-токен
  google_impersonate_email — email для domain-wide delegation (только с SA)

Если ни одна переменная не задана — per-user OAuth:
  платформа предлагает пользователю авторизоваться, flow ставится на паузу,
  после OAuth callback автоматически продолжается.

Безопасность: тулы НЕ используют get_container().
Доступ к сервисам только через фасады platform_services.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.eval.platform_services import get_file_bytes, get_google_oauth_token
from apps.flows.src.tools.decorator import tool
from core.clients.google_docs_client import GoogleDocsClient
from core.logging import get_logger

if TYPE_CHECKING:
    from core.state import ExecutionState

logger = get_logger(__name__)
JsonDict = dict[str, Any]


# ── описания ─────────────────────────────────────────────────────

_CREATE_DESCRIPTION = """
Создаёт Google Docs документ.

Два режима:
1. Пустой документ: передайте только title.
2. Из DOCX-файла платформы: передайте title + file_id (например результат fill_docx_template).
   DOCX загружается в Google Drive и автоматически конвертируется в Google Docs.

Возвращает: document_id, title, web_url (ссылка для открытия).
""".strip()

_READ_DESCRIPTION = """
Читает содержимое Google Docs документа как plain text.

Параметры:
- document_id: ID документа Google Docs.

Возвращает: text (plain-text содержимое документа).
""".strip()

_APPEND_DESCRIPTION = """
Добавляет текст в конец Google Docs документа.

Параметры:
- document_id: ID документа.
- text: текст для добавления.
""".strip()

_INSERT_DESCRIPTION = """
Вставляет текст в указанную позицию Google Docs документа.

Параметры:
- document_id: ID документа.
- text: текст для вставки.
- index: позиция (1-based; 1 = начало документа).
""".strip()

_FIND_REPLACE_DESCRIPTION = """
Находит и заменяет текст во всём Google Docs документе.

Параметры:
- document_id: ID документа.
- find: искомый текст.
- replace: текст замены.
- match_case: учитывать регистр (по умолчанию true).
""".strip()

_DELETE_RANGE_DESCRIPTION = """
Удаляет контент из Google Docs документа по диапазону индексов.

Параметры:
- document_id: ID документа.
- start_index: начальный индекс (включительно).
- end_index: конечный индекс (исключительно).
""".strip()

_SHARE_DESCRIPTION = """
Выдаёт доступ к Google Docs документу.

Режимы:
- По email: передайте email, получатель получит доступ.
- По ссылке: передайте anyone=true, документ станет доступен всем по ссылке.

Параметры:
- document_id: ID документа.
- email: email получателя (если anyone=false).
- role: уровень доступа — reader, commenter, writer (по умолчанию reader).
- anyone: если true — доступ по ссылке для всех.
""".strip()

# ── args schemas ─────────────────────────────────────────────────


class GDocsCreateArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, description="Заголовок документа.")
    file_id: str | None = Field(
        None,
        description="ID файла DOCX в платформе (результат fill_docx_template). Если не передан — пустой документ.",
    )


class GDocsDocumentIdArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(..., min_length=1, description="ID документа Google Docs.")


class GDocsAppendTextArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(..., min_length=1, description="ID документа.")
    text: str = Field(..., min_length=1, description="Текст для добавления в конец.")


class GDocsInsertTextArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(..., min_length=1, description="ID документа.")
    text: str = Field(..., min_length=1, description="Текст для вставки.")
    index: int = Field(..., ge=1, description="Позиция вставки (1-based).")


class GDocsFindReplaceArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(..., min_length=1, description="ID документа.")
    find: str = Field(..., min_length=1, description="Искомый текст.")
    replace: str = Field(..., description="Текст замены (может быть пустым для удаления).")
    match_case: bool = Field(True, description="Учитывать регистр.")


class GDocsDeleteRangeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(..., min_length=1, description="ID документа.")
    start_index: int = Field(..., ge=1, description="Начальный индекс (включительно).")
    end_index: int = Field(..., ge=2, description="Конечный индекс (исключительно).")


class GDocsShareArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(..., min_length=1, description="ID документа.")
    email: str | None = Field(None, description="Email получателя.")
    role: str = Field("reader", description="Уровень доступа: reader, commenter, writer.")
    anyone: bool = Field(False, description="Если true — доступ всем по ссылке.")


# ── mock ответы ──────────────────────────────────────────────────


def _create_mock(args: JsonDict, state: Any = None) -> JsonDict:
    return {
        "success": True,
        "document_id": "mock_doc_id_123",
        "title": args.get("title", "Mock"),
        "web_url": "https://docs.google.com/document/d/mock_doc_id_123/edit",
    }


def _read_mock(args: JsonDict, state: Any = None) -> JsonDict:
    return {
        "success": True,
        "document_id": args.get("document_id", "mock_doc_id"),
        "text": "Mock document content.\nSecond paragraph.",
    }


def _append_mock(args: JsonDict, state: Any = None) -> JsonDict:
    return {"success": True, "document_id": args.get("document_id", "mock_doc_id")}


def _insert_mock(args: JsonDict, state: Any = None) -> JsonDict:
    return {"success": True, "document_id": args.get("document_id", "mock_doc_id")}


def _find_replace_mock(args: JsonDict, state: Any = None) -> JsonDict:
    return {
        "success": True,
        "document_id": args.get("document_id", "mock_doc_id"),
        "occurrences_changed": 1,
    }


def _delete_range_mock(args: JsonDict, state: Any = None) -> JsonDict:
    return {"success": True, "document_id": args.get("document_id", "mock_doc_id")}


def _share_mock(args: JsonDict, state: Any = None) -> JsonDict:
    return {"success": True, "document_id": args.get("document_id", "mock_doc_id")}


def _require_state(state: ExecutionState | None) -> ExecutionState:
    if state is None:
        raise ValueError("Google Docs tools require ExecutionState")
    return state


async def _get_docs_client(state: ExecutionState | None) -> GoogleDocsClient:
    execution_state = _require_state(state)
    credentials_json = execution_state.variables.get("google_service_account")
    access_token = execution_state.variables.get("google_access_token")
    subject = execution_state.variables.get("google_impersonate_email")

    if not credentials_json and not access_token:
        access_token = await get_google_oauth_token(execution_state, service="docs")

    return GoogleDocsClient(
        credentials_json=credentials_json,
        access_token=access_token,
        subject=subject,
    )


# ── тулы ─────────────────────────────────────────────────────────


@tool(
    name="gdocs_create_document",
    description=_CREATE_DESCRIPTION,
    tags=["google_docs", "documents"],
    mock_response=_create_mock,
    args_schema=GDocsCreateArgs,
)
async def gdocs_create_document(
    title: str,
    file_id: str | None = None,
    state: ExecutionState | None = None,
) -> JsonDict:
    client = await _get_docs_client(state)

    if file_id:
        docx_bytes = await get_file_bytes(file_id)
        result = await client.upload_docx(title, docx_bytes)
        return {
            "success": True,
            "document_id": result["id"],
            "title": result.get("name", title),
            "web_url": result.get("webViewLink", ""),
        }

    result = await client.create_document(title)
    doc_id = result["documentId"]
    return {
        "success": True,
        "document_id": doc_id,
        "title": result.get("title", title),
        "web_url": f"https://docs.google.com/document/d/{doc_id}/edit",
    }


@tool(
    name="gdocs_read_document",
    description=_READ_DESCRIPTION,
    tags=["google_docs", "documents"],
    mock_response=_read_mock,
    args_schema=GDocsDocumentIdArgs,
)
async def gdocs_read_document(
    document_id: str,
    state: ExecutionState | None = None,
) -> JsonDict:
    client = await _get_docs_client(state)

    text = await client.read_as_text(document_id)
    return {"success": True, "document_id": document_id, "text": text}


@tool(
    name="gdocs_append_text",
    description=_APPEND_DESCRIPTION,
    tags=["google_docs", "documents"],
    mock_response=_append_mock,
    args_schema=GDocsAppendTextArgs,
)
async def gdocs_append_text(
    document_id: str,
    text: str,
    state: ExecutionState | None = None,
) -> JsonDict:
    client = await _get_docs_client(state)

    await client.append_text(document_id, text)
    return {"success": True, "document_id": document_id}


@tool(
    name="gdocs_insert_text",
    description=_INSERT_DESCRIPTION,
    tags=["google_docs", "documents"],
    mock_response=_insert_mock,
    args_schema=GDocsInsertTextArgs,
)
async def gdocs_insert_text(
    document_id: str,
    text: str,
    index: int,
    state: ExecutionState | None = None,
) -> JsonDict:
    client = await _get_docs_client(state)

    await client.insert_text(document_id, text, index)
    return {"success": True, "document_id": document_id}


@tool(
    name="gdocs_find_replace",
    description=_FIND_REPLACE_DESCRIPTION,
    tags=["google_docs", "documents"],
    mock_response=_find_replace_mock,
    args_schema=GDocsFindReplaceArgs,
)
async def gdocs_find_replace(
    document_id: str,
    find: str,
    replace: str,
    match_case: bool = True,
    state: ExecutionState | None = None,
) -> JsonDict:
    client = await _get_docs_client(state)

    result = await client.find_and_replace(
        document_id, find, replace, match_case=match_case
    )
    replies = result.get("replies", [{}])
    changed = 0
    if replies:
        changed = replies[0].get("replaceAllText", {}).get("occurrencesChanged", 0)
    return {
        "success": True,
        "document_id": document_id,
        "occurrences_changed": changed,
    }


@tool(
    name="gdocs_delete_range",
    description=_DELETE_RANGE_DESCRIPTION,
    tags=["google_docs", "documents"],
    mock_response=_delete_range_mock,
    args_schema=GDocsDeleteRangeArgs,
)
async def gdocs_delete_range(
    document_id: str,
    start_index: int,
    end_index: int,
    state: ExecutionState | None = None,
) -> JsonDict:
    client = await _get_docs_client(state)

    await client.delete_range(document_id, start_index, end_index)
    return {"success": True, "document_id": document_id}


@tool(
    name="gdocs_share_document",
    description=_SHARE_DESCRIPTION,
    tags=["google_docs", "documents"],
    mock_response=_share_mock,
    args_schema=GDocsShareArgs,
)
async def gdocs_share_document(
    document_id: str,
    email: str | None = None,
    role: str = "reader",
    anyone: bool = False,
    state: ExecutionState | None = None,
) -> JsonDict:
    client = await _get_docs_client(state)

    if anyone:
        await client.share_document_anyone(document_id, role=role)
    elif email:
        await client.share_document(document_id, email, role=role)
    else:
        raise ValueError("Укажите email или anyone=true для выдачи доступа.")

    return {"success": True, "document_id": document_id}


__all__ = [
    "gdocs_create_document",
    "gdocs_read_document",
    "gdocs_append_text",
    "gdocs_insert_text",
    "gdocs_find_replace",
    "gdocs_delete_range",
    "gdocs_share_document",
]
