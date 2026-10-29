"""Индексация документов Office-каталога в RAG (отдельный namespace на catalog_id)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from apps.office.models.api import (
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
from apps.office.services.file_binding_metadata import resolve_binding_metadata
from core.clients.rag_client import RagClient
from core.clients.service_client import ServiceClientError
from core.config import get_settings
from core.context import get_context
from core.documents.catalog import DocumentCatalog
from core.files.models import FileRecord
from core.logging import get_logger
from core.rag.indexable import effective_rag_file_category, is_rag_indexable_file_category
from core.rag.models import RAGMetadata, RAGSearchOptions, RAGSearchResult
from core.rag.rag_http_namespace_search import (
    filter_search_request_options,
    merge_search_request_options,
)
from core.rag.search_options_resolver import resolve_platform_search_options
from core.types import JsonObject, JsonValue, require_json_object

logger = get_logger(__name__)

OFFICE_CATALOG_RAG_NAMESPACE_PREFIX = "office-catalog-"


class OfficeCatalogRagIndexService:
    def __init__(
        self,
        rag_client: RagClient,
    ) -> None:
        self._rag_client: RagClient = rag_client

    @staticmethod
    def rag_namespace_id(catalog_id: str) -> str:
        normalized = catalog_id.strip()
        if normalized == "":
            raise ValueError("catalog_id is required")
        return f"{OFFICE_CATALOG_RAG_NAMESPACE_PREFIX}{normalized}"

    def _require_context(self) -> tuple[str, str, str]:
        context = get_context()
        if context is None:
            raise ValueError("Request context is missing")
        if context.active_company is None:
            raise ValueError("No active company")
        company_id = context.active_company.company_id
        workspace_namespace = context.active_namespace.strip()
        if workspace_namespace == "":
            raise ValueError("active_namespace is required")
        return company_id, workspace_namespace, context.user.user_id

    async def _get_catalog_or_raise(
        self,
        catalog_id: str,
        *,
        company_id: str,
        workspace_namespace: str,
    ) -> DocumentCatalog:
        catalog = await DocumentCatalog.catalog_in_namespace(
            catalog_id,
            company_id,
            workspace_namespace,
        )
        if catalog is None:
            raise ValueError("Catalog not found")
        return catalog

    @staticmethod
    def _binding_metadata(
        *,
        binding: FileRecord,
        catalog: DocumentCatalog,
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
            "document_title": binding.original_name,
            "file_category": resolve_binding_metadata(
                binding.original_name,
                binding.content_type.split(";", 1)[0].strip(),
            )[0],
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
        catalog.rag_index_enabled = True
        catalog.rag_index_updated_at = datetime.now(timezone.utc)
        _ = await catalog.save()
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
        catalog.rag_index_enabled = False
        catalog.rag_index_updated_at = datetime.now(timezone.utc)
        _ = await catalog.save()

    async def index_binding(
        self,
        binding: FileRecord,
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
                raise ValueError("scope_company_id is required")
            if workspace_namespace == "":
                raise ValueError("scope_workspace_namespace is required")
            if user_id == "":
                raise ValueError("scope_user_id is required")
        else:
            company_id, workspace_namespace, user_id = self._require_context()
        catalog_id = binding.catalog_id
        if catalog_id is None:
            raise ValueError("file has no catalog")
        catalog = await DocumentCatalog.catalog_in_namespace(
            catalog_id,
            company_id,
            workspace_namespace,
        )
        if catalog is None:
            raise ValueError("Catalog not found")
        if not catalog.rag_index_enabled:
            return None

        file_record = await FileRecord.get(binding.file_id)
        if file_record is None:
            raise ValueError(f"FileRecord not found: {binding.file_id}")

        resolved_category = effective_rag_file_category(
            file_category=resolve_binding_metadata(
                binding.original_name,
                binding.content_type.split(";", 1)[0].strip(),
            )[0],
            document_name=file_record.original_name,
        )
        if not is_rag_indexable_file_category(resolved_category):
            logger.info(
                "office.catalog.rag.index.skip",
                file_id=binding.file_id,
                catalog_id=catalog.catalog_id,
                file_category=resolved_category,
                document_name=file_record.original_name,
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
        logger.info("office.catalog.rag.index.enqueued", file_id=binding.file_id, catalog_id=catalog.catalog_id)
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
        catalog: DocumentCatalog,
        *,
        company_id: str,
        workspace_namespace: str,
    ) -> list[str]:
        catalog_ids: list[str] = []
        seen: set[str] = set()
        if catalog.rag_index_enabled:
            catalog_ids.append(catalog.catalog_id)
            seen.add(catalog.catalog_id)
        if not catalog.rag_index_include_subcatalogs:
            return catalog_ids
        queue = [catalog.catalog_id]
        while queue:
            current_id = queue.pop(0)
            children = await DocumentCatalog.list_children_by_title_key_asc(
                company_id=company_id,
                namespace=workspace_namespace,
                parent_catalog_id=current_id,
            )
            for child in children:
                if child.catalog_id in seen:
                    continue
                seen.add(child.catalog_id)
                queue.append(child.catalog_id)
                if child.rag_index_enabled:
                    catalog_ids.append(child.catalog_id)
        return catalog_ids

    async def _reindex_catalog_bindings(
        self,
        catalog: DocumentCatalog,
        *,
        company_id: str,
        workspace_namespace: str,
        user_id: str,
    ) -> tuple[str | None, int]:
        """Ставит каждый документ каталога в очередь RAG через владельца индекса.

        Возвращает task_id последнего поставленного документа и число поставленных.
        """
        bindings = await FileRecord.list_alive_in_catalog_by_updated_at_desc(
            company_id=company_id,
            catalog_id=catalog.catalog_id,
        )
        last_task_id: str | None = None
        enqueued = 0
        for binding in bindings:
            response = await self.index_binding(
                binding,
                scope_company_id=company_id,
                scope_workspace_namespace=workspace_namespace,
                scope_user_id=user_id,
            )
            if response is None:
                continue
            task_id = response.get("task_id")
            if not isinstance(task_id, str) or task_id.strip() == "":
                raise ValueError(f"RAG index_file without task_id for file_id={binding.file_id}")
            last_task_id = task_id
            enqueued += 1
        return last_task_id, enqueued

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
        updated = await self._get_catalog_or_raise(
            catalog_id,
            company_id=company_id,
            workspace_namespace=workspace_namespace,
        )
        if request.include_subcatalogs is not None:
            updated.rag_index_include_subcatalogs = request.include_subcatalogs
        if update_search_options:
            updated.rag_index_search_options = search_options_json
        _ = await updated.save()
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
        catalog: DocumentCatalog,
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
            raise ValueError("RAG index is not enabled for the catalog")

        searchable_catalog_ids = await self._searchable_catalog_ids_in_scope(
            catalog,
            company_id=company_id,
            workspace_namespace=workspace_namespace,
        )
        if not searchable_catalog_ids:
            raise ValueError("RAG index is not enabled for the catalog")

        last_task_id: str | None = None
        enqueued_total = 0
        for searchable_catalog_id in searchable_catalog_ids:
            searchable_catalog = await self._get_catalog_or_raise(
                searchable_catalog_id,
                company_id=company_id,
                workspace_namespace=workspace_namespace,
            )
            if not searchable_catalog.rag_index_enabled:
                continue
            task_id, enqueued = await self._reindex_catalog_bindings(
                searchable_catalog,
                company_id=company_id,
                workspace_namespace=workspace_namespace,
                user_id=user_id,
            )
            if task_id is not None:
                last_task_id = task_id
            enqueued_total += enqueued
            searchable_catalog.rag_index_enabled = True
            searchable_catalog.rag_index_updated_at = datetime.now(timezone.utc)
            _ = await searchable_catalog.save()
        return OfficeCatalogRagIndexRebuildResponse(
            task_id=last_task_id, enqueued_documents=enqueued_total
        )

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
            bindings = await FileRecord.list_alive_in_catalog_by_updated_at_desc(
                company_id=company_id,
                catalog_id=searchable_catalog_id,
            )
            for binding in bindings:
                document_name = binding.original_name
                file_category = resolve_binding_metadata(
                    binding.original_name,
                    binding.content_type.split(";", 1)[0].strip(),
                )[0]
                if not is_rag_indexable_file_category(
                    effective_rag_file_category(
                        file_category=file_category,
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
        raise ValueError(f"Unknown RAG indexing status: {status_value}")

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
            raise ValueError("query is required")
        limit = request.limit

        searchable_catalog_ids = await self._searchable_catalog_ids_in_scope(
            catalog,
            company_id=company_id,
            workspace_namespace=workspace_namespace,
        )
        if not searchable_catalog_ids:
            raise ValueError("No indexed catalogs to search")

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

        bindings: list[FileRecord] = []
        for searchable_catalog_id in searchable_catalog_ids:
            bindings.extend(
                await FileRecord.list_alive_in_catalog_by_updated_at_desc(
                    company_id=company_id,
                    catalog_id=searchable_catalog_id,
                )
            )
        binding_by_file_and_catalog: dict[tuple[str, str], FileRecord] = {}
        for binding in bindings:
            placed_catalog_id = binding.catalog_id
            if placed_catalog_id is None:
                continue
            binding_by_file_and_catalog[(binding.file_id, placed_catalog_id)] = binding

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
                    title=binding.original_name,
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
