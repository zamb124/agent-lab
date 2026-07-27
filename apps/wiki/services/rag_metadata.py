"""
Метаданные страниц wiki в RAG и сборка фильтров поиска.

Единственная точка, где формируются поля чанка: сервис и воркер пишут через
неё, поэтому набор полей не может разъехаться между путями индексации.

Все значения — скаляры. pgvector-провайдер умеет сравнивать только
string/number/boolean (`_metadata_expr_for_scalar`), поэтому массивы в
метаданные не попадают: структурные условия считаются в Postgres и приезжают
сюда готовым списком идентификаторов.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from pydantic import Field

from apps.wiki.base_model import WikiBaseModel
from apps.wiki.models.domain import WikiPage, WikiVisibility
from core.rag.models import RAGMetadata, RAGMetadataFilter

WIKI_SOURCE_KIND: Final[str] = "wiki_page"
"""Значение `source_kind` у чанков wiki.

В общем knowledge-namespace рядом лежат заметки Networkle, поэтому без этого
поля нельзя ограничить поиск только страницами wiki.
"""

MAX_PAGE_ID_FILTER_SIZE: Final[int] = 200
"""Предел размера списка в `$in`.

Более длинный список превращает запрос в перечисление половины базы; в этом
случае вызывающий обязан сузить область через `wiki_root_page_id`, а не молча
потерять часть результатов.
"""


class WikiRagFilterOverflowError(ValueError):
    """Список страниц для фильтра длиннее допустимого."""


def build_wiki_chunk_metadata(page: WikiPage, heading_path: str = "") -> RAGMetadata:
    """Метаданные чанка страницы.

    `ttl_seconds: 0` — страницы живут, пока живёт страница, и удаляются явной
    деиндексацией, а не по времени.
    """
    metadata: RAGMetadata = {
        "document_id": page.wiki_page_id,
        "company_id": page.company_id,
        "source_kind": WIKI_SOURCE_KIND,
        "ttl_seconds": 0,
        "wiki_namespace": page.namespace,
        "wiki_page_id": page.wiki_page_id,
        "wiki_parent_page_id": page.parent_page_id if page.parent_page_id else "",
        "wiki_root_page_id": page.root_page_id,
        "wiki_depth": page.depth,
        "wiki_visibility": page.visibility.value,
        "wiki_is_published": page.is_published,
        "wiki_title": page.title,
        "wiki_heading_path": heading_path,
        "wiki_updated_at_ts": int(page.updated_at.timestamp()),
        "wiki_author_user_id": page.created_by_user_id,
        "wiki_last_editor_user_id": page.last_edited_by_user_id,
    }
    return metadata


class WikiSearchFilter(WikiBaseModel):
    """Типизированные условия поиска.

    Агент задаёт именно эти поля; сырой JSON фильтра от модели не принимается,
    иначе в запрос уедет произвольное выражение мимо изоляции по namespace.
    """

    namespace: str = Field(..., min_length=1)
    root_page_id: str | None = None
    parent_page_id: str | None = None
    max_depth: int | None = Field(default=None, ge=0)
    published_only: bool = False
    updated_after: datetime | None = None
    editor_user_id: str | None = None
    visibility: WikiVisibility | None = None
    allowed_page_ids: list[str] | None = None
    excluded_page_ids: list[str] | None = None


def ensure_page_filter_size(size: int, kind: str = "перечисленных") -> None:
    """Проверить, что список идентификаторов помещается в фильтр `$in`/`$nin`."""
    if size > MAX_PAGE_ID_FILTER_SIZE:
        message = f"Список {kind} страниц ({size}) превышает предел {MAX_PAGE_ID_FILTER_SIZE}"
        raise WikiRagFilterOverflowError(f"{message}; сузьте поиск через root_page_id")


def build_wiki_search_filter(spec: WikiSearchFilter) -> RAGMetadataFilter:
    """Собрать фильтр метаданных из типизированных условий.

    Ограничение по `source_kind` и `wiki_namespace` добавляется всегда: поиск
    без границы namespace для wiki не существует.
    """
    conditions: list[RAGMetadataFilter] = [
        {"source_kind": {"$eq": WIKI_SOURCE_KIND}},
        {"wiki_namespace": {"$eq": spec.namespace}},
    ]

    if spec.root_page_id:
        conditions.append({"wiki_root_page_id": {"$eq": spec.root_page_id}})
    if spec.parent_page_id:
        conditions.append({"wiki_parent_page_id": {"$eq": spec.parent_page_id}})
    if spec.max_depth is not None:
        conditions.append({"wiki_depth": {"$lte": spec.max_depth}})
    if spec.published_only:
        conditions.append({"wiki_is_published": {"$eq": True}})
    if spec.updated_after is not None:
        conditions.append({"wiki_updated_at_ts": {"$gte": int(spec.updated_after.timestamp())}})
    if spec.editor_user_id:
        conditions.append({"wiki_last_editor_user_id": {"$eq": spec.editor_user_id}})
    if spec.visibility is not None:
        conditions.append({"wiki_visibility": {"$eq": spec.visibility.value}})

    if spec.allowed_page_ids is not None:
        ensure_page_filter_size(len(spec.allowed_page_ids), "разрешённых")
        conditions.append({"wiki_page_id": {"$in": list(spec.allowed_page_ids)}})

    if spec.excluded_page_ids:
        ensure_page_filter_size(len(spec.excluded_page_ids), "исключённых")
        conditions.append({"wiki_page_id": {"$nin": list(spec.excluded_page_ids)}})

    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


__all__ = [
    "MAX_PAGE_ID_FILTER_SIZE",
    "ensure_page_filter_size",
    "WIKI_SOURCE_KIND",
    "WikiRagFilterOverflowError",
    "WikiSearchFilter",
    "build_wiki_chunk_metadata",
    "build_wiki_search_filter",
]
