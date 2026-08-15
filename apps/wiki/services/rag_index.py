"""
Индексация страниц wiki в RAG.

Индексация включена всегда и не имеет пользовательского флага: страница
попадает в поиск при каждом сохранении. Слой определяется вычисленной
видимостью:

* `company` — общий knowledge-namespace компании, тот же, куда Networkle пишет
  заметки. Такую страницу сразу находит любой `rag_search` и ассистент в любом
  сервисе, отдельный инструмент не нужен;
* `restricted` — служебный namespace `wiki-restricted-{namespace}`. В общий
  индекс ограниченная страница не попадает физически, поэтому не может всплыть
  в ответе человеку без доступа.

Перенос между слоями всегда полный: частично переиндексированное поддерево
означает утечку, поэтому при ошибке поднимается исключение, а не «сколько
успели».
"""

from __future__ import annotations

from typing import Final

from apps.wiki.models.domain import WikiPage, WikiVisibility
from apps.wiki.services.rag_metadata import build_wiki_chunk_metadata
from core.clients.rag_client import RagClient
from core.clients.service_client import ServiceClientError
from core.logging import get_logger
from core.models.identity_models import NamespaceKind
from core.namespace.service import NamespaceService
from core.rag.models import RAGMetadataFilter, RAGSearchResult
from core.types import JsonValue, require_json_array, require_json_object

logger = get_logger(__name__)

RESTRICTED_NAMESPACE_PREFIX: Final[str] = "wiki-restricted-"


def restricted_namespace_id(namespace: str) -> str:
    """Служебный namespace для страниц с ограниченным доступом."""
    return f"{RESTRICTED_NAMESPACE_PREFIX}{namespace}"


def target_namespace_id(namespace: str, visibility: WikiVisibility) -> str:
    if visibility == WikiVisibility.COMPANY:
        return namespace
    return restricted_namespace_id(namespace)


def _parse_search_results(raw: JsonValue) -> list[RAGSearchResult]:
    items = require_json_array(raw, "wiki RAG search results")
    return [
        RAGSearchResult.model_validate(require_json_object(item, "wiki RAG search result"))
        for item in items
    ]


class WikiRagIndexService:
    """Запись и перенос страниц между слоями индекса."""

    def __init__(
        self,
        rag_client: RagClient,
        namespace_service: NamespaceService,
    ) -> None:
        self._rag: RagClient = rag_client
        self._namespace_service: NamespaceService = namespace_service
        self._ensured_restricted_namespaces: set[str] = set()

    async def index_page(self, page: WikiPage) -> None:
        """Записать страницу в слой, соответствующий её видимости."""
        text = page.text_markdown.strip()
        if not text:
            # Пустую страницу индексировать нечем; старую версию убираем,
            # иначе в поиске останется текст, которого уже нет.
            await self.remove_page(page)
            return

        if page.rag_visibility == WikiVisibility.RESTRICTED:
            await self.ensure_restricted_namespace(page.namespace)

        _ = await self._rag.ingest_text(
            target_namespace_id(page.namespace, page.rag_visibility),
            text,
            document_name=page.title if page.title else page.wiki_page_id,
            document_id=page.wiki_page_id,
            metadata=build_wiki_chunk_metadata(page),
        )

    async def remove_page(self, page: WikiPage) -> None:
        """Убрать страницу из обоих слоёв.

        Чистим и общий, и служебный namespace: видимость могла измениться
        между записью и удалением, и остаток в старом слое — та самая утечка.
        """
        await self.remove_page_from_namespace(page.wiki_page_id, page.namespace)

    async def remove_page_from_namespace(self, wiki_page_id: str, namespace: str) -> None:
        for namespace_id in (namespace, restricted_namespace_id(namespace)):
            await self._drop_index(namespace_id, wiki_page_id)

    async def _drop_index(self, namespace_id: str, wiki_page_id: str) -> None:
        """Снять документ с индекса; отсутствие записи — штатный исход.

        Деиндексация вызывается перед каждой записью и при удалении, поэтому
        обычно документа в одном из двух слоёв нет. 404 здесь означает
        «уже нет», то есть требуемое состояние достигнуто. Все остальные
        ошибки пробрасываются: незамеченный сбой оставил бы в общем индексе
        текст страницы, которую только что закрыли.
        """
        try:
            _ = await self._rag.delete_document_index(namespace_id, wiki_page_id)
        except ServiceClientError as exc:
            if exc.status_code == 404:
                return
            raise

    async def reindex_subtree(self, pages: list[WikiPage]) -> None:
        """Переписать индекс для поддерева после смены доступа или переноса.

        Каждая страница сначала снимается из обоих слоёв, потом пишется в
        актуальный: так порядок обхода не может оставить дубль в старом слое.
        """
        for page in pages:
            await self.remove_page(page)
            await self.index_page(page)
        logger.info(
            "wiki.rag.subtree_reindexed",
            extra={"pages": len(pages)},
        )

    async def ensure_restricted_namespace(self, namespace: str) -> None:
        """Создать служебный namespace под ограниченные страницы.

        Слой появляется лениво — в момент, когда на странице впервые
        ограничили доступ. Результат запоминается на время жизни процесса:
        создание идемпотентно, но лишний вызов на каждое сохранение не нужен.
        """
        restricted_id = restricted_namespace_id(namespace)
        if restricted_id in self._ensured_restricted_namespaces:
            return
        _ = await self._rag.create_namespace(
            restricted_id,
            description=f"Ограниченные страницы wiki пространства {namespace}",
        )
        # Dual-write platform_namespace FGA in-process (RAG HTTP create may
        # already do this; fail-closed ensure here so ingest can_view works).
        _ = await self._namespace_service.get_or_create(
            restricted_id,
            description=f"Ограниченные страницы wiki пространства {namespace}",
            kind=NamespaceKind.TECHNICAL,
        )
        self._ensured_restricted_namespaces.add(restricted_id)

    async def search(
        self,
        namespace: str,
        query: str,
        limit: int,
        filters: RAGMetadataFilter,
        *,
        include_restricted: bool,
    ) -> list[RAGSearchResult]:
        """Смысловой поиск по слоям пространства.

        Служебный слой подключается только когда пользователю доступна хотя бы
        одна ограниченная страница: до первого ограничения этого namespace в
        RAG попросту нет. Отсев по правам уже сделан фильтром, который собрал
        вызывающий.
        """
        if not include_restricted:
            payload = require_json_object(
                await self._rag.search(namespace, query, limit=limit, filters=filters),
                "wiki RAG search response",
            )
            return _parse_search_results(payload.get("results"))[:limit]

        payload = require_json_object(
            await self._rag.global_search(
                [namespace, restricted_namespace_id(namespace)],
                query,
                limit=limit,
                filters=filters,
            ),
            "wiki RAG global search response",
        )
        raw_by_namespace = payload.get("results")
        if not isinstance(raw_by_namespace, dict):
            raise ValueError("RAG global search: results должен быть объектом")

        hits: list[RAGSearchResult] = []
        for raw_results in raw_by_namespace.values():
            hits.extend(_parse_search_results(raw_results))
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:limit]


__all__ = [
    "RESTRICTED_NAMESPACE_PREFIX",
    "WikiRagIndexService",
    "restricted_namespace_id",
    "target_namespace_id",
]
