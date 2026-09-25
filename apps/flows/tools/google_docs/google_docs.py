"""
Платформенные тулы Google Docs: создание, чтение, редактирование, шаринг.

Auth: GoogleWorkspaceClient().resolve_auth (variables → user workspace OAuth →
prior docs/sheets credentials → company SA → OAuthInterrupt Connect Google).
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.clients.google_workspace_client import GoogleWorkspaceClient
from apps.flows.src.tools.decorator import tool
from core.clients.files_client import FilesClient
from core.clients.google_docs_client import GoogleDocsClient
from core.state import ExecutionState
from core.types import JsonObject, require_json_array, require_json_object

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
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, description="Заголовок документа.")
    file_id: str | None = Field(
        None,
        description="ID файла DOCX в платформе (результат fill_docx_template). Если не передан — пустой документ.",
    )


class GDocsDocumentIdArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    document_id: str = Field(..., min_length=1, description="ID документа Google Docs.")


class GDocsAppendTextArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    document_id: str = Field(..., min_length=1, description="ID документа.")
    text: str = Field(..., min_length=1, description="Текст для добавления в конец.")


class GDocsInsertTextArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    document_id: str = Field(..., min_length=1, description="ID документа.")
    text: str = Field(..., min_length=1, description="Текст для вставки.")
    index: int = Field(..., ge=1, description="Позиция вставки (1-based).")


class GDocsFindReplaceArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    document_id: str = Field(..., min_length=1, description="ID документа.")
    find: str = Field(..., min_length=1, description="Искомый текст.")
    replace: str = Field(..., description="Текст замены (может быть пустым для удаления).")
    match_case: bool = Field(True, description="Учитывать регистр.")


class GDocsDeleteRangeArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    document_id: str = Field(..., min_length=1, description="ID документа.")
    start_index: int = Field(..., ge=1, description="Начальный индекс (включительно).")
    end_index: int = Field(..., ge=2, description="Конечный индекс (исключительно).")


class GDocsShareArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    document_id: str = Field(..., min_length=1, description="ID документа.")
    email: str | None = Field(None, description="Email получателя.")
    role: str = Field("reader", description="Уровень доступа: reader, commenter, writer.")
    anyone: bool = Field(False, description="Если true — доступ всем по ссылке.")


def _require_state(state: ExecutionState | None) -> ExecutionState:
    if state is None:
        raise ValueError("Google Docs tools require ExecutionState")
    return state


async def _get_docs_client(
    state: ExecutionState | None,
    google_workspace_client: GoogleWorkspaceClient,
) -> GoogleDocsClient:
    execution_state = _require_state(state)
    material = await google_workspace_client.resolve_auth(execution_state)
    return GoogleDocsClient(
        credentials_json=material.credentials_json,
        access_token=material.access_token,
        subject=material.subject,
    )


# ── тулы ─────────────────────────────────────────────────────────


@tool(
    name="gdocs_create_document",
    description=_CREATE_DESCRIPTION,
    tags=["google_docs"],
    parameters_model=GDocsCreateArgs,
)
async def gdocs_create_document(
    title: str,
    file_id: str | None = None,
    state: ExecutionState | None = None,
    *,
    google_workspace_client: GoogleWorkspaceClient,
) -> JsonObject:
    client = await _get_docs_client(state, google_workspace_client)

    if file_id:
        docx_bytes = await FilesClient().get_bytes(file_id)
        result = require_json_object(
            await client.upload_docx(title, docx_bytes),
            "gdocs_create_document.upload_docx",
        )
        return {
            "document_id": result["id"],
            "title": result.get("name", title),
            "web_url": result.get("webViewLink", ""),
        }

    result = require_json_object(
        await client.create_document(title),
        "gdocs_create_document.create_document",
    )
    doc_id = str(result["documentId"])
    return {
        "document_id": doc_id,
        "title": result.get("title", title),
        "web_url": f"https://docs.google.com/document/d/{doc_id}/edit",
    }


@tool(
    name="gdocs_read_document",
    description=_READ_DESCRIPTION,
    tags=["google_docs"],
    parameters_model=GDocsDocumentIdArgs,
)
async def gdocs_read_document(
    document_id: str,
    state: ExecutionState | None = None,
    *,
    google_workspace_client: GoogleWorkspaceClient,
) -> JsonObject:
    client = await _get_docs_client(state, google_workspace_client)

    text = await client.read_as_text(document_id)
    return {"document_id": document_id, "text": text}


@tool(
    name="gdocs_append_text",
    description=_APPEND_DESCRIPTION,
    tags=["google_docs"],
    parameters_model=GDocsAppendTextArgs,
)
async def gdocs_append_text(
    document_id: str,
    text: str,
    state: ExecutionState | None = None,
    *,
    google_workspace_client: GoogleWorkspaceClient,
) -> JsonObject:
    client = await _get_docs_client(state, google_workspace_client)

    _ = await client.append_text(document_id, text)
    return {"document_id": document_id}


@tool(
    name="gdocs_insert_text",
    description=_INSERT_DESCRIPTION,
    tags=["google_docs"],
    parameters_model=GDocsInsertTextArgs,
)
async def gdocs_insert_text(
    document_id: str,
    text: str,
    index: int,
    state: ExecutionState | None = None,
    *,
    google_workspace_client: GoogleWorkspaceClient,
) -> JsonObject:
    client = await _get_docs_client(state, google_workspace_client)

    _ = await client.insert_text(document_id, text, index)
    return {"document_id": document_id}


@tool(
    name="gdocs_find_replace",
    description=_FIND_REPLACE_DESCRIPTION,
    tags=["google_docs"],
    parameters_model=GDocsFindReplaceArgs,
)
async def gdocs_find_replace(
    document_id: str,
    find: str,
    replace: str,
    match_case: bool = True,
    state: ExecutionState | None = None,
    *,
    google_workspace_client: GoogleWorkspaceClient,
) -> JsonObject:
    client = await _get_docs_client(state, google_workspace_client)

    result = require_json_object(
        await client.find_and_replace(document_id, find, replace, match_case=match_case),
        "gdocs_find_replace.result",
    )
    replies = require_json_array(result.get("replies", []), "gdocs_find_replace.replies")
    changed = 0
    if replies:
        reply = require_json_object(replies[0], "gdocs_find_replace.replies[0]")
        replace_all_text = require_json_object(
            reply.get("replaceAllText", {}),
            "gdocs_find_replace.replies[0].replaceAllText",
        )
        occurrences = replace_all_text.get("occurrencesChanged", 0)
        if not isinstance(occurrences, int) or isinstance(occurrences, bool):
            raise ValueError("gdocs_find_replace.occurrencesChanged must be an integer")
        changed = occurrences
    return {
        "document_id": document_id,
        "occurrences_changed": changed,
    }


@tool(
    name="gdocs_delete_range",
    description=_DELETE_RANGE_DESCRIPTION,
    tags=["google_docs"],
    parameters_model=GDocsDeleteRangeArgs,
)
async def gdocs_delete_range(
    document_id: str,
    start_index: int,
    end_index: int,
    state: ExecutionState | None = None,
    *,
    google_workspace_client: GoogleWorkspaceClient,
) -> JsonObject:
    client = await _get_docs_client(state, google_workspace_client)

    _ = await client.delete_range(document_id, start_index, end_index)
    return {"document_id": document_id}


@tool(
    name="gdocs_share_document",
    description=_SHARE_DESCRIPTION,
    tags=["google_docs"],
    parameters_model=GDocsShareArgs,
)
async def gdocs_share_document(
    document_id: str,
    email: str | None = None,
    role: str = "reader",
    anyone: bool = False,
    state: ExecutionState | None = None,
    *,
    google_workspace_client: GoogleWorkspaceClient,
) -> JsonObject:
    client = await _get_docs_client(state, google_workspace_client)

    if anyone:
        _ = await client.share_document_anyone(document_id, role=role)
    elif email:
        _ = await client.share_document(document_id, email, role=role)
    else:
        raise ValueError("Specify email or anyone=true to grant access.")

    return {"document_id": document_id}


__all__ = [
    "gdocs_create_document",
    "gdocs_read_document",
    "gdocs_append_text",
    "gdocs_insert_text",
    "gdocs_find_replace",
    "gdocs_delete_range",
    "gdocs_share_document",
]
