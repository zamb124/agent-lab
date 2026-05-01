"""
Платформенные тулы RAG: HTTP к сервису rag через RagClient (контекст компании только на сервере).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.tools import tool
from core.clients.rag_client import RagClient
from core.clients.service_client import ServiceClientError

_RAG_CREATE_NAMESPACE_DESCRIPTION = """
Регистрирует новое пространство имён (namespace) для документов RAG в текущей компании.

Ответ при успехе: success=true плюс поля ответа API (name, company_id, description, is_default и т.д. — как в POST /rag/api/v1/namespaces).
Ответ при ошибке: success=false, error (текст из HTTP/ServiceClient).

Параметры:
- name (строка): уникальное имя namespace внутри компании (как правило латиница, цифры, подчёркивание).
- description (строка, опционально): человекочитаемое описание.

Когда вызывать: нужно отдельное хранилище знаний под задачу; дальше в него клади текст через rag_add_text и ищи через rag_search.
""".strip()

_RAG_ADD_TEXT_DESCRIPTION = """
Добавляет в указанный RAG-namespace текст как один документ (синхронная индексация, без загрузки файла).

Компания и права проверяются на сервере: namespace должен быть создан для текущей компании (например через rag_create_namespace или UI RAG).

Ответ при успехе: success=true, document_id, document_name, namespace_id, status, provider.
Ответ при ошибке: success=false, error.

Параметры:
- namespace_id (строка): имя существующего namespace (то же значение, что поле name при создании).
- collection_id (строка): обязательный тег подкорпуса внутри namespace; попадает в metadata.collection_id (не передавай другое значение в metadata для этого ключа).
- text (строка): полный текст для индексации (не пустой после trim).
- document_name (строка, опционально): логическое имя документа; если не задано, сервер сгенерирует.
- metadata (объект, опционально): плоские или вложенные метаданные (ограничены размером и глубиной на API).
- document_id (строка, опционально): если задан, совпадает с идентификатором документа при повторной загрузке (перезапись чанков того же id).

Когда вызывать: нужно положить в базу знаний фрагмент текста (заметка, выжимка, инструкция) для последующего семантического поиска.
""".strip()

_RAG_SEARCH_DESCRIPTION = """
Семантический поиск по уже проиндексированным документам в указанном namespace.

Ответ при успехе: success=true, results (массив фрагментов: content, score, document_id, document_name, metadata, namespace), query, namespace_id, provider.
Ответ при ошибке: success=false, error.

Параметры:
- namespace_id (строка): имя namespace, зарегистрированного для компании.
- collection_id (строка): обязательный тег подкорпуса; мерджится в filters.collection_id для ограничения выдачи документами этой коллекции.
- query (строка): запрос естественным языком.
- limit (целое, по умолчанию 5): максимум результатов (разумно 3–20).
- filters (объект, опционально): дополнительные фильтры по metadata на стороне провайдера; collection_id вшивается поверх.

Когда вызывать: нужно найти релевантные куски из ранее добавленных в RAG текстов.
""".strip()


class RagCreateNamespaceArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(..., min_length=1, description="Имя нового namespace внутри компании.")
    description: Optional[str] = Field(
        None,
        description="Описание; можно не передавать.",
    )


class RagAddTextArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    namespace_id: str = Field(..., min_length=1, description="Имя существующего namespace.")
    collection_id: str = Field(
        ...,
        min_length=1,
        description="Подкорпус внутри namespace; кладётся в metadata.collection_id.",
    )
    text: str = Field(..., min_length=1, description="Текст для индексации.")
    document_name: Optional[str] = Field(None, description="Имя документа; опционально.")
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Метаданные документа (объект JSON); опционально.",
    )
    document_id: Optional[str] = Field(
        None,
        description="Явный id документа для идемпотентной перезаписи; опционально.",
    )


class RagSearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    namespace_id: str = Field(
        ...,
        min_length=1,
        description="Имя namespace, в который уже загружали документы (как при rag_create_namespace / rag_add_text).",
    )
    collection_id: str = Field(
        ...,
        min_length=1,
        description="Подкорпус; мерджится в filters.collection_id.",
    )
    query: str = Field(
        ...,
        min_length=1,
        description="Запрос естественным языком по смыслу фрагментов в этом namespace.",
    )
    limit: int = Field(5, ge=1, le=100)
    filters: Optional[Dict[str, Any]] = Field(None, description="Фильтры по metadata; опционально.")


@tool(
    name="rag_create_namespace",
    description=_RAG_CREATE_NAMESPACE_DESCRIPTION,
    tags=["rag", "knowledge"],
    args_schema=RagCreateNamespaceArgs,
)
async def rag_create_namespace(
    name: str,
    description: Optional[str] = None,
) -> dict:
    client = RagClient()
    try:
        raw = await client.create_namespace(name, description)
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc)}
    return {"success": True, **raw}


@tool(
    name="rag_add_text",
    description=_RAG_ADD_TEXT_DESCRIPTION,
    tags=["rag", "knowledge"],
    args_schema=RagAddTextArgs,
)
async def rag_add_text(
    namespace_id: str,
    collection_id: str,
    text: str,
    document_name: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    document_id: Optional[str] = None,
) -> dict:
    merged_meta: Dict[str, Any] = dict(metadata) if metadata is not None else {}
    if "collection_id" in merged_meta and merged_meta["collection_id"] != collection_id:
        raise ValueError(
            "metadata.collection_id не совпадает с аргументом collection_id",
        )
    merged_meta["collection_id"] = collection_id
    client = RagClient()
    try:
        raw = await client.ingest_text(
            namespace_id,
            text,
            document_name=document_name,
            metadata=merged_meta,
            document_id=document_id,
        )
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc)}
    return {"success": True, **raw}


@tool(
    name="rag_search",
    description=_RAG_SEARCH_DESCRIPTION,
    tags=["rag", "knowledge"],
    args_schema=RagSearchArgs,
)
async def rag_search(
    namespace_id: str,
    collection_id: str,
    query: str,
    limit: int = 5,
    filters: Optional[Dict[str, Any]] = None,
) -> dict:
    merged_filters: Dict[str, Any] = dict(filters) if filters is not None else {}
    if "collection_id" in merged_filters and merged_filters["collection_id"] != collection_id:
        raise ValueError(
            "filters.collection_id не совпадает с аргументом collection_id",
        )
    merged_filters["collection_id"] = collection_id
    client = RagClient()
    try:
        raw = await client.search(
            namespace_id,
            query,
            limit=limit,
            filters=merged_filters,
        )
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc)}
    return {"success": True, **raw}
