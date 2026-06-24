"""Индексация документов Office-каталога в RAG (отдельный namespace на catalog_id)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from apps.office.db.models import OfficeDocumentBinding, OfficeDocumentCatalog
from apps.office.models.api import (
    OfficeCatalogRagIndexBindingItem,
    OfficeCatalogRagIndexEnableResponse,
    OfficeCatalogRagIndexRebuildResponse,
    OfficeCatalogRagIndexSettingsResponse,
    OfficeCatalogRagIndexStatusResponse,
    OfficeCatalogRagIndexStatusTotals,
    OfficeCatalogSemanticSearchHit,
    OfficeCatalogSemanticSearchResponse,
)
from apps.rag_worker.broker import broker as rag_worker_broker
from apps.rag_worker.tasks.indexing_tasks import RAG_INDEX_OFFICE_CATALOG_TASK_NAME
from core.clients.rag_client import RagClient
from core.clients.service_client import ServiceClientError
from core.context import get_context
from core.logging import get_logger
from core.rag.models import RAGMetadata, RAGSearchResult
from core.tasks.kicker import kiq_task_name_with_context
from core.types import JsonObject, JsonValue, require_json_object

if TYPE_CHECKING:
    from apps.office.db.repositories.catalog_repository import CatalogRepository
    from apps.office.db.repositories.document_binding_repository import DocumentBindingRepository
    from core.files.file_repository import FileRepository

logger = get_logger(__name__)

OFFICE_CATALOG_RAG_NAMESPACE_PREFIX = "office-catalog-"


class OfficeCatalogRagIndexService:
    def __init__(
        self,
        catalog_repository: CatalogRepository,
        document_binding_repository: DocumentBindingRepository,
        file_repository: FileRepository,
        rag_client: RagClient,
    ) -> None:
        self._catalog_repository: CatalogRepository = catalog_repository
        self._document_binding_repository: DocumentBindingRepository = document_binding_repository
        self._file_repository: FileRepository = file_repository
        self._rag_client: RagClient = rag_client

    @staticmethod
    def rag_namespace_id(catalog_id: str) -> str:
        normalized = catalog_id.strip()
        if normalized == "":
            raise ValueError("catalog_id обязателен")
        return f"{OFFICE_CATALOG_RAG_NAMESPACE_PREFIX}{normalized}"

    def _require_context(self) -> tuple[str, str, str]:
        context = get_context()
        if context is None:
            raise ValueError("Нет контекста запроса")
        if context.active_company is None:
            raise ValueError("Нет активной компании")
        company_id = context.active_company.company_id
        workspace_namespace = context.active_namespace.strip()
        if workspace_namespace == "":
            raise ValueError("active_namespace обязателен")
        return company_id, workspace_namespace, context.user.user_id

    async def _get_catalog_or_raise(
        self,
        catalog_id: str,
        *,
        company_id: str,
        workspace_namespace: str,
    ) -> OfficeDocumentCatalog:
        catalog = await self._catalog_repository.get(catalog_id, company_id, workspace_namespace)
        if catalog is None:
            raise ValueError("Каталог не найден")
        return catalog

    @staticmethod
    def _binding_metadata(
        *,
        binding: OfficeDocumentBinding,
        catalog: OfficeDocumentCatalog,
        company_id: str,
        workspace_namespace: str,
        user_id: str,
    ) -> RAGMetadata:
        return {
            "source": "office",
            "company_id": company_id,
            "office_namespace": workspace_namespace,
            "catalog_id": catalog.catalog_id,
            "binding_id": binding.binding_id,
            "document_title": binding.title,
            "file_category": binding.file_category,
            "uploaded_by_user_id": user_id,
            "ttl_seconds": 0,
            "external_file_owner": "peer",
        }

    async def enable(self, catalog_id: str) -> OfficeCatalogRagIndexEnableResponse:
        company_id, workspace_namespace, _user_id = self._require_context()
        catalog = await self._get_catalog_or_raise(
            catalog_id,
            company_id=company_id,
            workspace_namespace=workspace_namespace,
        )
        rag_namespace_id = self.rag_namespace_id(catalog.catalog_id)
        if catalog.rag_index_enabled:
            rebuild = await self.rebuild_catalog(catalog.catalog_id)
            return OfficeCatalogRagIndexEnableResponse(
                rag_namespace_id=rag_namespace_id,
                initial_task_id=rebuild.task_id,
            )
        _ = await self._rag_client.create_namespace(
            rag_namespace_id,
            description=catalog.title,
        )
        updated = await self._catalog_repository.set_rag_index_enabled(
            catalog.catalog_id,
            company_id,
            workspace_namespace,
            enabled=True,
        )
        if updated is None:
            raise ValueError("Каталог не найден")
        rebuild = await self.rebuild_catalog(catalog.catalog_id)
        return OfficeCatalogRagIndexEnableResponse(
            rag_namespace_id=rag_namespace_id,
            initial_task_id=rebuild.task_id,
        )

    async def disable(self, catalog_id: str) -> None:
        company_id, workspace_namespace, _user_id = self._require_context()
        catalog = await self._get_catalog_or_raise(
            catalog_id,
            company_id=company_id,
            workspace_namespace=workspace_namespace,
        )
        rag_namespace_id = self.rag_namespace_id(catalog.catalog_id)
        try:
            _ = await self._rag_client.delete_namespace(rag_namespace_id)
        except ServiceClientError as exc:
            if not str(exc).startswith("HTTP 404"):
                raise
        updated = await self._catalog_repository.set_rag_index_enabled(
            catalog.catalog_id,
            company_id,
            workspace_namespace,
            enabled=False,
        )
        if updated is None:
            raise ValueError("Каталог не найден")

    async def index_binding(
        self,
        binding: OfficeDocumentBinding,
        *,
        scope_company_id: str | None = None,
        scope_workspace_namespace: str | None = None,
        scope_user_id: str | None = None,
    ) -> JsonObject | None:
        if (
            scope_company_id is not None
            and scope_workspace_namespace is not None
            and scope_user_id is not None
        ):
            company_id = scope_company_id.strip()
            workspace_namespace = scope_workspace_namespace.strip()
            user_id = scope_user_id.strip()
            if company_id == "":
                raise ValueError("scope_company_id обязателен")
            if workspace_namespace == "":
                raise ValueError("scope_workspace_namespace обязателен")
            if user_id == "":
                raise ValueError("scope_user_id обязателен")
        else:
            company_id, workspace_namespace, user_id = self._require_context()
        catalog = await self._catalog_repository.get(
            binding.catalog_id,
            company_id,
            workspace_namespace,
        )
        if catalog is None:
            raise ValueError("Каталог не найден")
        if not catalog.rag_index_enabled:
            return None

        file_record = await self._file_repository.get(binding.file_id)
        if file_record is None:
            raise ValueError(f"FileRecord не найден: {binding.file_id}")

        metadata = self._binding_metadata(
            binding=binding,
            catalog=catalog,
            company_id=company_id,
            workspace_namespace=workspace_namespace,
            user_id=user_id,
        )
        response = await self._rag_client.index_file(
            self.rag_namespace_id(catalog.catalog_id),
            binding.file_id,
            metadata=metadata,
            document_name=file_record.original_name,
        )
        logger.info(
            "Office catalog RAG index enqueued binding_id=%s file_id=%s catalog_id=%s",
            binding.binding_id,
            binding.file_id,
            catalog.catalog_id,
        )
        return response

    async def unindex_binding(self, catalog_id: str, file_id: str) -> None:
        company_id, workspace_namespace, _user_id = self._require_context()
        catalog = await self._get_catalog_or_raise(
            catalog_id,
            company_id=company_id,
            workspace_namespace=workspace_namespace,
        )
        rag_namespace_id = self.rag_namespace_id(catalog.catalog_id)
        try:
            _ = await self._rag_client.delete_document_index(rag_namespace_id, file_id)
        except ServiceClientError as exc:
            if not str(exc).startswith("HTTP 404"):
                raise

    async def _searchable_catalog_ids_in_scope(
        self,
        catalog: OfficeDocumentCatalog,
        *,
        company_id: str,
        workspace_namespace: str,
    ) -> list[str]:
        return await self._catalog_repository.resolve_rag_search_catalog_ids(
            catalog.catalog_id,
            company_id,
            workspace_namespace,
            include_subcatalogs=catalog.rag_index_include_subcatalogs,
        )

    async def _enqueue_catalog_rebuild(
        self,
        catalog: OfficeDocumentCatalog,
        *,
        company_id: str,
        workspace_namespace: str,
        user_id: str,
    ) -> str:
        bindings = await self._document_binding_repository.list_by_company_namespace_and_catalog(
            company_id,
            workspace_namespace,
            catalog.catalog_id,
        )
        items = [
            OfficeCatalogRagIndexBindingItem(
                file_id=binding.file_id,
                binding_id=binding.binding_id,
                title=binding.title,
                file_category=binding.file_category,
            )
            for binding in bindings
        ]
        rag_namespace_id = self.rag_namespace_id(catalog.catalog_id)
        task = await kiq_task_name_with_context(
            RAG_INDEX_OFFICE_CATALOG_TASK_NAME,
            rag_worker_broker,
            company_id=company_id,
            workspace_namespace=workspace_namespace,
            catalog_id=catalog.catalog_id,
            catalog_title=catalog.title,
            user_id=user_id,
            rag_namespace_id=rag_namespace_id,
            items=[item.model_dump() for item in items],
        )
        return task.task_id

    async def set_include_subcatalogs(
        self,
        catalog_id: str,
        *,
        include_subcatalogs: bool,
    ) -> OfficeCatalogRagIndexSettingsResponse:
        company_id, workspace_namespace, _user_id = self._require_context()
        updated = await self._catalog_repository.set_rag_index_include_subcatalogs(
            catalog_id,
            company_id,
            workspace_namespace,
            include_subcatalogs=include_subcatalogs,
        )
        if updated is None:
            raise ValueError("Каталог не найден")
        return OfficeCatalogRagIndexSettingsResponse(
            include_subcatalogs=updated.rag_index_include_subcatalogs,
        )

    async def rebuild_catalog(self, catalog_id: str) -> OfficeCatalogRagIndexRebuildResponse:
        company_id, workspace_namespace, user_id = self._require_context()
        catalog = await self._get_catalog_or_raise(
            catalog_id,
            company_id=company_id,
            workspace_namespace=workspace_namespace,
        )
        if not catalog.rag_index_enabled:
            raise ValueError("RAG-индекс для каталога не включён")

        searchable_catalog_ids = await self._searchable_catalog_ids_in_scope(
            catalog,
            company_id=company_id,
            workspace_namespace=workspace_namespace,
        )
        if not searchable_catalog_ids:
            raise ValueError("RAG-индекс для каталога не включён")

        last_task_id = ""
        for searchable_catalog_id in searchable_catalog_ids:
            searchable_catalog = await self._get_catalog_or_raise(
                searchable_catalog_id,
                company_id=company_id,
                workspace_namespace=workspace_namespace,
            )
            if not searchable_catalog.rag_index_enabled:
                continue
            last_task_id = await self._enqueue_catalog_rebuild(
                searchable_catalog,
                company_id=company_id,
                workspace_namespace=workspace_namespace,
                user_id=user_id,
            )
            _ = await self._catalog_repository.set_rag_index_enabled(
                searchable_catalog.catalog_id,
                company_id,
                workspace_namespace,
                enabled=True,
            )
        if last_task_id == "":
            raise ValueError("RAG-индекс для каталога не включён")
        return OfficeCatalogRagIndexRebuildResponse(task_id=last_task_id)

    async def get_status(self, catalog_id: str) -> OfficeCatalogRagIndexStatusResponse:
        company_id, workspace_namespace, _user_id = self._require_context()
        catalog = await self._get_catalog_or_raise(
            catalog_id,
            company_id=company_id,
            workspace_namespace=workspace_namespace,
        )
        rag_namespace_id = self.rag_namespace_id(catalog.catalog_id)
        searchable_catalog_ids = await self._searchable_catalog_ids_in_scope(
            catalog,
            company_id=company_id,
            workspace_namespace=workspace_namespace,
        )

        totals = OfficeCatalogRagIndexStatusTotals()
        for searchable_catalog_id in searchable_catalog_ids:
            bindings = await self._document_binding_repository.list_by_company_namespace_and_catalog(
                company_id,
                workspace_namespace,
                searchable_catalog_id,
            )
            for binding in bindings:
                bucket = await self._status_bucket_for_file(binding.file_id)
                if bucket == "ready":
                    totals.ready += 1
                elif bucket == "pending":
                    totals.pending += 1
                elif bucket == "failed":
                    totals.failed += 1
                else:
                    totals.absent += 1

        return OfficeCatalogRagIndexStatusResponse(
            enabled=catalog.rag_index_enabled,
            rag_namespace_id=rag_namespace_id,
            include_subcatalogs=catalog.rag_index_include_subcatalogs,
            totals=totals,
            rag_index_updated_at=catalog.rag_index_updated_at,
        )

    async def _status_bucket_for_file(
        self,
        file_id: str,
    ) -> Literal["ready", "pending", "failed", "absent"]:
        try:
            status_payload = await self._rag_client.get_document_processing_status(file_id)
        except ServiceClientError as exc:
            if str(exc).startswith("HTTP 404"):
                return "absent"
            raise
        status_value = status_payload.get("status")
        if not isinstance(status_value, str):
            raise ValueError("RAG status response.status must be a string")
        if status_value in ("pending", "processing"):
            return "pending"
        if status_value == "failed":
            return "failed"
        if status_value == "completed":
            return "ready"
        raise ValueError(f"Неизвестный статус индексации RAG: {status_value}")

    @staticmethod
    def _catalog_id_from_search_hit(hit: RAGSearchResult) -> str | None:
        metadata_catalog_id = hit.metadata.get("catalog_id")
        if isinstance(metadata_catalog_id, str) and metadata_catalog_id.strip() != "":
            return metadata_catalog_id.strip()
        namespace_id = hit.namespace.strip()
        if namespace_id.startswith(OFFICE_CATALOG_RAG_NAMESPACE_PREFIX):
            catalog_id = namespace_id[len(OFFICE_CATALOG_RAG_NAMESPACE_PREFIX):]
            if catalog_id != "":
                return catalog_id
        return None

    @staticmethod
    def _parse_search_results(raw_results: JsonValue) -> list[RAGSearchResult]:
        if not isinstance(raw_results, list):
            raise ValueError("RAG search response.results must be a list")
        parsed: list[RAGSearchResult] = []
        for item in raw_results:
            if not isinstance(item, dict):
                raise ValueError("RAG search result item must be an object")
            parsed.append(RAGSearchResult.model_validate(item))
        return parsed

    @staticmethod
    def _dedupe_search_hits(hits: list[RAGSearchResult]) -> list[RAGSearchResult]:
        best_by_file_id: dict[str, RAGSearchResult] = {}
        for hit in hits:
            existing = best_by_file_id.get(hit.document_id)
            if existing is None or hit.score > existing.score:
                best_by_file_id[hit.document_id] = hit
        deduped = list(best_by_file_id.values())
        deduped.sort(key=lambda item: item.score, reverse=True)
        return deduped

    async def search_catalog(
        self,
        catalog_id: str,
        query: str,
        *,
        limit: int = 20,
    ) -> OfficeCatalogSemanticSearchResponse:
        company_id, workspace_namespace, _user_id = self._require_context()
        catalog = await self._get_catalog_or_raise(
            catalog_id,
            company_id=company_id,
            workspace_namespace=workspace_namespace,
        )
        normalized_query = query.strip()
        if normalized_query == "":
            raise ValueError("query обязателен")

        searchable_catalog_ids = await self._searchable_catalog_ids_in_scope(
            catalog,
            company_id=company_id,
            workspace_namespace=workspace_namespace,
        )
        if not searchable_catalog_ids:
            raise ValueError("Нет проиндексированных каталогов для поиска")

        namespace_ids = [self.rag_namespace_id(searchable_id) for searchable_id in searchable_catalog_ids]
        if len(namespace_ids) == 1:
            search_payload = require_json_object(
                await self._rag_client.search(namespace_ids[0], normalized_query, limit=limit),
                "Office catalog RAG search response",
            )
            hits = self._parse_search_results(search_payload["results"])
        else:
            global_payload = require_json_object(
                await self._rag_client.global_search(namespace_ids, normalized_query, limit=limit),
                "Office catalog RAG global search response",
            )
            raw_results_by_namespace = global_payload["results"]
            if not isinstance(raw_results_by_namespace, dict):
                raise ValueError("RAG global search response.results must be an object")
            hits: list[RAGSearchResult] = []
            for namespace_results in raw_results_by_namespace.values():
                hits.extend(self._parse_search_results(namespace_results))

        deduped_hits = self._dedupe_search_hits(hits)[:limit]

        bindings = await self._document_binding_repository.list_by_company_namespace_and_catalogs(
            company_id,
            workspace_namespace,
            searchable_catalog_ids,
        )
        binding_by_file_and_catalog: dict[tuple[str, str], OfficeDocumentBinding] = {}
        for binding in bindings:
            binding_by_file_and_catalog[(binding.file_id, binding.catalog_id)] = binding

        catalog_titles: dict[str, str] = {}
        for searchable_id in searchable_catalog_ids:
            searchable_catalog = await self._get_catalog_or_raise(
                searchable_id,
                company_id=company_id,
                workspace_namespace=workspace_namespace,
            )
            catalog_titles[searchable_catalog.catalog_id] = searchable_catalog.title

        items: list[OfficeCatalogSemanticSearchHit] = []
        for hit in deduped_hits:
            hit_catalog_id = self._catalog_id_from_search_hit(hit)
            if hit_catalog_id is None:
                continue
            binding = binding_by_file_and_catalog.get((hit.document_id, hit_catalog_id))
            if binding is None:
                continue
            catalog_title = catalog_titles.get(hit_catalog_id)
            if catalog_title is None:
                continue
            items.append(
                OfficeCatalogSemanticSearchHit(
                    binding_id=binding.binding_id,
                    file_id=hit.document_id,
                    catalog_id=hit_catalog_id,
                    catalog_title=catalog_title,
                    title=binding.title,
                    snippet=hit.content,
                    score=hit.score,
                )
            )

        return OfficeCatalogSemanticSearchResponse(
            query=normalized_query,
            include_subcatalogs=catalog.rag_index_include_subcatalogs,
            catalog_ids=searchable_catalog_ids,
            items=items,
        )
