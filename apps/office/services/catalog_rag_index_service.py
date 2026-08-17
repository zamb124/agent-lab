"""Индексация документов Office-каталога в RAG (отдельный namespace на catalog_id)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from apps.office.db.models import OfficeDocumentBinding, OfficeDocumentCatalog
from apps.office.models.api import (
    OfficeCatalogRagIndexBindingItem,
    OfficeCatalogRagIndexEnableResponse,
    OfficeCatalogRagIndexRebuildResponse,
    OfficeCatalogRagIndexSettingsPatchRequest,
    OfficeCatalogRagIndexSettingsResponse,
    OfficeCatalogRagIndexStatusResponse,
    OfficeCatalogRagIndexStatusTotals,
    OfficeCatalogSemanticSearchHit,
    OfficeCatalogSemanticSearchRequest,
    OfficeCatalogSemanticSearchResponse,
)
from apps.rag_worker.tasks.task_names import RAG_INDEX_OFFICE_CATALOG
from core.clients.rag_client import RagClient
from core.clients.service_client import ServiceClientError
from core.config import get_settings
from core.context import get_context
from core.logging import get_logger
from core.rag.indexable import effective_rag_file_category, is_rag_indexable_file_category
from core.rag.models import RAGMetadata, RAGSearchOptions, RAGSearchResult
from core.rag.rag_http_namespace_search import (
    filter_search_request_options,
    merge_search_request_options,
)
from core.rag.search_options_resolver import resolve_platform_search_options
from core.tasks import enqueue
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
            "file_id": binding.file_id,
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

        resolved_category = effective_rag_file_category(
            file_category=binding.file_category,
            document_name=file_record.original_name,
        )
        if not is_rag_indexable_file_category(resolved_category):
            logger.info(
                (
                    "Office catalog RAG index skip non-indexable file_id=%s "
                    "catalog_id=%s file_category=%s document_name=%s"
                ),
                binding.file_id,
                catalog.catalog_id,
                resolved_category,
                file_record.original_name,
            )
            return None

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
            "Office catalog RAG index enqueued file_id=%s catalog_id=%s",
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
        if not catalog.rag_index_enabled:
            return
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
                title=binding.title,
                file_category=binding.file_category,
            )
            for binding in bindings
        ]
        rag_namespace_id = self.rag_namespace_id(catalog.catalog_id)
        task = await enqueue(
            RAG_INDEX_OFFICE_CATALOG,
            company_id=company_id,
            workspace_namespace=workspace_namespace,
            catalog_id=catalog.catalog_id,
            catalog_title=catalog.title,
            user_id=user_id,
            rag_namespace_id=rag_namespace_id,
            items=[item.model_dump() for item in items],
        )
        return task.task_id

    async def patch_rag_index_settings(
        self,
        catalog_id: str,
        request: OfficeCatalogRagIndexSettingsPatchRequest,
    ) -> OfficeCatalogRagIndexSettingsResponse:
        company_id, workspace_namespace, _user_id = self._require_context()
        call_opts = filter_search_request_options(request)
        update_search_options = request.clear_search_options is True or call_opts is not None
        search_options_json: JsonObject | None = None
        if request.clear_search_options is True:
            search_options_json = None
        elif call_opts is not None:
            search_options_json = call_opts.model_dump(exclude_none=True)
            if search_options_json == {}:
                search_options_json = None
        updated = await self._catalog_repository.patch_rag_index_settings(
            catalog_id,
            company_id,
            workspace_namespace,
            include_subcatalogs=request.include_subcatalogs,
            search_options=search_options_json,
            update_search_options=update_search_options,
        )
        if updated is None:
            raise ValueError("Каталог не найден")
        return OfficeCatalogRagIndexSettingsResponse(
            include_subcatalogs=updated.rag_index_include_subcatalogs,
            search_options=self.catalog_search_options_model(updated),
        )

    async def set_include_subcatalogs(
        self,
        catalog_id: str,
        *,
        include_subcatalogs: bool,
    ) -> OfficeCatalogRagIndexSettingsResponse:
        return await self.patch_rag_index_settings(
            catalog_id,
            OfficeCatalogRagIndexSettingsPatchRequest(include_subcatalogs=include_subcatalogs),
        )

    @staticmethod
    def catalog_search_options_model(
        catalog: OfficeDocumentCatalog,
    ) -> RAGSearchOptions | None:
        raw = catalog.rag_index_search_options
        if raw is None:
            return None
        return filter_search_request_options(raw)

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

        indexable_file_ids: list[str] = []
        non_indexable_count = 0
        for searchable_catalog_id in searchable_catalog_ids:
            bindings = await self._document_binding_repository.list_by_company_namespace_and_catalog(
                company_id,
                workspace_namespace,
                searchable_catalog_id,
            )
            for binding in bindings:
                file_record = await self._file_repository.get(binding.file_id)
                document_name = (
                    file_record.original_name if file_record is not None else binding.title
                )
                if not is_rag_indexable_file_category(
                    effective_rag_file_category(
                        file_category=binding.file_category,
                        document_name=document_name,
                    )
                ):
                    # Подписи/архивы/unknown не в индексе; старые failed-статусы в UI не считаем.
                    non_indexable_count += 1
                    continue
                indexable_file_ids.append(binding.file_id)

        buckets = await self.batch_status_buckets(indexable_file_ids)
        totals = OfficeCatalogRagIndexStatusTotals(absent=non_indexable_count)
        for file_id in indexable_file_ids:
            bucket = buckets[file_id]
            if bucket == "ready":
                totals.ready += 1
            elif bucket == "failed":
                totals.failed += 1
            else:
                # pending / processing / no status row yet (queued after enable)
                totals.pending += 1

        return OfficeCatalogRagIndexStatusResponse(
            enabled=catalog.rag_index_enabled,
            rag_namespace_id=rag_namespace_id,
            include_subcatalogs=catalog.rag_index_include_subcatalogs,
            search_options=self.catalog_search_options_model(catalog),
            platform_defaults=resolve_platform_search_options(settings=get_settings()),
            totals=totals,
            rag_index_updated_at=catalog.rag_index_updated_at,
        )

    async def batch_status_buckets(
        self,
        file_ids: list[str],
    ) -> dict[str, Literal["ready", "pending", "failed", "absent"]]:
        """Один batch-запрос к RAG на список file_id → bucket статуса индексации."""
        if not file_ids:
            return {}
        unique_ids = list(dict.fromkeys(file_ids))
        result: dict[str, Literal["ready", "pending", "failed", "absent"]] = {}
        chunk_size = 500
        for offset in range(0, len(unique_ids), chunk_size):
            chunk = unique_ids[offset : offset + chunk_size]
            statuses = await self._rag_client.get_documents_processing_statuses(chunk)
            for file_id in chunk:
                result[file_id] = self._bucket_from_status_payload(statuses.get(file_id))
        return result

    @staticmethod
    def _bucket_from_status_payload(
        status_payload: JsonObject | None,
    ) -> Literal["ready", "pending", "failed", "absent"]:
        if status_payload is None:
            return "absent"
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

    async def _status_bucket_for_file(
        self,
        file_id: str,
    ) -> Literal["ready", "pending", "failed", "absent"]:
        buckets = await self.batch_status_buckets([file_id])
        return buckets[file_id]

    @staticmethod
    def _catalog_id_from_search_hit(hit: RAGSearchResult) -> str | None:
        metadata_catalog_id = hit.attributes.get("catalog_id")
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
        request: OfficeCatalogSemanticSearchRequest,
    ) -> OfficeCatalogSemanticSearchResponse:
        company_id, workspace_namespace, _user_id = self._require_context()
        catalog = await self._get_catalog_or_raise(
            catalog_id,
            company_id=company_id,
            workspace_namespace=workspace_namespace,
        )
        normalized_query = request.query.strip()
        if normalized_query == "":
            raise ValueError("query обязателен")
        limit = request.limit

        searchable_catalog_ids = await self._searchable_catalog_ids_in_scope(
            catalog,
            company_id=company_id,
            workspace_namespace=workspace_namespace,
        )
        if not searchable_catalog_ids:
            raise ValueError("Нет проиндексированных каталогов для поиска")

        namespace_ids = [self.rag_namespace_id(searchable_id) for searchable_id in searchable_catalog_ids]
        settings = get_settings()
        catalog_overrides = self.catalog_search_options_model(catalog)
        request_overrides = filter_search_request_options(request)
        merged_overrides = merge_search_request_options(catalog_overrides, request_overrides)
        resolved_search_options = resolve_platform_search_options(
            settings=settings,
            per_channel_top_k=max(limit * 3, limit),
            overrides=merged_overrides,
        )
        if len(namespace_ids) == 1:
            search_payload = require_json_object(
                await self._rag_client.search(
                    namespace_ids[0],
                    normalized_query,
                    limit=limit,
                    channels=resolved_search_options.channels,
                    rrf_k=resolved_search_options.rrf_k,
                    per_channel_top_k=resolved_search_options.per_channel_top_k,
                    rerank=resolved_search_options.rerank,
                    rerank_max_candidates=resolved_search_options.rerank_max_candidates,
                    retrieval=resolved_search_options.retrieval,
                    freshness_weight=resolved_search_options.freshness_weight,
                    freshness_half_life_days=resolved_search_options.freshness_half_life_days,
                ),
                "Office catalog RAG search response",
            )
            hits = self._parse_search_results(search_payload["results"])
        else:
            global_payload = require_json_object(
                await self._rag_client.global_search(
                    namespace_ids,
                    normalized_query,
                    limit=limit,
                    channels=resolved_search_options.channels,
                    rrf_k=resolved_search_options.rrf_k,
                    per_channel_top_k=resolved_search_options.per_channel_top_k,
                    rerank=resolved_search_options.rerank,
                    rerank_max_candidates=resolved_search_options.rerank_max_candidates,
                    retrieval=resolved_search_options.retrieval,
                    freshness_weight=resolved_search_options.freshness_weight,
                    freshness_half_life_days=resolved_search_options.freshness_half_life_days,
                ),
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
