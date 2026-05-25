"""
API для управления документами RAG.
"""

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import Field

from apps.rag.config import get_rag_settings
from apps.rag_worker.broker import broker as rag_worker_broker
from core.context import require_active_company, require_context
from core.files.models import FileResponse
from core.files.processors import FileProcessor
from core.logging import get_logger
from core.models import StrictBaseModel
from core.pagination import OffsetPage
from core.rag.factory import get_rag_provider
from core.rag.models import (
    DocumentProcessingStatus,
    RAGDocument,
    RAGIngestTextResponse,
    RAGMetadata,
)
from core.rag.ttl import ensure_ttl_seconds_in_metadata
from core.tasks.kicker import kiq_task_name_with_context
from core.types import JsonObject, parse_json_object

from ..dependencies import ContainerDep
from .namespace_access import (
    require_registered_rag_namespace,
    validate_ingest_text_body,
    validate_rag_user_metadata,
)

logger = get_logger(__name__)

router = APIRouter(tags=["documents"])


# DocumentListResponse is replaced by OffsetPage[RAGDocument]


class DocumentUploadResponse(StrictBaseModel):
    document_id: str
    task_id: str
    status: str
    file: FileResponse


class IngestTextRequest(StrictBaseModel):
    text: str = Field(..., min_length=1)
    document_name: str | None = None
    metadata: RAGMetadata = Field(default_factory=dict)
    document_id: str | None = None


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

    rag_provider = get_rag_provider(provider, settings=settings) if provider else get_rag_provider(settings=settings)
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
    rag_provider = get_rag_provider(provider, settings=settings) if provider else get_rag_provider(settings=settings)

    completed_docs = await rag_provider.list_documents(namespace_id, limit=limit)

    status_repo = container.document_status_repository
    processing_statuses = await status_repo.list_by_namespace(
        namespace_id, status=["pending", "processing", "failed"], limit=limit
    )

    all_documents = list(completed_docs)
    for status in processing_statuses:
        all_documents.append(RAGDocument(
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
        ))

    items = all_documents[:limit]

    return OffsetPage[RAGDocument](
        items=items,
        total=len(items),
        limit=limit,
        offset=offset,
    )


@router.post("/namespaces/{namespace_id}/documents", status_code=202, response_model=DocumentUploadResponse)
async def upload_document(
    namespace_id: str,
    container: ContainerDep,
    file: Annotated[UploadFile, File()],
    metadata: Annotated[str, Form()] = "{}",
    provider: Annotated[str | None, Query()] = None,
) -> DocumentUploadResponse:
    """
    Принимает документ, сохраняет через FileProcessor (FileRecord в shared DB),
    запускает асинхронную индексацию в RAG.
    """
    settings = get_rag_settings()
    if not settings.s3.enabled or not settings.s3.default_bucket:
        raise HTTPException(status_code=503, detail="S3 не настроен.")

    metadata_dict: RAGMetadata = parse_json_object(metadata, "metadata") if metadata else {}
    file_data = await file.read()

    context = require_context()
    company_id = require_active_company().company_id
    user_id = context.user.user_id

    processor = FileProcessor(file_repository=container.file_repository)
    file_record = await processor.persist_uploaded_file(
        data=file_data,
        original_name=file.filename or "document",
        content_type=file.content_type or "application/octet-stream",
        uploaded_by=user_id,
        company_id=company_id,
        public=False,
        download_url_prefix="/rag/api/v1/files/download",
    )

    document_id = file_record.file_id
    metadata_dict["document_id"] = document_id
    metadata_dict["s3_bucket"] = file_record.s3_bucket
    metadata_dict["company_id"] = company_id
    metadata_dict["uploaded_by_user_id"] = user_id

    try:
        metadata_dict = ensure_ttl_seconds_in_metadata(
            metadata_dict,
            default_ttl_seconds=settings.rag.ttl.default_ttl_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    ttl_raw = metadata_dict["ttl_seconds"]
    if not isinstance(ttl_raw, int) or isinstance(ttl_raw, bool):
        raise RuntimeError("ensure_ttl_seconds_in_metadata returned non-integer ttl_seconds")
    ttl_sec = ttl_raw

    task_id_placeholder = f"pending_{document_id}"
    status_repo = container.document_status_repository
    _ = await status_repo.create_status(
        document_id=document_id,
        task_id=task_id_placeholder,
        namespace_id=namespace_id,
        document_name=file.filename or "document",
        file_size=len(file_data),
        ttl_seconds=ttl_sec,
        extra_metadata={},
    )

    task = await kiq_task_name_with_context(
        "rag.index_document_s3",
        rag_worker_broker,
        company_id=company_id,
        namespace_id=namespace_id,
        s3_key=file_record.s3_key,
        document_name=file.filename or "document",
        metadata=dict(metadata_dict),
        provider=provider,
    )

    _ = await status_repo.finalize_enqueued_indexing_task(document_id, task.task_id)

    logger.info(
        f"Документ принят: doc_id={document_id}, task_id={task.task_id}, s3_key={file_record.s3_key}"
    )
    return DocumentUploadResponse(
        document_id=document_id,
        task_id=task.task_id,
        status="pending",
        file=FileResponse.from_record(file_record),
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
        processor = FileProcessor(file_repository=container.file_repository)
        _ = await processor.delete_file(document_id)

    if status is not None:
        _ = await status_repo.delete_by_document_id(document_id)

    settings = get_rag_settings()
    rag_provider = get_rag_provider(provider, settings=settings) if provider else get_rag_provider(settings=settings)
    success = await rag_provider.delete_document(namespace_id, document_id)

    if not success and status is None and file_record is None:
        raise HTTPException(status_code=404, detail="Document not found")

    logger.info(f"Удалён документ {document_id} из namespace {namespace_id}")
    return {"success": True, "document_id": document_id}


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
