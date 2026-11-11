"""Бизнес-функции RAG: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

from pydantic import Field

import core.tracing.attributes as trace_attributes
from apps.rag.config import get_rag_settings
from apps.rag.di import Di
from apps.rag.models import (
    DocumentStatusesBatchRequest,
    DocumentStatusesBatchResponse,
    GlobalSearchResponse,
    IndexFileRequest,
    IndexFileResponse,
    IngestTextRequest,
    NamespaceCreateRequest,
    NamespaceDeleteResponse,
    ProviderInfo,
    ProvidersView,
    RagDocumentDeleteResult,
    SearchResponse,
)
from apps.rag.namespace_access import (
    require_registered_rag_namespace,
    validate_ingest_text_body,
    validate_rag_user_metadata,
)
from apps.rag.tasks.task_names import RAG_INDEX_DOCUMENT_S3
from core.ai.rerank_client import AIRerankerClientError
from core.authz.models import AuthzObject
from core.billing.service import BillingService
from core.context import require_active_company, require_context
from core.db.models.rag import DocumentProcessingStatus
from core.errors.boundary import PlatformAccessDeniedError, PlatformNotFoundError
from core.files.models import FileRecord
from core.logging import get_logger
from core.models import StrictBaseModel
from core.models.identity_models import Namespace, User
from core.pagination import OffsetPage
from core.rag.base_provider import BaseRAGProvider, validate_metadata_filters
from core.rag.factory import get_rag_provider
from core.rag.models import (
    RAGDocument,
    RAGDocumentContent,
    RAGGlobalSearchRequest,
    RAGIngestTextResponse,
    RAGMetadata,
    RAGNamespaceSearchRequest,
    RAGSearchOptions,
)
from core.rag.post_retrieval_rerank import (
    apply_rerank_after_retrieve_by_score_desc,
    apply_rerank_after_retrieve_grouped_by_score_desc,
)
from core.rag.rag_http_namespace_search import filter_search_request_options
from core.rag.search_options_resolver import resolve_platform_search_options
from core.rag.ttl import ensure_ttl_seconds_in_metadata
from core.tasks import enqueue
from core.tracing.operation_span import traced_operation
from core.websocket import (
    EmptyPayload,
    WsCommandError,
    raise_forbidden,
    raise_invalid,
    raise_not_found,
)

logger = get_logger(__name__)


class RagNamespaceCreatePayload(NamespaceCreateRequest):
    provider: str | None = None


class RagNamespaceDeletePayload(StrictBaseModel):
    name: str = Field(min_length=1)
    provider: str | None = None


class RagDocumentsListPayload(StrictBaseModel):
    namespace_id: str = Field(min_length=1)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=1000)
    provider: str | None = None


class RagIngestTextPayload(IngestTextRequest):
    namespace_id: str = Field(min_length=1)
    provider: str | None = None


class RagIndexFilePayload(IndexFileRequest):
    namespace_id: str = Field(min_length=1)
    provider: str | None = None


class RagDocumentRefPayload(StrictBaseModel):
    namespace_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    provider: str | None = None


class RagDocumentStatusPayload(StrictBaseModel):
    document_id: str = Field(min_length=1)


class RagNamespaceSearchPayload(RAGNamespaceSearchRequest):
    namespace_id: str = Field(min_length=1)
    provider: str | None = None


class RagGlobalSearchPayload(RAGGlobalSearchRequest):
    provider: str | None = None





def _resolve_provider(
    provider: str | None, *, billing_service: BillingService
) -> tuple[BaseRAGProvider, str]:
    settings = get_rag_settings()
    rag_provider = (
        get_rag_provider(provider, settings=settings, billing_service=billing_service)
        if provider
        else get_rag_provider(settings=settings, billing_service=billing_service)
    )
    provider_name = provider if provider is not None else settings.rag.default_provider
    return rag_provider, provider_name


async def _company_view(di: Di) -> str:
    company_id = require_active_company().company_id
    await di.authz_service.require_can_view(AuthzObject.company(company_id))
    return company_id


async def _company_admin(di: Di) -> str:
    company_id = require_active_company().company_id
    await di.authz_service.require_company_admin(company_id=company_id)
    return company_id


async def _namespace(di: Di, namespace_id: str) -> None:
    try:
        await require_registered_rag_namespace(
            namespace_id,
            authz_service=di.authz_service,
            namespace_service=di.namespace_service,
        )
    except PlatformAccessDeniedError as exc:
        raise_forbidden(exc)
    except PlatformNotFoundError as exc:
        raise_not_found(exc, str(exc))


async def op_namespaces_create(
    payload: RagNamespaceCreatePayload,
    *,
    user: User,
    di: Di,
) -> Namespace:
    _ = user
    company_id = await _company_admin(di)
    rag_provider, _provider_name = _resolve_provider(payload.provider, billing_service=di.billing_service)
    try:
        _ = await rag_provider.create_namespace(
            name=payload.name, description=payload.description
        )
        namespace = await di.namespace_service.get_or_create(
            payload.name, description=payload.description
        )
    except ValueError as exc:
        raise_invalid(exc)
    logger.info("rag.namespace", name=payload.name, company_id=company_id)
    return namespace


async def op_namespaces_remove(
    payload: RagNamespaceDeletePayload,
    *,
    user: User,
    di: Di,
) -> NamespaceDeleteResponse:
    _ = user
    company_id = await _company_admin(di)
    rag_provider, _provider_name = _resolve_provider(payload.provider, billing_service=di.billing_service)
    provider_deleted = await rag_provider.delete_namespace(payload.name)
    ns_from_repo = await di.namespace_service.get(payload.name)
    if not provider_deleted and ns_from_repo is None:
        raise WsCommandError("not_found", "Namespace not found", error_code='not_found')
    _ = await di.namespace_service.delete(payload.name)
    logger.info("rag.namespace", name=payload.name, company_id=company_id)
    return NamespaceDeleteResponse(success=True, name=payload.name)


async def op_documents_list(
    payload: RagDocumentsListPayload,
    *,
    user: User,
    di: Di,
) -> OffsetPage[RAGDocument]:
    _ = user
    await _namespace(di, payload.namespace_id)
    rag_provider, _provider_name = _resolve_provider(payload.provider, billing_service=di.billing_service)
    completed_docs = await rag_provider.list_documents(payload.namespace_id, limit=payload.limit)
    processing_statuses = await DocumentProcessingStatus.list_for_namespace_by_updated_at_desc(
        payload.namespace_id, status=["pending", "processing", "failed"], limit=payload.limit
    )
    all_documents = list(completed_docs)
    for status in processing_statuses:
        all_documents.append(
            RAGDocument(
                document_id=status.document_id,
                name=status.document_name,
                namespace=status.namespace_id,
                status=status.status,
                created_at=status.created_at.isoformat(),
                metadata={
                    "file_size": status.file_size,
                    "error_message": status.error_message,
                    "task_id": status.task_id,
                    "created_at": status.created_at.isoformat(),
                    "updated_at": status.updated_at.isoformat(),
                },
            )
        )
    items = all_documents[: payload.limit]
    return OffsetPage[RAGDocument](
        items=items, total=len(items), limit=payload.limit, offset=payload.offset
    )


async def op_documents_ingest_text(
    payload: RagIngestTextPayload,
    *,
    user: User,
    di: Di,
) -> RAGIngestTextResponse:
    _ = user
    await _namespace(di, payload.namespace_id)
    try:
        validate_rag_user_metadata(payload.metadata)
        text = validate_ingest_text_body(payload.text)
    except ValueError as exc:
        raise_invalid(exc)
    context = require_context()
    company_id = require_active_company().company_id
    merged_meta: RAGMetadata = dict(payload.metadata)
    merged_meta["company_id"] = company_id
    merged_meta["uploaded_by_user_id"] = context.user.user_id
    if payload.document_id:
        merged_meta["document_id"] = payload.document_id
    settings = get_rag_settings()
    try:
        merged_meta = ensure_ttl_seconds_in_metadata(
            merged_meta, default_ttl_seconds=settings.rag.ttl.default_ttl_seconds
        )
    except ValueError as exc:
        raise_invalid(exc)
    rag_provider, provider_name = _resolve_provider(payload.provider, billing_service=di.billing_service)
    doc = await rag_provider.upload_document_from_text(
        namespace_id=payload.namespace_id,
        text=text,
        document_name=payload.document_name,
        metadata=merged_meta,
    )
    return RAGIngestTextResponse(
        document_id=doc.document_id,
        document_name=doc.name,
        namespace_id=payload.namespace_id,
        status=doc.status,
        provider=provider_name,
    )


async def _enqueue_s3_indexing_task(
    *,
    namespace_id: str,
    document_id: str,
    s3_key: str,
    document_name: str,
    file_size: int,
    metadata_dict: RAGMetadata,
    provider: str | None,
) -> tuple[str, str]:
    settings = get_rag_settings()
    try:
        metadata_dict = ensure_ttl_seconds_in_metadata(
            metadata_dict, default_ttl_seconds=settings.rag.ttl.default_ttl_seconds
        )
    except ValueError as exc:
        raise_invalid(exc)
    ttl_raw = metadata_dict["ttl_seconds"]
    if not isinstance(ttl_raw, int) or isinstance(ttl_raw, bool):
        raise RuntimeError("ensure_ttl_seconds_in_metadata returned non-integer ttl_seconds")
    task_id_placeholder = f"pending_{document_id}"
    _ = await DocumentProcessingStatus.upsert_pending(
        document_id=document_id,
        task_id=task_id_placeholder,
        namespace_id=namespace_id,
        document_name=document_name,
        file_size=file_size,
        ttl_seconds=ttl_raw,
        extra_metadata={},
    )
    company_id = require_active_company().company_id
    task = await enqueue(
        RAG_INDEX_DOCUMENT_S3,
        company_id=company_id,
        namespace_id=namespace_id,
        s3_key=s3_key,
        document_name=document_name,
        metadata=dict(metadata_dict),
        provider=provider,
    )
    _ = await DocumentProcessingStatus.update_task_id(document_id, task.task_id)
    return document_id, task.task_id


async def op_documents_index_file(
    payload: RagIndexFilePayload,
    *,
    user: User,
    di: Di,
) -> IndexFileResponse:
    _ = user
    await _namespace(di, payload.namespace_id)
    try:
        validate_rag_user_metadata(payload.metadata)
    except ValueError as exc:
        raise_invalid(exc)
    file_id = payload.file_id.strip()
    if file_id == "":
        raise WsCommandError("ws_invalid_payload", "file_id is required", error_code='ws_invalid_payload')
    context = require_context()
    company_id = require_active_company().company_id
    file_record = await FileRecord.get(file_id)
    if file_record is None:
        raise WsCommandError("not_found", "File not found", error_code='not_found')
    if file_record.company_id != company_id:
        raise WsCommandError("forbidden", "File does not belong to the company", error_code='forbidden')
    if payload.document_name is None or payload.document_name == "":
        document_name = file_record.original_name
    else:
        document_name = payload.document_name
    metadata_dict: RAGMetadata = dict(payload.metadata)
    metadata_dict["document_id"] = file_id
    metadata_dict["storage_id"] = file_record.storage_id
    metadata_dict["company_id"] = company_id
    metadata_dict["uploaded_by_user_id"] = context.user.user_id
    metadata_dict["external_file_owner"] = "peer"
    document_id, task_id = await _enqueue_s3_indexing_task(
        namespace_id=payload.namespace_id,
        document_id=file_id,
        s3_key=file_record.s3_key,
        document_name=document_name,
        file_size=file_record.file_size,
        metadata_dict=metadata_dict,
        provider=payload.provider,
    )
    return IndexFileResponse(
        document_id=document_id,
        task_id=task_id,
        status="pending",
        file_id=file_id,
    )


async def op_documents_remove(
    payload: RagDocumentRefPayload,
    *,
    user: User,
    di: Di,
) -> RagDocumentDeleteResult:
    _ = user
    await _namespace(di, payload.namespace_id)
    status = await DocumentProcessingStatus.get(payload.document_id)
    file_record = await FileRecord.get(payload.document_id)
    if file_record is not None:
        _ = await di.files_service.delete(payload.document_id)
    if status is not None:
        _ = await DocumentProcessingStatus.delete_by_id(payload.document_id)
    rag_provider, _provider_name = _resolve_provider(payload.provider, billing_service=di.billing_service)
    success = await rag_provider.delete_document(payload.namespace_id, payload.document_id)
    if not success and status is None and file_record is None:
        raise WsCommandError("not_found", "Document not found", error_code='not_found')
    return RagDocumentDeleteResult(success=True, document_id=payload.document_id)


async def op_documents_index_remove(
    payload: RagDocumentRefPayload,
    *,
    user: User,
    di: Di,
) -> RagDocumentDeleteResult:
    _ = user
    await _namespace(di, payload.namespace_id)
    status = await DocumentProcessingStatus.get(payload.document_id)
    if status is not None:
        _ = await DocumentProcessingStatus.delete_by_id(payload.document_id)
    rag_provider, _provider_name = _resolve_provider(payload.provider, billing_service=di.billing_service)
    success = await rag_provider.delete_document(payload.namespace_id, payload.document_id)
    if not success and status is None:
        raise WsCommandError("not_found", "Document index not found", error_code='not_found')
    return RagDocumentDeleteResult(success=True, document_id=payload.document_id)


async def op_documents_content(
    payload: RagDocumentRefPayload,
    *,
    user: User,
    di: Di,
) -> RAGDocumentContent:
    _ = user
    await _namespace(di, payload.namespace_id)
    rag_provider, _provider_name = _resolve_provider(payload.provider, billing_service=di.billing_service)
    try:
        content = await rag_provider.get_document_content(payload.namespace_id, payload.document_id)
    except ValueError as exc:
        raise WsCommandError("internal", str(exc), error_code='internal') from exc
    if content is None:
        raise WsCommandError("not_found", "Document content not found", error_code='not_found')
    return content


async def op_documents_status(
    payload: RagDocumentStatusPayload,
    *,
    user: User,
    di: Di,
) -> DocumentProcessingStatus:
    _ = user
    _ = await _company_view(di)
    status = await DocumentProcessingStatus.get(payload.document_id)
    if status is None:
        raise WsCommandError("not_found", "Document status not found", error_code='not_found')
    return status


async def op_documents_statuses(
    payload: DocumentStatusesBatchRequest,
    *,
    user: User,
    di: Di,
) -> DocumentStatusesBatchResponse:
    _ = user
    _ = await _company_view(di)
    normalized_ids: list[str] = []
    seen: set[str] = set()
    for raw_id in payload.document_ids:
        document_id = raw_id.strip()
        if document_id == "":
            raise WsCommandError("ws_invalid_payload", "document_ids must not contain empty values", error_code='ws_invalid_payload')
        if document_id in seen:
            continue
        seen.add(document_id)
        normalized_ids.append(document_id)
    if not normalized_ids:
        raise WsCommandError("ws_invalid_payload", "document_ids is required", error_code='ws_invalid_payload')
    found = await DocumentProcessingStatus.get_many(normalized_ids)
    statuses: dict[str, DocumentProcessingStatus | None] = {
        document_id: found.get(document_id) for document_id in normalized_ids
    }
    return DocumentStatusesBatchResponse(statuses=statuses)


async def op_search_defaults(
    payload: EmptyPayload,
    *,
    user: User,
    di: Di,
) -> RAGSearchOptions:
    _ = payload, user
    company_id = require_active_company().company_id
    await di.authz_service.require_can_view(AuthzObject.company(company_id))
    return resolve_platform_search_options(settings=get_rag_settings())


async def op_search_namespace(
    payload: RagNamespaceSearchPayload,
    *,
    user: User,
    di: Di,
) -> SearchResponse:
    _ = user
    await _namespace(di, payload.namespace_id)
    if payload.filters is not None:
        try:
            validate_metadata_filters(payload.filters)
        except ValueError as exc:
            raise_invalid(exc)
    rag_provider, provider_name = _resolve_provider(payload.provider, billing_service=di.billing_service)
    settings = get_rag_settings()
    resolved_search_options = resolve_platform_search_options(
        settings=settings,
        overrides=filter_search_request_options(payload),
        per_channel_top_k=payload.per_channel_top_k,
    )
    try:
        async with traced_operation(
            "rag.search.namespace",
            event_type="rag.search",
            operation_category="rag_search",
            resource_type="rag.namespace",
            resource_id=payload.namespace_id,
            extra_attributes={
                trace_attributes.ATTR_RAG_STAGE: "search",
                "platform.rag.search_pool_size": payload.limit,
            },
        ) as span:
            results = await rag_provider.search(
                namespace_id=payload.namespace_id,
                query=payload.query,
                limit=payload.limit,
                filters=payload.filters,
                search_options=resolved_search_options,
            )
            results = await apply_rerank_after_retrieve_by_score_desc(
                results=results,
                query=payload.query,
                provider_name=provider_name,
                request_rerank=resolved_search_options.rerank,
                profile_sd=None,
                settings=settings,
                request_rerank_max_candidates=resolved_search_options.rerank_max_candidates,
                score_cache=di.rerank_score_cache,
            )
            span.set_attribute("platform.rag.result_count", len(results))
    except AIRerankerClientError as exc:
        raise WsCommandError("internal", str(exc.detail), error_code='internal') from exc
    return SearchResponse(
        results=results,
        query=payload.query,
        namespace_id=payload.namespace_id,
        provider=provider_name,
    )


async def op_search_global(
    payload: RagGlobalSearchPayload,
    *,
    user: User,
    di: Di,
) -> GlobalSearchResponse:
    _ = user
    if not payload.namespace_ids:
        raise WsCommandError("ws_invalid_payload", "No namespaces provided", error_code='ws_invalid_payload')
    for namespace_id in payload.namespace_ids:
        await _namespace(di, namespace_id)
    if payload.filters is not None:
        try:
            validate_metadata_filters(payload.filters)
        except ValueError as exc:
            raise_invalid(exc)
    rag_provider, provider_name = _resolve_provider(payload.provider, billing_service=di.billing_service)
    settings = get_rag_settings()
    resolved_search_options = resolve_platform_search_options(
        settings=settings,
        overrides=filter_search_request_options(payload),
        per_channel_top_k=payload.per_channel_top_k,
    )
    try:
        results = await rag_provider.search_multiple_namespaces(
            namespace_ids=payload.namespace_ids,
            query=payload.query,
            limit=payload.limit,
            filters=payload.filters,
            search_options=resolved_search_options,
        )
        results = await apply_rerank_after_retrieve_grouped_by_score_desc(
            results_by_namespace=results,
            namespace_order=payload.namespace_ids,
            query=payload.query,
            provider_name=provider_name,
            request_rerank=resolved_search_options.rerank,
            profile_sd=None,
            settings=settings,
            request_rerank_max_candidates=resolved_search_options.rerank_max_candidates,
            score_cache=di.rerank_score_cache,
        )
    except AIRerankerClientError as exc:
        raise WsCommandError("internal", str(exc.detail), error_code='internal') from exc
    return GlobalSearchResponse(results=results, query=payload.query, provider=provider_name)


async def op_providers_list(
    payload: EmptyPayload,
    *,
    user: User,
    di: Di,
) -> ProvidersView:
    _ = payload, user, di
    settings = get_rag_settings()
    if not settings.rag.enabled:
        raise WsCommandError("internal", "RAG is disabled", error_code='internal')
    providers: list[ProviderInfo] = []
    for name, config in settings.rag.providers.items():
        if config.enabled:
            providers.append(
                ProviderInfo(
                    name=name,
                    enabled=True,
                    is_default=(name == settings.rag.default_provider),
                    type=name,
                )
            )
    return ProvidersView(items=providers, current_provider=settings.rag.default_provider)
