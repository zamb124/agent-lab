"""RAG document status push публикуется на `platform:events`."""

from __future__ import annotations

import pytest

from apps.rag.events import RAG_DOCUMENT_STATUS_UPDATED, publish_rag_document_status_updated
from tests.fixtures.platform_events import platform_events_listener


@pytest.mark.asyncio
async def test_publish_rag_document_status_updated_on_stream(unique_id: str) -> None:
    document_id = f"doc_{unique_id}"
    async with platform_events_listener() as receive:
        await publish_rag_document_status_updated(
            company_id="system",
            document_id=document_id,
            namespace_id=f"ns_{unique_id}",
            status="completed",
            document_name="report.pdf",
            chunks_count=3,
        )
        events = await receive(RAG_DOCUMENT_STATUS_UPDATED, None, 3.0)
        matched = [e for e in events if e["payload"].get("document_id") == document_id]
        assert len(matched) == 1
        assert matched[0]["payload"]["status"] == "completed"
        assert matched[0]["payload"]["chunks_count"] == 3
        assert matched[0]["company_id"] == "system"
