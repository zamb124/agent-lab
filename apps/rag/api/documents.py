"""Документы RAG: тонкая REST-обвязка тех же `op_*`."""

from typing import Annotated

from fastapi import APIRouter, Query

from apps.rag.models import (
    DocumentStatusesBatchRequest,
    DocumentStatusesBatchResponse,
    IndexFileRequest,
    IndexFileResponse,
    IngestTextRequest,
    RagDocumentDeleteResult,
)
from apps.rag.realtime.operations import (
    RagDocumentRefPayload,
    RagDocumentsListPayload,
    RagDocumentStatusPayload,
    RagIndexFilePayload,
    RagIngestTextPayload,
    op_documents_content,
    op_documents_index_file,
    op_documents_index_remove,
    op_documents_ingest_text,
    op_documents_list,
    op_documents_remove,
    op_documents_status,
    op_documents_statuses,
)
from core.context import require_context
from core.pagination import OffsetPage
from core.rag.models import (
    DocumentProcessingStatus,
    RAGDocument,
    RAGDocumentContent,
    RAGIngestTextResponse,
)

from ..dependencies import ContainerDep

router = APIRouter(tags=["documents"])


@router.post("/namespaces/{namespace_id}/ingest-text", response_model=RAGIngestTextResponse)
async def ingest_text(
    namespace_id: str,
    request: IngestTextRequest,
    container: ContainerDep,
    provider: Annotated[str | None, Query()] = None,
) -> RAGIngestTextResponse:
    return await op_documents_ingest_text(
        RagIngestTextPayload(
            namespace_id=namespace_id,
            text=request.text,
            document_name=request.document_name,
            metadata=request.metadata,
            document_id=request.document_id,
            provider=provider,
        ),
        user=require_context().user,
        container=container,
    )


@router.get("/namespaces/{namespace_id}/documents", response_model=OffsetPage[RAGDocument])
async def list_documents(
    namespace_id: str,
    container: ContainerDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    provider: Annotated[str | None, Query()] = None,
) -> OffsetPage[RAGDocument]:
    return await op_documents_list(
        RagDocumentsListPayload(
            namespace_id=namespace_id, offset=offset, limit=limit, provider=provider
        ),
        user=require_context().user,
        container=container,
    )


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
    return await op_documents_index_file(
        RagIndexFilePayload(
            namespace_id=namespace_id,
            file_id=request.file_id,
            document_name=request.document_name,
            metadata=request.metadata,
            provider=provider,
        ),
        user=require_context().user,
        container=container,
    )


@router.delete("/namespaces/{namespace_id}/documents/{document_id}")
async def delete_document(
    namespace_id: str,
    document_id: str,
    container: ContainerDep,
    provider: Annotated[str | None, Query()] = None,
) -> RagDocumentDeleteResult:
    return await op_documents_remove(
        RagDocumentRefPayload(
            namespace_id=namespace_id, document_id=document_id, provider=provider
        ),
        user=require_context().user,
        container=container,
    )


@router.delete("/namespaces/{namespace_id}/documents/{document_id}/index")
async def delete_document_index(
    namespace_id: str,
    document_id: str,
    container: ContainerDep,
    provider: Annotated[str | None, Query()] = None,
) -> RagDocumentDeleteResult:
    return await op_documents_index_remove(
        RagDocumentRefPayload(
            namespace_id=namespace_id, document_id=document_id, provider=provider
        ),
        user=require_context().user,
        container=container,
    )


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
    return await op_documents_content(
        RagDocumentRefPayload(
            namespace_id=namespace_id, document_id=document_id, provider=provider
        ),
        user=require_context().user,
        container=container,
    )


@router.get("/documents/{document_id}/status")
async def get_document_status(
    document_id: str,
    container: ContainerDep,
) -> DocumentProcessingStatus:
    return await op_documents_status(
        RagDocumentStatusPayload(document_id=document_id),
        user=require_context().user,
        container=container,
    )


@router.post("/documents/statuses", response_model=DocumentStatusesBatchResponse)
async def get_documents_statuses_batch(
    body: DocumentStatusesBatchRequest,
    container: ContainerDep,
) -> DocumentStatusesBatchResponse:
    return await op_documents_statuses(
        body, user=require_context().user, container=container
    )
