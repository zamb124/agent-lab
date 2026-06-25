"""HTTP client for Office document bind."""

from __future__ import annotations

from core.clients.service_client import ServiceClient
from core.documents.placement import DocsBindResult, DocsPlacement
from core.types import JsonObject, require_json_object


class DocumentsClient:
    async def bind_file(self, placement: DocsPlacement) -> DocsBindResult:
        client = ServiceClient()
        body: JsonObject = require_json_object(
            placement.model_dump(mode="json"),
            "DocsPlacement",
        )
        response = await client.post(
            "office",
            "/documents/api/v1/documents/bind",
            json=body,
            timeout=60.0,
        )
        payload = require_json_object(response, "DocumentsClient.bind_file")
        return DocsBindResult.model_validate(payload)
