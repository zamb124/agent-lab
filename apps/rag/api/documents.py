"""
API для управления документами RAG.
"""

import json
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from pydantic import BaseModel

from apps.rag_worker.tasks.indexing_tasks import upload_document_task
from core.context import get_context
from core.files.models import FileResponse
from core.files.processors import FileProcessor
from core.logging import get_logger
from core.rag.factory import get_rag_provider
from core.rag.models import RAGDocument
from ..container import RAGContainer
from ..dependencies import get_container_dep

logger = get_logger(__name__)

router = APIRouter(tags=["documents"])


class DocumentListResponse(BaseModel):
    documents: List[RAGDocument]
    namespace_id: str
    provider: str


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

    return DocumentListResponse(
        documents=all_documents[:limit],
        namespace_id=namespace_id,
        provider=provider_name,
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
    запускает асинхронную индексацию в RAG.
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
    file_record = file_record.model_copy(update={
        "company_id": company_id,
        "download_url": f"/rag/api/v1/files/download/{file_record.file_id}",
    })
    await container.file_repository.set(file_record)

    document_id = file_record.file_id
    metadata_dict["document_id"] = document_id
    metadata_dict["s3_bucket"] = file_record.s3_bucket

    task_id_placeholder = f"task_{document_id}"
    status_repo = container.document_status_repository
    await status_repo.create_status(
        document_id=document_id,
        task_id=task_id_placeholder,
        namespace_id=namespace_id,
        document_name=file.filename or "document",
        file_size=len(file_data),
    )

    task = await upload_document_task.kiq(
        namespace_id=namespace_id,
        s3_key=file_record.s3_key,
        document_name=file.filename or "document",
        metadata=metadata_dict,
    )

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

    if status is not None:
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
