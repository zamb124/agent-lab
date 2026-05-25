"""
Тулы Официального интернет-портала правовой информации (ips.pravo.gov.ru).

Семантический поиск по тексту НПА в RAG: если документ ещё не индексирован в подкорпусе,
сначала загружается с IPS и кладётся в RAG, затем выполняется поиск.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.tools.decorator import tool
from core.clients.pravo import (
    PravoClient,
    PravoClientError,
)
from core.clients.rag_client import RagClient
from core.clients.service_client import ServiceClientError

JsonDict = dict[str, Any]

_PRAVO_CATALOG_SEARCH_DESCRIPTION = """
Поиск нормативных актов на ips.pravo.gov.ru через HTTP API POST /api/ips/legislation/search.json
(аналог гибридного поиска в веб-интерфейсе).

Возвращает список записей (title, url на legislation/document, document_hash из поля docs).

Параметры:
- keyword (строка): фраза; слова разбиваются на лексемы и передаются в IPS через разделитель ``&``.
- page (целое, по умолчанию 1): номер страницы выдачи.
""".strip()

_PRAVO_DOCUMENT_RAG_SEARCH_DESCRIPTION = """
Семантический поиск по одному нормативному акту с ips.pravo.gov.ru в вашем RAG-namespace.

Логика: выполняется поиск только по чанкам этого документа (стабильный document_id от hash IPS).
Если документ ещё не загружен в RAG для пары namespace_id + collection_id — текст скачивается с IPS,
индексируется (rag_add_text), затем повторяется поиск по запросу.

Ответ при успехе дополнительно содержит ``documents``: список из одного объекта с полями источника IPS
(hash, source_url, rag_document_id, title при наличии, indexed_into_rag_this_call, опционально text_character_count).
Это не бинарные вложения платформы, а канонические ссылки на акт и метаданные для пользователя/агента.

Параметры:
- namespace_id (строка): имя RAG namespace компании.
- collection_id (строка): подкорпус (metadata.collection_id / filters.collection_id).
- document_ref (строка): полный URL …/legislation/document?...&hash=… **или** 64-символьный hash hex.
- query (строка): вопрос естественным языком по содержанию акта.
- limit (целое, по умолчанию 5): число фрагментов (как у rag_search).
- force_refresh (bool, по умолчанию false): принудительно перезагрузить текст с IPS и переиндексировать перед поиском.
""".strip()


class PravoCatalogSearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    keyword: str = Field(..., min_length=1, description="Ключевые слова для расширенного поиска IPS.")
    page: int = Field(1, ge=1, description="Страница выдачи IPS.")


class PravoDocumentRagSearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    namespace_id: str = Field(..., min_length=1, description="Имя RAG namespace.")
    collection_id: str = Field(
        ...,
        min_length=1,
        description="Подкорпус внутри namespace (как у rag_add_text / rag_search).",
    )
    document_ref: str = Field(
        ...,
        min_length=1,
        description="URL legislation/document с hash или отдельно 64-символьный hash.",
    )
    query: str = Field(..., min_length=1, description="Семантический запрос по тексту акта.")
    limit: int = Field(5, ge=1, le=100)
    force_refresh: bool = Field(
        False,
        description="Перезагрузить текст с IPS и переиндексировать даже если в RAG уже есть чанки.",
    )


def _doc_filters(collection_id: str, rag_document_id: str) -> dict[str, Any]:
    return {
        "$and": [
            {"collection_id": collection_id},
            {"document_id": rag_document_id},
        ],
    }


def _ips_document_row(
    *,
    doc_hash: str,
    source_url: str,
    rag_document_id: str,
    title: str | None,
    indexed_into_rag_this_call: bool,
    text_character_count: int | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "document_hash": doc_hash,
        "source_url": source_url,
        "rag_document_id": rag_document_id,
        "title": title,
        "indexed_into_rag_this_call": indexed_into_rag_this_call,
    }
    if text_character_count is not None:
        row["text_character_count"] = text_character_count
    return row


async def _run_rag_search(
    *,
    namespace_id: str,
    query: str,
    limit: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    client = RagClient()
    return await client.search(
        namespace_id,
        query,
        limit=limit,
        filters=filters,
    )


@tool(
    name="pravo_catalog_search",
    description=_PRAVO_CATALOG_SEARCH_DESCRIPTION,
    tags=["law", "rag", "knowledge", "external"],
    parameters_model=PravoCatalogSearchArgs,
)
async def pravo_catalog_search(keyword: str, page: int = 1) -> JsonDict:
    try:
        hits = await PravoClient().search_catalog(keyword=keyword, page=page)
    except PravoClientError as exc:
        msg = str(exc).strip() or type(exc).__name__
        return {"success": False, "error": msg}
    except (ValueError, ServiceClientError) as exc:
        msg = str(exc).strip() or type(exc).__name__
        return {"success": False, "error": msg}
    except Exception as exc:
        msg = str(exc).strip() or type(exc).__name__
        return {"success": False, "error": msg}

    items: list[dict[str, Any]] = [
        {"title": h.title, "url": h.url, "document_hash": h.document_hash} for h in hits
    ]
    return {
        "success": True,
        "keyword": keyword,
        "page": page,
        "items": items,
        "count": len(items),
    }


@tool(
    name="pravo_document_rag_search",
    description=_PRAVO_DOCUMENT_RAG_SEARCH_DESCRIPTION,
    tags=["law", "rag", "knowledge", "external"],
    parameters_model=PravoDocumentRagSearchArgs,
)
async def pravo_document_rag_search(
    namespace_id: str,
    collection_id: str,
    document_ref: str,
    query: str,
    limit: int = 5,
    force_refresh: bool = False,
) -> JsonDict:
    pravo_client = PravoClient()
    try:
        doc_hash = PravoClient.extract_legislation_document_hash(document_ref)
        source_url = PravoClient.legislation_document_api_url(doc_hash)
        rag_document_id = PravoClient.rag_document_id(doc_hash)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    filters = _doc_filters(collection_id, rag_document_id)
    ingested = False

    if not force_refresh:
        try:
            raw_first = await _run_rag_search(
                namespace_id=namespace_id,
                query=query,
                limit=limit,
                filters=filters,
            )
        except ServiceClientError as exc:
            return {"success": False, "error": str(exc)}
        results_first: list[Any] = list(raw_first.get("results", []))
        if results_first:
            return {
                "success": True,
                "document_ingested": False,
                "pravo_document_hash": doc_hash,
                "source_url": source_url,
                "rag_document_id": rag_document_id,
                "documents": [
                    _ips_document_row(
                        doc_hash=doc_hash,
                        source_url=source_url,
                        rag_document_id=rag_document_id,
                        title=None,
                        indexed_into_rag_this_call=False,
                    ),
                ],
                **raw_first,
            }

    try:
        doc = await pravo_client.fetch_legislation_document(document_hash=doc_hash)
    except PravoClientError as exc:
        msg = str(exc).strip() or type(exc).__name__
        return {"success": False, "error": msg}
    except Exception as exc:
        msg = str(exc).strip() or type(exc).__name__
        return {"success": False, "error": msg}

    merged_meta: dict[str, Any] = {
        "collection_id": collection_id,
        "pravo_ips": True,
        "pravo_document_hash": doc_hash,
        "pravo_source_url": doc.source_url,
    }
    if doc.title:
        merged_meta["pravo_title"] = doc.title

    document_name = doc.title if doc.title else f"IPS {doc_hash[:16]}…"

    rag = RagClient()
    try:
        await rag.ingest_text(
            namespace_id,
            doc.text,
            document_name=document_name,
            metadata=merged_meta,
            document_id=rag_document_id,
        )
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc)}
    ingested = True

    try:
        raw_second = await _run_rag_search(
            namespace_id=namespace_id,
            query=query,
            limit=limit,
            filters=filters,
        )
    except ServiceClientError as exc:
        return {"success": False, "error": str(exc)}

    return {
        "success": True,
        "document_ingested": ingested,
        "pravo_document_hash": doc_hash,
        "source_url": source_url,
        "rag_document_id": rag_document_id,
        "documents": [
            _ips_document_row(
                doc_hash=doc_hash,
                source_url=source_url,
                rag_document_id=rag_document_id,
                title=doc.title,
                indexed_into_rag_this_call=ingested,
                text_character_count=len(doc.text),
            ),
        ],
        **raw_second,
    }
