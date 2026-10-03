"""Хук индексации файла в RAG после создания."""

from __future__ import annotations

from core.clients.rag_client import RagClient
from core.rag.models import RAGMetadata


async def index_file_in_rag(file_id: str, namespace_id: str, metadata: RAGMetadata | None) -> None:
    rag_metadata: RAGMetadata = metadata if metadata is not None else {}
    _ = await RagClient().index_file(namespace_id, file_id, metadata=rag_metadata)
