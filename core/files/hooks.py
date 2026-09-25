"""Хуки ``FilesService`` процесса: Documents bind каждого durable файла и RAG-индексация."""

from __future__ import annotations

from core.clients.documents_client import DocumentsClient
from core.clients.rag_client import RagClient
from core.documents.placement import DocsBindResult, DocsPlacement
from core.rag.models import RAGMetadata


async def bind_document_placement(placement: DocsPlacement) -> DocsBindResult:
    """Documents bind каждого durable файла процесса."""
    return await DocumentsClient().bind_file(placement)


async def index_file_in_rag(file_id: str, namespace_id: str, metadata: RAGMetadata | None) -> None:
    rag_metadata: RAGMetadata = metadata if metadata is not None else {}
    _ = await RagClient().index_file(namespace_id, file_id, metadata=rag_metadata)
