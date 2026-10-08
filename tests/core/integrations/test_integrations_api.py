"""
Тесты API endpoints интеграций: credentials CRUD и OAuth callback.

Используются реальные PostgreSQL + ASGI-клиент flows_client + auth.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import parse_qs, urlparse

import pytest
from aiohttp import web

import core.integrations.oauth_service as oauth_service_module
from apps.flows.di import FlowsDi
from core.config import get_settings
from core.config.models import AuthConfig, AuthProviderConfig
from core.di import require_di
from core.integrations.guided_integration_error import (
    GuidedIntegrationError,
    GuidedIntegrationLink,
)
from core.integrations.models import IntegrationCredential, IntegrationProvider
from core.integrations.oauth_service import (
    set_oauth_credential_saved_hook,
)
from tests.fixtures.aiohttp_ephemeral import ephemeral_web_server


@pytest.fixture(autouse=True)
def credential_repository(app: object) -> None:
    _ = app
    from core.config import get_settings

    settings = get_settings()
    shared_url = settings.database.shared_url
    if shared_url is None:
        raise RuntimeError("DATABASE__SHARED_URL обязателен для тестов integrations API")


async def _insert_credential(
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
    await IntegrationCredential.upsert_by_credential_id(cred)
    return cred


def _token_app() -> web.Application:
    async def token(_request: web.Request) -> web.Response:
        return web.json_response(
            {
                "access_token": "guided-access",
                "refresh_token": "guided-refresh",
                "expires_in": 3600,
                "token_type": "Bearer",
            }
        )

    app = web.Application()
    app.router.add_post("/token", token)
    return app


@asynccontextmanager
async def _oauth_save_raises(
    monkeypatch: pytest.MonkeyPatch,
    flows_app: object,
    *,
    service_name: str,
    system_user_id: str,
    exc: BaseException,
    oauth_ui_locale: Literal["ru", "en"] | None = None,
) -> AsyncIterator[str]:
    async with ephemeral_web_server(_token_app()) as base_url:
        settings = get_settings()
        monkeypatch.setattr(
            settings,
            "auth",
            AuthConfig(
                providers={
                    "google": AuthProviderConfig(
                        client_id="test-client-id",
                        client_secret="test-secret",
                        auth_url="https://accounts.google.com/o/oauth2/v2/auth",
                        token_url=f"{base_url}/token",
                    ),
                },
            ),
        )

        async def fail(_credential: IntegrationCredential) -> None:
            raise exc

        previous = oauth_service_module._oauth_credential_saved_hook
        set_oauth_credential_saved_hook(fail)
        oauth = require_di(flows_app, FlowsDi).oauth_service
        try:
            auth_url = await oauth.build_auth_url(
                provider=IntegrationProvider.GOOGLE,
                service=service_name,
                scopes=["openid"],
                user_id=system_user_id,
                company_id="system",
                redirect_uri="http://127.0.0.1/callback",
                return_path="/",
                oauth_ui_locale=oauth_ui_locale,
            )
            state = parse_qs(urlparse(auth_url).query)["state"][0]
            yield state
        finally:
            oauth_service_module._oauth_credential_saved_hook = previous
            _ = await IntegrationCredential.delete_by_user_provider_service(
                "system",
                system_user_id,
                IntegrationProvider.GOOGLE,
                service_name,
            )


class TestListCredentials:
    @pytest.mark.asyncio
    async def test_returns_user_items(
        self,
        flows_client,
        auth_headers_system,
        system_user_id,
        unique_id,
    ) -> None:
        svc_a = f"svc-a-{unique_id}"
        svc_b = f"svc-b-{unique_id}"
        for svc in (svc_a, svc_b):
            await _insert_credential(
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
        system_user_id,
        unique_id,
    ) -> None:
        svc = f"svc-del-{unique_id}"
        await _insert_credential(
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

        loaded = await IntegrationCredential.by_natural_key(
            company_id="system",
            user_id=system_user_id,
            provider=IntegrationProvider.GOOGLE,
            service=svc,
            mailbox_binding_id=None,
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
        assert resp.json()["error_code"] == "not_found"

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
        assert resp.status_code == 400
        assert resp.json()["error_code"] == "ws_invalid_payload"


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
        assert (
            "expired" in resp.json()["detail"].lower() or "invalid" in resp.json()["detail"].lower()
        )


class TestOAuthCallbackGuidedIntegrationError:
    @pytest.mark.asyncio
    async def test_returns_json_without_sec_fetch_dest(
        self,
        flows_client,
        flows_app,
        monkeypatch: pytest.MonkeyPatch,
        unique_id: str,
        system_user_id: str,
    ) -> None:
        exc = GuidedIntegrationError(
            code="test_oauth_guided",
            title_ru="RU title",
            title_en="EN title",
            message_ru="RU body",
            message_en="EN body",
            links=(
                GuidedIntegrationLink(
                    href="/crm/namespaces",
                    label_ru="Lru",
                    label_en="Len",
                ),
            ),
        )
        async with _oauth_save_raises(
            monkeypatch,
            flows_app,
            service_name=f"guided-json-{unique_id}",
            system_user_id=system_user_id,
            exc=exc,
        ) as state:
            resp = await flows_client.get(
                "/flows/api/v1/integrations/oauth/callback",
                params={"code": "x", "state": state},
                headers={"Accept-Language": "en"},
            )
        assert resp.status_code == 400
        assert resp.headers.get("content-type", "").startswith("application/json")
        payload = resp.json()
        assert payload["code"] == "test_oauth_guided"
        assert payload["detail"] == "EN body"
        assert payload["guided"]["title"] == "EN title"
        assert payload["guided"]["links"][0]["href"] == "/crm/namespaces"
        assert "request_id" in payload

    @pytest.mark.asyncio
    async def test_returns_html_for_sec_fetch_dest_document(
        self,
        flows_client,
        flows_app,
        monkeypatch: pytest.MonkeyPatch,
        unique_id: str,
        system_user_id: str,
    ) -> None:
        exc = GuidedIntegrationError(
            code="test_oauth_guided_html",
            title_ru="RU title",
            title_en="EN title",
            message_ru="RU body",
            message_en="EN body",
            links=(
                GuidedIntegrationLink(
                    href="/crm/namespaces",
                    label_ru="Lru",
                    label_en="Len",
                ),
            ),
        )
        async with _oauth_save_raises(
            monkeypatch,
            flows_app,
            service_name=f"guided-html-{unique_id}",
            system_user_id=system_user_id,
            exc=exc,
        ) as state:
            resp = await flows_client.get(
                "/flows/api/v1/integrations/oauth/callback",
                params={"code": "x", "state": state},
                headers={
                    "Sec-Fetch-Dest": "document",
                    "Accept-Language": "en",
                },
            )
        assert resp.status_code == 400
        assert "text/html" in resp.headers.get("content-type", "")
        assert b"EN title" in resp.content
        assert b"/crm/namespaces" in resp.content

    @pytest.mark.asyncio
    async def test_returns_html_russian_when_language_cookie_ru(
        self,
        flows_client,
        flows_app,
        monkeypatch: pytest.MonkeyPatch,
        unique_id: str,
        system_user_id: str,
    ) -> None:
        exc = GuidedIntegrationError(
            code="test_oauth_guided_cookie_ru",
            title_ru="Заголовок по-русски",
            title_en="EN title",
            message_ru="Тело ru",
            message_en="EN body",
            links=(
                GuidedIntegrationLink(
                    href="/crm/namespaces",
                    label_ru="Пространства",
                    label_en="Spaces",
                ),
            ),
        )
        async with _oauth_save_raises(
            monkeypatch,
            flows_app,
            service_name=f"guided-cookie-{unique_id}",
            system_user_id=system_user_id,
            exc=exc,
        ) as state:
            resp = await flows_client.get(
                "/flows/api/v1/integrations/oauth/callback",
                params={"code": "x", "state": state},
                headers={
                    "Sec-Fetch-Dest": "document",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Cookie": "language=ru",
                },
            )
        assert resp.status_code == 400
        assert "text/html" in resp.headers.get("content-type", "")
        assert "Заголовок по-русски".encode("utf-8") in resp.content

    @pytest.mark.asyncio
    async def test_returns_html_russian_when_oauth_state_ui_locale_overrides_accept_en(
        self,
        flows_client,
        flows_app,
        monkeypatch: pytest.MonkeyPatch,
        unique_id: str,
        system_user_id: str,
    ) -> None:
        exc = GuidedIntegrationError(
            code="test_oauth_state_locale_ru",
            title_ru="Заголовок по-русски",
            title_en="EN title",
            message_ru="Тело ru",
            message_en="EN body",
            links=(),
        )
        async with _oauth_save_raises(
            monkeypatch,
            flows_app,
            service_name=f"guided-locale-{unique_id}",
            system_user_id=system_user_id,
            exc=exc,
            oauth_ui_locale="ru",
        ) as state:
            resp = await flows_client.get(
                "/flows/api/v1/integrations/oauth/callback",
                params={"code": "x", "state": state},
                headers={
                    "Sec-Fetch-Dest": "document",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
        assert resp.status_code == 400
        assert "text/html" in resp.headers.get("content-type", "")
        assert "Заголовок по-русски".encode("utf-8") in resp.content

    @pytest.mark.asyncio
    async def test_returns_html_for_browser_accept_without_sec_fetch_dest(
        self,
        flows_client,
        flows_app,
        monkeypatch: pytest.MonkeyPatch,
        unique_id: str,
        system_user_id: str,
    ) -> None:
        exc = GuidedIntegrationError(
            code="test_oauth_guided_html_accept",
            title_ru="RU title",
            title_en="EN title",
            message_ru="RU body",
            message_en="EN body",
            links=(
                GuidedIntegrationLink(
                    href="/crm/namespaces",
                    label_ru="Lru",
                    label_en="Len",
                ),
            ),
        )
        async with _oauth_save_raises(
            monkeypatch,
            flows_app,
            service_name=f"guided-accept-{unique_id}",
            system_user_id=system_user_id,
            exc=exc,
        ) as state:
            resp = await flows_client.get(
                "/flows/api/v1/integrations/oauth/callback",
                params={"code": "x", "state": state},
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en",
                },
            )
        assert resp.status_code == 400
        assert "text/html" in resp.headers.get("content-type", "")
        assert b"EN title" in resp.content

    @pytest.mark.asyncio
    async def test_returns_json_when_explicit_application_json_accept(
        self,
        flows_client,
        flows_app,
        monkeypatch: pytest.MonkeyPatch,
        unique_id: str,
        system_user_id: str,
    ) -> None:
        exc = GuidedIntegrationError(
            code="test_oauth_guided_json_accept",
            title_ru="RU title",
            title_en="EN title",
            message_ru="RU body",
            message_en="EN body",
            links=(
                GuidedIntegrationLink(
                    href="/crm/namespaces",
                    label_ru="Lru",
                    label_en="Len",
                ),
            ),
        )
        async with _oauth_save_raises(
            monkeypatch,
            flows_app,
            service_name=f"guided-json-accept-{unique_id}",
            system_user_id=system_user_id,
            exc=exc,
        ) as state:
            resp = await flows_client.get(
                "/flows/api/v1/integrations/oauth/callback",
                params={"code": "x", "state": state},
                headers={
                    "Accept": "application/json",
                    "Accept-Language": "en",
                },
            )
        assert resp.status_code == 400
        assert resp.headers.get("content-type", "").startswith("application/json")
        assert resp.json()["code"] == "test_oauth_guided_json_accept"

    @pytest.mark.asyncio
    async def test_value_error_returns_html_when_document_navigation(
        self,
        flows_client,
    ) -> None:
        resp = await flows_client.get(
            "/flows/api/v1/integrations/oauth/callback",
            params={"code": "x", "state": "missing-oauth-state"},
            headers={
                "Sec-Fetch-Dest": "document",
                "Accept-Language": "en",
            },
        )
        assert resp.status_code == 400
        assert "text/html" in resp.headers.get("content-type", "")
        assert b"OAuth state is invalid or expired" in resp.content
        assert b"Connection failed" in resp.content
