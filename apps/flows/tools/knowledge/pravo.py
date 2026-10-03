"""
Тулы Официального интернет-портала правовой информации (ips.pravo.gov.ru).

Тонкие обёртки над PravoClient; семантический поиск по НПА — PravoClient.document_rag_search.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.tools.decorator import tool
from core.clients.pravo import PravoClient
from core.types import JsonObject

_PRAVO_CATALOG_SEARCH_DESCRIPTION = """
Поиск нормативных актов на ips.pravo.gov.ru через HTTP API POST /api/ips/legislation/search.json
(аналог гибридного поиска в веб-интерфейсе).

Возвращает список записей (title, url на legislation/document, document_hash из поля docs).
Ошибки IPS/HTTP пробрасываются.

Параметры:
- keyword (строка): фраза; слова разбиваются на лексемы и передаются в IPS через разделитель ``&``.
- page (целое, по умолчанию 1): номер страницы выдачи.
""".strip()

_PRAVO_DOCUMENT_RAG_SEARCH_DESCRIPTION = """
Семантический поиск по одному нормативному акту с ips.pravo.gov.ru в вашем RAG-namespace.

Логика (на клиенте): поиск только по чанкам этого документа (стабильный document_id от hash IPS).
Если документ ещё не загружен в RAG для пары namespace_id + collection_id — текст скачивается с IPS,
индексируется, затем повторяется поиск по запросу.

Ответ содержит ``documents``: список из одного объекта с полями источника IPS
(hash, source_url, rag_document_id, title при наличии, indexed_into_rag_this_call, опционально text_character_count).
Ошибки IPS/RAG/ServiceClient пробрасываются.

Параметры:
- namespace_id (строка): имя RAG namespace компании.
- collection_id (строка): подкорпус (metadata.collection_id / filters.collection_id).
- document_ref (строка): полный URL …/legislation/document?...&hash=… **или** 64-символьный hash hex.
- query (строка): вопрос естественным языком по содержанию акта.
- limit (целое, по умолчанию 5): число фрагментов (как у rag_search).
- force_refresh (bool, по умолчанию false): принудительно перезагрузить текст с IPS и переиндексировать перед поиском.
""".strip()


class PravoCatalogSearchArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    keyword: str = Field(..., min_length=1, description="Ключевые слова для расширенного поиска IPS.")
    page: int = Field(1, ge=1, description="Страница выдачи IPS.")


class PravoDocumentRagSearchArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

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
    limit: int = Field(5, ge=1, le=100, description="Максимум фрагментов в ответе (как у rag_search).")
    force_refresh: bool = Field(
        False,
        description="Перезагрузить текст с IPS и переиндексировать даже если в RAG уже есть чанки.",
    )


@tool(
    name="pravo_catalog_search",
    description=_PRAVO_CATALOG_SEARCH_DESCRIPTION,
    tags=["knowledge"],
    parameters_model=PravoCatalogSearchArgs,
)
async def pravo_catalog_search(keyword: str, page: int = 1) -> JsonObject:
    hits = await PravoClient().search_catalog(keyword=keyword, page=page)
    items: list[JsonObject] = [
        {"title": h.title, "url": h.url, "document_hash": h.document_hash} for h in hits
    ]
    return {
        "keyword": keyword,
        "page": page,
        "items": items,
        "count": len(items),
    }


@tool(
    name="pravo_document_rag_search",
    description=_PRAVO_DOCUMENT_RAG_SEARCH_DESCRIPTION,
    tags=["knowledge"],
    parameters_model=PravoDocumentRagSearchArgs,
)
async def pravo_document_rag_search(
    namespace_id: str,
    collection_id: str,
    document_ref: str,
    query: str,
    limit: int = 5,
    force_refresh: bool = False,
) -> JsonObject:
    return await PravoClient().document_rag_search(
        namespace_id=namespace_id,
        collection_id=collection_id,
        document_ref=document_ref,
        query=query,
        limit=limit,
        force_refresh=force_refresh,
    )
