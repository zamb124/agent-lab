"""Каталог событий RAG на шине `platform:events`."""

from __future__ import annotations

from pydantic import BaseModel

from core.events import publish_event_to_company, register_platform_event

RAG_DOCUMENT_STATUS_UPDATED = "rag/document/status_updated"


class RagDocumentStatusUpdatedEventPayload(BaseModel):
    """Payload `rag/document/status_updated`."""

    document_id: str
    namespace_id: str
    company_id: str
    status: str
    document_name: str | None = None
    error_message: str | None = None
    chunks_count: int | None = None


register_platform_event(
    RAG_DOCUMENT_STATUS_UPDATED,
    RagDocumentStatusUpdatedEventPayload,
    description="Смена статуса индексации RAG-документа (pending/processing/completed/failed).",
)


async def publish_rag_document_status_updated(
    *,
    company_id: str,
    document_id: str,
    namespace_id: str,
    status: str,
    document_name: str | None = None,
    error_message: str | None = None,
    chunks_count: int | None = None,
) -> None:
    payload = RagDocumentStatusUpdatedEventPayload(
        document_id=document_id,
        namespace_id=namespace_id,
        company_id=company_id,
        status=status,
        document_name=document_name,
        error_message=error_message,
        chunks_count=chunks_count,
    )
    await publish_event_to_company(
        company_id,
        RAG_DOCUMENT_STATUS_UPDATED,
        payload.model_dump(mode="json"),
    )


__all__ = [
    "RAG_DOCUMENT_STATUS_UPDATED",
    "RagDocumentStatusUpdatedEventPayload",
    "publish_rag_document_status_updated",
]
