"""
API для управления документами RAG.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field

from apps.rag.config import get_rag_settings
from apps.rag_worker.broker import broker as rag_worker_broker
from core.context import require_active_company, require_context
from core.logging import get_logger
from core.models import StrictBaseModel
from core.pagination import OffsetPage
from core.rag.factory import get_rag_provider
from core.rag.models import (
    DocumentProcessingStatus,
    RAGDocument,
    RAGDocumentContent,
    RAGIngestTextResponse,
    RAGMetadata,
)
from core.rag.ttl import ensure_ttl_seconds_in_metadata
from core.tasks.kicker import kiq_task_name_with_context
from core.types import JsonObject

from ..dependencies import ContainerDep
from .namespace_access import (
    require_registered_rag_namespace,
    validate_ingest_text_body,
    validate_rag_user_metadata,
)

logger = get_logger(__name__)

router = APIRouter(tags=["documents"])


# DocumentListResponse заменён на OffsetPage[RAGDocument]


class IngestTextRequest(StrictBaseModel):
    text: str = Field(..., min_length=1)
    document_name: str | None = None
    metadata: RAGMetadata = Field(default_factory=dict)
    document_id: str | None = None


class IndexFileRequest(StrictBaseModel):
    file_id: str = Field(..., min_length=1)
    document_name: str | None = None
    metadata: RAGMetadata = Field(default_factory=dict)


class IndexFileResponse(StrictBaseModel):
    document_id: str
    task_id: str
    status: str
    file_id: str


@router.post("/namespaces/{namespace_id}/ingest-text", response_model=RAGIngestTextResponse)
async def ingest_text(
    namespace_id: str,
    request: IngestTextRequest,
    container: ContainerDep,
    provider: Annotated[str | None, Query()] = None,
) -> RAGIngestTextResponse:
    """
    Синхронная индексация произвольного текста в namespace (без файла и S3).
    Namespace должен существовать в репозитории текущей компании.
    """
    await require_registered_rag_namespace(namespace_id, container)
    validate_rag_user_metadata(request.metadata)
    text = validate_ingest_text_body(request.text)

    context = require_context()
    company_id = require_active_company().company_id
    user_id = context.user.user_id

    merged_meta: RAGMetadata = dict(request.metadata)
    merged_meta["company_id"] = company_id
    merged_meta["uploaded_by_user_id"] = user_id
    if request.document_id:
        merged_meta["document_id"] = request.document_id

    settings = get_rag_settings()
    try:
        merged_meta = ensure_ttl_seconds_in_metadata(
            merged_meta,
            default_ttl_seconds=settings.rag.ttl.default_ttl_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    rag_provider = (
        get_rag_provider(provider, settings=settings)
        if provider
        else get_rag_provider(settings=settings)
    )
    provider_name = provider or settings.rag.default_provider

    doc = await rag_provider.upload_document_from_text(
        namespace_id=namespace_id,
        text=text,
        document_name=request.document_name,
        metadata=merged_meta,
    )

    return RAGIngestTextResponse(
        document_id=doc.document_id,
        document_name=doc.name,
        namespace_id=namespace_id,
        status=doc.status,
        provider=provider_name,
    )


@router.get("/namespaces/{namespace_id}/documents", response_model=OffsetPage[RAGDocument])
async def list_documents(
    namespace_id: str,
    container: ContainerDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    provider: Annotated[str | None, Query()] = None,
) -> OffsetPage[RAGDocument]:
    """Список документов в namespace (completed + in-progress)."""
    settings = get_rag_settings()
    rag_provider = (
        get_rag_provider(provider, settings=settings)
        if provider
        else get_rag_provider(settings=settings)
    )

    completed_docs = await rag_provider.list_documents(namespace_id, limit=limit)

    status_repo = container.document_status_repository
    processing_statuses = await status_repo.list_by_namespace(
        namespace_id, status=["pending", "processing", "failed"], limit=limit
    )

    all_documents = list(completed_docs)
    for status in processing_statuses:
        all_documents.append(
            RAGDocument(
                document_id=status.document_id,
                name=status.document_name,
                namespace=status.namespace_id,
                status=status.status,
                metadata={
                    "file_size": status.file_size,
                    "error_message": status.error_message,
                    "task_id": status.task_id,
                    "created_at": status.created_at.isoformat(),
                    "updated_at": status.updated_at.isoformat(),
                },
            )
        )

    items = all_documents[:limit]

    return OffsetPage[RAGDocument](
        items=items,
        total=len(items),
        limit=limit,
        offset=offset,
    )


async def _enqueue_s3_indexing_task(
    *,
    namespace_id: str,
    container: ContainerDep,
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
            metadata_dict,
            default_ttl_seconds=settings.rag.ttl.default_ttl_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ttl_raw = metadata_dict["ttl_seconds"]
    if not isinstance(ttl_raw, int) or isinstance(ttl_raw, bool):
        raise RuntimeError("ensure_ttl_seconds_in_metadata returned non-integer ttl_seconds")
    ttl_sec = ttl_raw

    status_repo = container.document_status_repository
    task_id_placeholder = f"pending_{document_id}"
    _ = await status_repo.create_status(
        document_id=document_id,
        task_id=task_id_placeholder,
        namespace_id=namespace_id,
        document_name=document_name,
        file_size=file_size,
        ttl_seconds=ttl_sec,
        extra_metadata={},
    )

    company_id = require_active_company().company_id
    task = await kiq_task_name_with_context(
        "rag.index_document_s3",
        rag_worker_broker,
        company_id=company_id,
        namespace_id=namespace_id,
        s3_key=s3_key,
        document_name=document_name,
        metadata=dict(metadata_dict),
        provider=provider,
    )
    _ = await status_repo.finalize_enqueued_indexing_task(document_id, task.task_id)
    return document_id, task.task_id


@router.post(
    "/namespaces/{namespace_id}/documents/index-file",
    status_code=202,
    response_model=IndexFileResponse,
)
async def index_existing_file(
    namespace_id: str,
    request: IndexFileRequest,
    container: ContainerDep,
    provider: Annotated[str | None, Query()] = None,
) -> IndexFileResponse:
    """
    Асинхронная индексация существующего FileRecord (без повторной загрузки в S3).
    Владелец байтов — peer-сервис (Office и т.п.); RAG только строит vector index.
    """
    await require_registered_rag_namespace(namespace_id, container)
    validate_rag_user_metadata(request.metadata)

    file_id = request.file_id.strip()
    if file_id == "":
        raise HTTPException(status_code=400, detail="file_id обязателен")

    context = require_context()
    company_id = require_active_company().company_id
    user_id = context.user.user_id

    file_record = await container.file_repository.get(file_id)
    if file_record is None:
        raise HTTPException(status_code=404, detail="Файл не найден")
    if file_record.company_id != company_id:
        raise HTTPException(status_code=403, detail="Файл не принадлежит компании")

    document_name = request.document_name or file_record.original_name
    metadata_dict: RAGMetadata = dict(request.metadata)
    metadata_dict["document_id"] = file_id
    metadata_dict["s3_bucket"] = file_record.s3_bucket
    metadata_dict["company_id"] = company_id
    metadata_dict["uploaded_by_user_id"] = user_id
    metadata_dict["external_file_owner"] = "peer"

    document_id, task_id = await _enqueue_s3_indexing_task(
        namespace_id=namespace_id,
        container=container,
        document_id=file_id,
        s3_key=file_record.s3_key,
        document_name=document_name,
        file_size=file_record.file_size,
        metadata_dict=metadata_dict,
        provider=provider,
    )

    logger.info(
        "index-file принят: doc_id=%s task_id=%s s3_key=%s namespace=%s",
        document_id,
        task_id,
        file_record.s3_key,
        namespace_id,
    )
    return IndexFileResponse(
        document_id=document_id,
        task_id=task_id,
        status="pending",
        file_id=file_id,
    )


@router.delete("/namespaces/{namespace_id}/documents/{document_id}")
async def delete_document(
    namespace_id: str,
    document_id: str,
    container: ContainerDep,
    provider: Annotated[str | None, Query()] = None,
) -> JsonObject:
    """Удаляет документ из S3, shared DB и векторного индекса."""
    status_repo = container.document_status_repository
    status = await status_repo.get_by_document_id(document_id)

    file_record = await container.file_repository.get(document_id)
    if file_record is not None:
        _ = await container.files_service.delete(document_id)

    if status is not None:
        _ = await status_repo.delete_by_document_id(document_id)

    settings = get_rag_settings()
    rag_provider = (
        get_rag_provider(provider, settings=settings)
        if provider
        else get_rag_provider(settings=settings)
    )
    success = await rag_provider.delete_document(namespace_id, document_id)

    if not success and status is None and file_record is None:
        raise HTTPException(status_code=404, detail="Document not found")

    logger.info(f"Удалён документ {document_id} из namespace {namespace_id}")
    return {"success": True, "document_id": document_id}


@router.delete("/namespaces/{namespace_id}/documents/{document_id}/index")
async def delete_document_index(
    namespace_id: str,
    document_id: str,
    container: ContainerDep,
    provider: Annotated[str | None, Query()] = None,
) -> JsonObject:
    """Удаляет только vector index и статус обработки; FileRecord и S3 не трогает."""
    await require_registered_rag_namespace(namespace_id, container)

    status_repo = container.document_status_repository
    status = await status_repo.get_by_document_id(document_id)
    if status is not None:
        _ = await status_repo.delete_by_document_id(document_id)

    settings = get_rag_settings()
    rag_provider = (
        get_rag_provider(provider, settings=settings)
        if provider
        else get_rag_provider(settings=settings)
    )
    success = await rag_provider.delete_document(namespace_id, document_id)

    if not success and status is None:
        raise HTTPException(status_code=404, detail="Document index not found")

    logger.info(
        "Удалён vector index document_id=%s namespace=%s",
        document_id,
        namespace_id,
    )
    return {"success": True, "document_id": document_id}


@router.get(
    "/namespaces/{namespace_id}/documents/{document_id}/content",
    response_model=RAGDocumentContent,
)
async def get_document_content(
    namespace_id: str,
    document_id: str,
    container: ContainerDep,
    provider: Annotated[str | None, Query()] = None,
) -> RAGDocumentContent:
    """Собранный текст документа из чанков индекса."""
    await require_registered_rag_namespace(namespace_id, container)
    settings = get_rag_settings()
    rag_provider = (
        get_rag_provider(provider, settings=settings)
        if provider
        else get_rag_provider(settings=settings)
    )
    try:
        content = await rag_provider.get_document_content(namespace_id, document_id)
    except ValueError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    if content is None:
        raise HTTPException(status_code=404, detail="Document content not found")
    return content


@router.get("/documents/{document_id}/status")
async def get_document_status(
    document_id: str,
    container: ContainerDep,
) -> DocumentProcessingStatus:
    """Статус обработки документа."""
    status_repo = container.document_status_repository
    status = await status_repo.get_by_document_id(document_id)
    if not status:
        raise HTTPException(status_code=404, detail="Document status not found")
    return status
