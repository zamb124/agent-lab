"""
API для управления документами RAG.
"""

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from apps.rag_worker.tasks.indexing_tasks import index_rag_document_s3_task
from core.context import get_context
from core.files.models import FileResponse
from core.files.processors import FileProcessor
from core.logging import get_logger
from core.rag.factory import get_rag_provider
from core.rag.models import DocumentProcessingStatus as DocumentStatusModel
from core.rag.models import RAGDocument

from ..container import RAGContainer
from ..dependencies import get_container_dep

logger = get_logger(__name__)

router = APIRouter(tags=["documents"])


class NamespaceDocumentsSummary(BaseModel):
    """Агрегаты по списку документов в namespace (ответ GET …/documents)."""

    total_documents: int
    total_chunks: int
    status_counts: Dict[str, int]


def _split_from_status_or_metadata(
    status: Optional[DocumentStatusModel],
    doc_metadata: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if status and status.extra_metadata:
        rt = status.extra_metadata.get("indexing_runtime")
        if isinstance(rt, dict):
            sp = rt.get("split")
            if isinstance(sp, dict):
                return sp
    im = doc_metadata.get("indexing_runtime")
    if isinstance(im, dict):
        sp = im.get("split")
        if isinstance(sp, dict):
            return sp
    return None


def _runs_and_reindex(extra: Optional[Dict[str, Any]]) -> tuple[Optional[int], Optional[int]]:
    if not extra:
        return None, None
    raw = extra.get("indexing_run_count")
    if raw is None:
        return None, None
    runs = int(raw)
    return runs, max(0, runs - 1)


def _enrich_document(
    doc: RAGDocument,
    status: Optional[DocumentStatusModel],
    chunk_counts: Dict[str, int],
) -> RAGDocument:
    doc_id = doc.document_id
    chunks: Optional[int] = None
    if status is not None and status.chunks_count is not None:
        chunks = int(status.chunks_count)
    elif doc_id in chunk_counts:
        chunks = int(chunk_counts[doc_id])
    extra = status.extra_metadata if status is not None else None
    runs, reindex = _runs_and_reindex(extra if isinstance(extra, dict) else None)
    split = _split_from_status_or_metadata(status, doc.metadata)
    return doc.model_copy(
        update={
            "chunks_count": chunks,
            "indexing_runs": runs,
            "reindex_count": reindex,
            "split": split,
        }
    )


def _build_summary(documents: List[RAGDocument]) -> NamespaceDocumentsSummary:
    status_counts: Dict[str, int] = {}
    total_chunks = 0
    for d in documents:
        st = str(d.status or "unknown")
        status_counts[st] = status_counts.get(st, 0) + 1
        c = d.chunks_count
        if c is not None:
            total_chunks += int(c)
    return NamespaceDocumentsSummary(
        total_documents=len(documents),
        total_chunks=total_chunks,
        status_counts=status_counts,
    )


class DocumentListResponse(BaseModel):
    documents: List[RAGDocument]
    namespace_id: str
    provider: str
    summary: NamespaceDocumentsSummary


class DocumentUploadResponse(BaseModel):
    document_id: str
    task_id: str
    status: str
    file: FileResponse


@router.get("/namespaces/{namespace_id}/documents", response_model=DocumentListResponse)
async def list_documents(
    namespace_id: str,
    limit: int = Query(100, ge=1, le=1000),
    provider: Optional[str] = Query(None),
    container: RAGContainer = Depends(get_container_dep),
) -> DocumentListResponse:
    """Список документов в namespace (completed + in-progress)."""
    from core.config import get_settings

    settings = get_settings()
    rag_provider = get_rag_provider(provider) if provider else container.rag_provider
    provider_name = provider or settings.rag.default_provider

    completed_docs = await rag_provider.list_documents(namespace_id, limit=limit)

    status_repo = container.document_status_repository
    processing_statuses = await status_repo.list_by_namespace(
        namespace_id, status=["pending", "processing", "failed"], limit=limit
    )

    all_documents = list(completed_docs)
    for status in processing_statuses:
        em = status.extra_metadata if isinstance(status.extra_metadata, dict) else {}
        meta = {
            "file_size": status.file_size,
            "error_message": status.error_message,
            "task_id": status.task_id,
            "created_at": status.created_at.isoformat(),
            "updated_at": status.updated_at.isoformat(),
        }
        if em:
            if "indexing_runtime" in em:
                meta["indexing_runtime"] = em["indexing_runtime"]
        all_documents.append(
            RAGDocument(
                document_id=status.document_id,
                name=status.document_name,
                namespace=status.namespace_id,
                status=status.status,
                metadata=meta,
            )
        )

    sliced = all_documents[:limit]
    doc_ids = [d.document_id for d in sliced]
    status_map = await status_repo.get_latest_by_namespace_and_document_ids(
        namespace_id, doc_ids
    )
    chunk_counts = await status_repo.count_chunks_by_namespace_and_document_ids(
        namespace_id, doc_ids
    )
    enriched = [
        _enrich_document(doc, status_map.get(doc.document_id), chunk_counts)
        for doc in sliced
    ]

    return DocumentListResponse(
        documents=enriched,
        namespace_id=namespace_id,
        provider=provider_name,
        summary=_build_summary(enriched),
    )


@router.post("/namespaces/{namespace_id}/documents", status_code=202, response_model=DocumentUploadResponse)
async def upload_document(
    namespace_id: str,
    file: UploadFile = File(...),
    metadata: str = Form(default="{}"),
    provider: Optional[str] = Query(None),
    container: RAGContainer = Depends(get_container_dep),
) -> DocumentUploadResponse:
    """
    Принимает документ, сохраняет через FileProcessor (FileRecord в shared DB),
    ставит задачу индексации в воркер (TaskIQ) и отвечает сразу — без ожидания
    завершения индексации; готовность по GET /documents/{document_id}/status.

    Опционально в JSON ``metadata``: ``index_profile_config`` — частичный профиль
    (слияние с ``rag.document_indexing``), например ``{"split": {"strategy": "semantic"}}``.
    """
    from core.config import get_settings

    settings = get_settings()
    if not settings.s3.enabled or not settings.s3.default_bucket:
        raise HTTPException(status_code=503, detail="S3 не настроен.")

    metadata_dict: Dict[str, Any] = json.loads(metadata) if metadata else {}
    file_data = await file.read()

    context = get_context()
    company_id = context.active_company.company_id
    user_id = context.user.user_id

    processor = FileProcessor(file_repository=container.file_repository)
    file_record = await processor.process_file_from_bytes(
        data=file_data,
        original_name=file.filename or "document",
        content_type=file.content_type or "application/octet-stream",
        uploaded_by=user_id,
        public=False,
    )
    file_record = file_record.model_copy(
        update={
            "company_id": company_id,
            "download_url": f"/rag/api/v1/files/download/{file_record.file_id}",
        }
    )
    await container.file_repository.set(file_record)

    document_id = file_record.file_id
    metadata_dict["document_id"] = document_id
    metadata_dict["s3_bucket"] = file_record.s3_bucket
    metadata_dict["company_id"] = company_id

    status_repo = container.document_status_repository
    task_id_placeholder = f"pending_{document_id}"
    await status_repo.create_status(
        document_id=document_id,
        task_id=task_id_placeholder,
        namespace_id=namespace_id,
        document_name=file.filename or "document",
        file_size=len(file_data),
        extra_metadata={},
    )

    task = await index_rag_document_s3_task.kiq(
        company_id=company_id,
        namespace_id=namespace_id,
        s3_key=file_record.s3_key,
        document_name=file.filename or "document",
        metadata=dict(metadata_dict),
    )
    task_id = task.task_id

    await status_repo.finalize_enqueued_indexing_task(document_id, task_id)

    logger.info(
        "Документ принят: doc_id=%s, task_id=%s, s3_key=%s",
        document_id,
        task_id,
        file_record.s3_key,
    )
    return DocumentUploadResponse(
        document_id=document_id,
        task_id=task_id,
        status="pending",
        file=FileResponse.from_record(file_record),
    )


@router.delete("/namespaces/{namespace_id}/documents/{document_id}")
async def delete_document(
    namespace_id: str,
    document_id: str,
    provider: Optional[str] = Query(None),
    container: RAGContainer = Depends(get_container_dep),
):
    """Удаляет документ из S3, shared DB и векторного индекса."""
    status_repo = container.document_status_repository
    status = await status_repo.get_by_document_id(document_id)

    file_record = await container.file_repository.get(document_id)
    if file_record is not None:
        processor = FileProcessor(file_repository=container.file_repository)
        await processor.delete_file(document_id)

    await status_repo.delete_by_document_id(document_id)

    rag_provider = get_rag_provider(provider) if provider else container.rag_provider
    success = await rag_provider.delete_document(namespace_id, document_id)

    if not success and status is None and file_record is None:
        raise HTTPException(status_code=404, detail="Document not found")

    logger.info(f"Удалён документ {document_id} из namespace {namespace_id}")
    return {"success": True, "document_id": document_id}


@router.get("/documents/{document_id}/status")
async def get_document_status(
    document_id: str,
    container: RAGContainer = Depends(get_container_dep),
):
    """Статус обработки документа."""
    status_repo = container.document_status_repository
    status = await status_repo.get_by_document_id(document_id)
    if not status:
        raise HTTPException(status_code=404, detail="Document status not found")
    return status

