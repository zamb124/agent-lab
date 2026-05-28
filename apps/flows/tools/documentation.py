"""Tools Lara для публичного documentation assistant."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.tools.decorator import tool
from core.clients.rag_client import RagClient
from core.clients.service_client import ServiceClientError
from core.docs.assistant import (
    DOCS_RAG_NAMESPACE_ID,
    docs_collection_for_language,
    docs_search_card_blocks,
    docs_url_for_page,
    normalize_docs_language,
)
from core.types import JsonObject, JsonValue, require_json_array, require_json_object

if TYPE_CHECKING:
    from core.state import ExecutionState

JsonDict = JsonObject

_DOCS_SEARCH_DESCRIPTION = """
Ищет только по публичной документации Humanitec/NetWorkle и возвращает найденные
страницы с прямыми URL для перехода пользователя.

Когда вызывать:
- перед любым ответом по возможностям платформы, документации, API, сценариям или инструкциям;
- когда пользователь просит ссылку, раздел, страницу, пример или пошаговую инструкцию.

Ответ:
- success=true;
- results: фрагменты документации с title, url, content, score;
- blocks: карточки страниц для embed-чата, чтобы пользователь мог открыть нужные страницы.

Не используй этот tool для поиска вне документации.
""".strip()


class DocsSearchArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(
        ...,
        min_length=1,
        description="Короткий смысловой запрос по документации.",
    )
    limit: int = Field(
        5,
        ge=1,
        le=8,
        description="Сколько фрагментов вернуть. Обычно 3-5 достаточно.",
    )
    language: str | None = Field(
        None,
        description="Язык документации: ru, en или auto. Если не задан, берется язык страницы.",
    )


class DocsPrepareContextArgs(DocsSearchArgs):
    """Аргументы детерминированного поиска по docs перед LLM-вызовом ответа."""


def _state_variables(state: "ExecutionState") -> JsonObject:
    return state.variables


def _result_item(raw: JsonObject, *, current_page_url: str, language: str) -> JsonObject:
    metadata = raw.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    metadata_obj = require_json_object(metadata, "docs_search.result.metadata")
    fallback_url = str(metadata_obj.get("source_url") or metadata_obj.get("page_url") or "").strip()
    page_path = str(metadata_obj.get("page_path") or "").strip("/")
    title = str(
        metadata_obj.get("page_title")
        or raw.get("document_name")
        or raw.get("document_id")
        or "Documentation",
    ).strip()
    url = docs_url_for_page(
        page_path=page_path,
        language=language,
        current_page_url=current_page_url,
        fallback_url=fallback_url,
    )
    return {
        "title": title,
        "url": url,
        "canonical_url": fallback_url,
        "content": str(raw.get("content") or ""),
        "score": raw.get("score"),
        "document_id": raw.get("document_id"),
        "chunk_id": raw.get("chunk_id"),
        "page_path": page_path,
    }


def _prompt_context_from_results(results: list[JsonObject], *, language: str) -> tuple[str, str]:
    is_en = normalize_docs_language(language) == "en"
    if not results:
        empty = (
            "No relevant documentation pages were found for this question."
            if is_en
            else "По этому вопросу не найдено подходящих страниц документации."
        )
        return empty, ""

    context_lines: list[str] = []
    link_lines: list[str] = []
    for index, item in enumerate(results[:5], start=1):
        title = str(item.get("title") or "Documentation").strip()
        url = str(item.get("url") or "").strip()
        content = str(item.get("content") or "").strip()
        excerpt = content[:1200].strip()
        if len(content) > len(excerpt):
            excerpt = f"{excerpt.rstrip()}..."
        context_lines.append(
            "\n".join(
                part
                for part in (
                    f"{index}. {title}",
                    f"URL: {url}" if url else "",
                    excerpt,
                )
                if part
            )
        )
        if url:
            link_lines.append(f"- [{title}]({url})")
    return "\n\n".join(context_lines), "\n".join(link_lines[:3])


async def _search_docs(
    *,
    query: str,
    limit: int,
    language: str | None,
    state: "ExecutionState",
) -> JsonDict:
    variables = _state_variables(state)
    current_page_url = str(variables.get("page_url") or "").strip()
    resolved_language = normalize_docs_language(
        language,
        variables.get("docs_language"),
        variables.get("interface_language_code"),
        variables.get("user_language"),
        current_page_url,
    )
    collection_id = docs_collection_for_language(resolved_language)
    client = RagClient()
    try:
        raw = await client.search(
            DOCS_RAG_NAMESPACE_ID,
            query.strip(),
            limit=limit,
            filters={"collection_id": collection_id},
            channels={"semantic": True, "lexical": True},
            per_channel_top_k=max(limit * 3, 8),
            rerank=False,
        )
    except ServiceClientError as exc:
        return {
            "success": False,
            "error": str(exc),
            "query": query.strip(),
            "language": resolved_language,
            "namespace_id": DOCS_RAG_NAMESPACE_ID,
            "collection_id": collection_id,
            "results": [],
            "blocks": [],
            "prompt_context": str(exc),
            "prompt_links": "",
        }

    raw_results: list[JsonValue]
    raw_results_value = raw.get("results")
    if raw_results_value is None:
        raw_results = []
    else:
        raw_results = require_json_array(raw_results_value, "docs_search.results")

    results: list[JsonObject] = []
    seen_urls: set[str] = set()
    for index, item in enumerate(raw_results):
        if not isinstance(item, dict):
            continue
        result_item = _result_item(
            require_json_object(item, f"docs_search.results[{index}]"),
            current_page_url=current_page_url,
            language=resolved_language,
        )
        dedupe_key = str(result_item.get("url") or result_item.get("document_id") or "")
        if dedupe_key in seen_urls:
            continue
        seen_urls.add(dedupe_key)
        results.append(result_item)

    prompt_context, prompt_links = _prompt_context_from_results(
        results,
        language=resolved_language,
    )
    return {
        "success": True,
        "query": query.strip(),
        "language": resolved_language,
        "namespace_id": DOCS_RAG_NAMESPACE_ID,
        "collection_id": collection_id,
        "results": results,
        "blocks": docs_search_card_blocks(results, language=resolved_language),
        "prompt_context": prompt_context,
        "prompt_links": prompt_links,
    }


@tool(
    name="docs_search",
    description=_DOCS_SEARCH_DESCRIPTION,
    tags=["docs", "documentation", "rag", "lara"],
    parameters_model=DocsSearchArgs,
)
async def docs_search(
    query: str,
    limit: int = 5,
    language: str | None = None,
    *,
    state: "ExecutionState",
) -> JsonDict:
    return await _search_docs(query=query, limit=limit, language=language, state=state)


@tool(
    name="docs_prepare_context",
    description=(
        "Детерминированно ищет по публичной документации и возвращает готовый "
        "контекст prompt_context + prompt_links для ответа Lara без LLM tool-calling."
    ),
    tags=["docs", "documentation", "rag", "lara"],
    parameters_model=DocsPrepareContextArgs,
)
async def docs_prepare_context(
    query: str,
    limit: int = 5,
    language: str | None = None,
    *,
    state: "ExecutionState",
) -> JsonDict:
    return await _search_docs(query=query, limit=limit, language=language, state=state)
