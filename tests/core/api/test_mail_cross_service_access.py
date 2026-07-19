"""Cross-service visibility of mail API (как calendar)."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_mail_bindings_me_available_in_all_services(
    unique_id: str,
    frontend_client,
    flows_client,
    crm_client,
    rag_client,
    sync_client,
    auth_headers_system,
) -> None:
    _ = unique_id
    clients = [
        ("frontend", frontend_client, "/frontend/api/mail/bindings/me"),
        ("flows", flows_client, "/flows/api/mail/bindings/me"),
        ("crm", crm_client, "/crm/api/mail/bindings/me"),
        ("rag", rag_client, "/rag/api/mail/bindings/me"),
        ("sync", sync_client, "/sync/api/mail/bindings/me"),
    ]
    for service_name, client, url in clients:
        response = await client.get(url, headers=auth_headers_system)
        assert response.status_code == 200, f"{service_name} must expose mail bindings/me"
        data = response.json()
        assert isinstance(data, dict)
        assert "items" in data and isinstance(data["items"], list)
