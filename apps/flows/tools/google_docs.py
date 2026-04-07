"""
Платформенные тулы Google Docs: создание, чтение, редактирование, шаринг.

Авторизация (порядок приоритета):
  1. Company-level: state.variables
     - "google_service_account"    — JSON ключа Service Account;
     - "google_impersonate_email"  — email для domain-wide delegation;
     - "google_access_token"       — статичный OAuth2 Bearer-токен.
  2. Per-user OAuth: integration_credentials в БД
     (get_context → company_id + user_id → OAuthService.get_valid_token)
  3. Нет credentials → FlowInterrupt с OAuthInterrupt (auto-resume после OAuth callback).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.runtime.exceptions import FlowInterrupt
from apps.flows.src.tools import tool
from core.clients.google_docs_client import GoogleDocsClient
from core.logging import get_logger
from core.state.interrupt import OAuthInterrupt

if TYPE_CHECKING:
    from core.state import ExecutionState

logger = get_logger(__name__)

GOOGLE_DOCS_SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]


async def _resolve_gdocs_client(state: "ExecutionState") -> GoogleDocsClient:
    """
    Трёхступенчатый резолв credentials для Google Docs.

    Возвращает GoogleDocsClient при успехе.
    При отсутствии credentials бросает FlowInterrupt(body=OAuthInterrupt(...))
    с auth URL и flow_context для auto-resume после OAuth callback.
    """
    credentials_json = state.variables.get("google_service_account")
    access_token = state.variables.get("google_access_token")
    subject = state.variables.get("google_impersonate_email")

    if not credentials_json and not access_token:
        from apps.flows.src.container import get_container
        from core.context import get_context
        from core.integrations.models import IntegrationProvider

        ctx = get_context()
        if ctx is None or ctx.active_company is None or ctx.user is None:
            raise ValueError("Контекст с активной компанией обязателен для Google Docs")

        container = get_container()
        credential = await container.oauth_service.get_valid_token(
            company_id=ctx.active_company.company_id,
            user_id=ctx.user.user_id,
            provider=IntegrationProvider.GOOGLE,
            service="docs",
        )
        if credential:
            access_token = credential.access_token
        else:
            flow_context: dict[str, Any] = {
                "flow_id": state.session_flow_id,
                "session_id": state.session_id,
                "task_id": state.task_id,
                "context_id": state.context_id,
                "skill_id": state.skill_id,
                "channel": "a2a",
                "user_id": ctx.user.user_id,
                "context_data": ctx.model_dump(mode="json"),
            }
            auth_url = await container.oauth_service.build_auth_url(
                provider=IntegrationProvider.GOOGLE,
                service="docs",
                scopes=GOOGLE_DOCS_SCOPES,
                user_id=ctx.user.user_id,
                company_id=ctx.active_company.company_id,
                flow_context=flow_context,
            )
            raise FlowInterrupt(
                body=OAuthInterrupt(
                    question="Для работы с Google Docs нужна авторизация Google",
                    auth_url=auth_url,
                    provider="google",
                    service="docs",
                ),
            )

    return GoogleDocsClient(
        credentials_json=credentials_json,
        access_token=access_token,
        subject=subject,
    )


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
    file_id: Optional[str] = Field(
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
    email: Optional[str] = Field(None, description="Email получателя.")
    role: str = Field("reader", description="Уровень доступа: reader, commenter, writer.")
    anyone: bool = Field(False, description="Если true — доступ всем по ссылке.")


# ── mock ответы ──────────────────────────────────────────────────


def _create_mock(args: dict, state: Any = None) -> dict:
    return {
        "success": True,
        "document_id": "mock_doc_id_123",
        "title": args.get("title", "Mock"),
        "web_url": "https://docs.google.com/document/d/mock_doc_id_123/edit",
    }


def _read_mock(args: dict, state: Any = None) -> dict:
    return {
        "success": True,
        "document_id": args.get("document_id", "mock_doc_id"),
        "text": "Mock document content.\nSecond paragraph.",
    }


def _append_mock(args: dict, state: Any = None) -> dict:
    return {"success": True, "document_id": args.get("document_id", "mock_doc_id")}


def _insert_mock(args: dict, state: Any = None) -> dict:
    return {"success": True, "document_id": args.get("document_id", "mock_doc_id")}


def _find_replace_mock(args: dict, state: Any = None) -> dict:
    return {
        "success": True,
        "document_id": args.get("document_id", "mock_doc_id"),
        "occurrences_changed": 1,
    }


def _delete_range_mock(args: dict, state: Any = None) -> dict:
    return {"success": True, "document_id": args.get("document_id", "mock_doc_id")}


def _share_mock(args: dict, state: Any = None) -> dict:
    return {"success": True, "document_id": args.get("document_id", "mock_doc_id")}


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
    file_id: Optional[str] = None,
    state: Optional["ExecutionState"] = None,
) -> dict:
    client = await _resolve_gdocs_client(state)

    if file_id:
        from apps.flows.src.container import get_container
        from core.files import S3ClientFactory

        container = get_container()
        record = await container.file_repository.get(file_id)
        if record is None:
            raise ValueError(f"Файл {file_id} не найден в хранилище")
        s3 = S3ClientFactory.create_client_for_bucket(record.s3_bucket)
        docx_bytes = await s3.download_bytes(record.s3_key)

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
    state: Optional["ExecutionState"] = None,
) -> dict:
    client = await _resolve_gdocs_client(state)
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
    state: Optional["ExecutionState"] = None,
) -> dict:
    client = await _resolve_gdocs_client(state)
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
    state: Optional["ExecutionState"] = None,
) -> dict:
    client = await _resolve_gdocs_client(state)
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
    state: Optional["ExecutionState"] = None,
) -> dict:
    client = await _resolve_gdocs_client(state)
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
    state: Optional["ExecutionState"] = None,
) -> dict:
    client = await _resolve_gdocs_client(state)
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
    email: Optional[str] = None,
    role: str = "reader",
    anyone: bool = False,
    state: Optional["ExecutionState"] = None,
) -> dict:
    client = await _resolve_gdocs_client(state)

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
