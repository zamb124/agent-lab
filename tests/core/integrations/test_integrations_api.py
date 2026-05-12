"""
Тесты API endpoints интеграций: credentials CRUD и OAuth callback.

Используются реальные PostgreSQL + ASGI-клиент flows_client + auth.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from core.integrations.guided_integration_error import (
    GuidedIntegrationError,
    GuidedIntegrationLink,
)
from core.integrations.models import IntegrationCredential, IntegrationProvider
from core.integrations.repository import IntegrationCredentialRepository


@pytest.fixture()
def credential_repository(app) -> IntegrationCredentialRepository:
    from core.config import get_settings
    settings = get_settings()
    return IntegrationCredentialRepository(db_url=settings.database.shared_url)


async def _insert_credential(
    repo: IntegrationCredentialRepository,
    *,
    credential_id: str,
    company_id: str,
    user_id: str,
    provider: IntegrationProvider = IntegrationProvider.GOOGLE,
    service: str = "docs",
) -> IntegrationCredential:
    now = datetime.now(timezone.utc)
    cred = IntegrationCredential(
        credential_id=credential_id,
        company_id=company_id,
        user_id=user_id,
        provider=provider,
        service=service,
        access_token=f"token-{credential_id}",
        refresh_token=f"refresh-{credential_id}",
        created_at=now,
        updated_at=now,
    )
    await repo.upsert(cred)
    return cred


class TestListCredentials:
    @pytest.mark.asyncio
    async def test_returns_user_items(
        self,
        flows_client,
        auth_headers_system,
        credential_repository,
        system_user_id,
        unique_id,
    ) -> None:
        svc_a = f"svc-a-{unique_id}"
        svc_b = f"svc-b-{unique_id}"
        for svc in (svc_a, svc_b):
            await _insert_credential(
                credential_repository,
                credential_id=f"cred-list-{unique_id}-{svc}",
                company_id="system",
                user_id=system_user_id,
                service=svc,
            )

        resp = await flows_client.get(
            "/flows/api/v1/integrations/credentials",
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        items = data["items"]
        services = {item["service"] for item in items}
        assert svc_a in services
        assert svc_b in services
        for item in items:
            assert "access_token" not in item
            assert "refresh_token" not in item

    @pytest.mark.asyncio
    async def test_empty_when_no_credentials(
        self,
        flows_client,
        auth_headers_system,
    ) -> None:
        resp = await flows_client.get(
            "/flows/api/v1/integrations/credentials",
            headers=auth_headers_system,
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_unauthorized_without_auth(
        self,
        flows_client,
    ) -> None:
        resp = await flows_client.get("/flows/api/v1/integrations/credentials")
        assert resp.status_code in (401, 403)


class TestDeleteCredential:
    @pytest.mark.asyncio
    async def test_delete_success(
        self,
        flows_client,
        auth_headers_system,
        credential_repository,
        system_user_id,
        unique_id,
    ) -> None:
        svc = f"svc-del-{unique_id}"
        await _insert_credential(
            credential_repository,
            credential_id=f"cred-del-{unique_id}",
            company_id="system",
            user_id=system_user_id,
            provider=IntegrationProvider.GOOGLE,
            service=svc,
        )

        resp = await flows_client.delete(
            f"/flows/api/v1/integrations/credentials/google/{svc}",
            headers=auth_headers_system,
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        loaded = await credential_repository.get_by_user_provider_service(
            company_id="system",
            user_id=system_user_id,
            provider=IntegrationProvider.GOOGLE,
            service=svc,
        )
        assert loaded is None

    @pytest.mark.asyncio
    async def test_delete_not_found(
        self,
        flows_client,
        auth_headers_system,
    ) -> None:
        resp = await flows_client.delete(
            "/flows/api/v1/integrations/credentials/google/nonexistent",
            headers=auth_headers_system,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_invalid_provider(
        self,
        flows_client,
        auth_headers_system,
    ) -> None:
        resp = await flows_client.delete(
            "/flows/api/v1/integrations/credentials/invalid_provider/docs",
            headers=auth_headers_system,
        )
        assert resp.status_code == 422


class TestOAuthCallback:
    @pytest.mark.asyncio
    async def test_missing_params(self, flows_client) -> None:
        resp = await flows_client.get("/flows/api/v1/integrations/oauth/callback")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_error_param(self, flows_client) -> None:
        resp = await flows_client.get(
            "/flows/api/v1/integrations/oauth/callback",
            params={"error": "access_denied"},
        )
        assert resp.status_code == 400
        assert "access_denied" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_expired_state(self, flows_client) -> None:
        resp = await flows_client.get(
            "/flows/api/v1/integrations/oauth/callback",
            params={"code": "some-code", "state": "nonexistent-state"},
        )
        assert resp.status_code == 400
        assert "expired" in resp.json()["detail"].lower() or "invalid" in resp.json()["detail"].lower()


class TestOAuthCallbackGuidedIntegrationError:
    @pytest.mark.asyncio
    async def test_returns_json_without_sec_fetch_dest(self, flows_client, flows_app) -> None:
        exc = GuidedIntegrationError(
            code="test_oauth_guided",
            title_ru="RU title",
            title_en="EN title",
            message_ru="RU body",
            message_en="EN body",
            links=(
                GuidedIntegrationLink(
                    href="/crm/settings/spaces",
                    label_ru="Lru",
                    label_en="Len",
                ),
            ),
        )
        oauth = flows_app.state.container.oauth_service
        with patch.object(oauth, "complete_oauth", new=AsyncMock(side_effect=exc)):
            resp = await flows_client.get(
                "/flows/api/v1/integrations/oauth/callback",
                params={"code": "x", "state": "y"},
                headers={"Accept-Language": "en"},
            )
        assert resp.status_code == 400
        assert resp.headers.get("content-type", "").startswith("application/json")
        payload = resp.json()
        assert payload["code"] == "test_oauth_guided"
        assert payload["detail"] == "EN body"
        assert payload["guided"]["title"] == "EN title"
        assert payload["guided"]["links"][0]["href"] == "/crm/settings/spaces"
        assert "request_id" in payload

    @pytest.mark.asyncio
    async def test_returns_html_for_sec_fetch_dest_document(self, flows_client, flows_app) -> None:
        exc = GuidedIntegrationError(
            code="test_oauth_guided_html",
            title_ru="RU title",
            title_en="EN title",
            message_ru="RU body",
            message_en="EN body",
            links=(
                GuidedIntegrationLink(
                    href="/crm/settings/spaces",
                    label_ru="Lru",
                    label_en="Len",
                ),
            ),
        )
        oauth = flows_app.state.container.oauth_service
        with patch.object(oauth, "complete_oauth", new=AsyncMock(side_effect=exc)):
            resp = await flows_client.get(
                "/flows/api/v1/integrations/oauth/callback",
                params={"code": "x", "state": "y"},
                headers={
                    "Sec-Fetch-Dest": "document",
                    "Accept-Language": "en",
                },
            )
        assert resp.status_code == 400
        assert "text/html" in resp.headers.get("content-type", "")
        assert b"EN title" in resp.content
        assert b"/crm/settings/spaces" in resp.content

    @pytest.mark.asyncio
    async def test_value_error_returns_html_when_document_navigation(
        self, flows_client, flows_app,
    ) -> None:
        oauth = flows_app.state.container.oauth_service
        with patch.object(
            oauth,
            "complete_oauth",
            new=AsyncMock(side_effect=ValueError("plain error")),
        ):
            resp = await flows_client.get(
                "/flows/api/v1/integrations/oauth/callback",
                params={"code": "x", "state": "y"},
                headers={
                    "Sec-Fetch-Dest": "document",
                    "Accept-Language": "en",
                },
            )
        assert resp.status_code == 400
        assert "text/html" in resp.headers.get("content-type", "")
        assert b"plain error" in resp.content
        assert b"Connection failed" in resp.content
