"""
Тесты OAuthService и IntegrationCredentialRepository.

Используются реальные PostgreSQL (shared БД через conftest) для repository,
и mock-storage + mock-HTTP для OAuthService.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest

from core.integrations.models import IntegrationCredential, IntegrationProvider, OAuthProviderConfig
from core.integrations.oauth_service import OAuthService, OAuthTokenRefreshError
from core.integrations.providers.amocrm import parse_amocrm_subdomain_from_referer
from core.integrations.repository import IntegrationCredentialRepository


class FakeHttpClient:
    """Фейковый HTTP-клиент, возвращает заданный ответ на POST."""

    def __init__(self, responses: list[httpx.Response]) -> None:
        self._responses = list(responses)
        self._call_index = 0

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        if self._call_index >= len(self._responses):
            raise RuntimeError(f"FakeHttpClient: no response for call #{self._call_index}")
        resp = self._responses[self._call_index]
        self._call_index += 1
        return resp


@asynccontextmanager
async def _fake_http_factory(responses: list[httpx.Response], **kwargs: Any):
    """Заменяет get_httpx_client: возвращает FakeHttpClient."""
    yield FakeHttpClient(responses)


_FAKE_REQUEST = httpx.Request("POST", "https://oauth2.googleapis.com/token")


def _make_token_response(
    access_token: str = "new-access",
    refresh_token: str = "new-refresh",
    expires_in: int = 3600,
    *,
    status_code: int = 200,
    extra: dict[str, Any] | None = None,
) -> httpx.Response:
    body: dict[str, Any] = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": expires_in,
        "token_type": "Bearer",
        "scope": "https://www.googleapis.com/auth/documents",
    }
    if extra:
        body.update(extra)
    return httpx.Response(status_code=status_code, json=body, request=_FAKE_REQUEST)


def _make_error_response(
    error: str,
    description: str = "",
    status_code: int = 400,
) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json={"error": error, "error_description": description},
        request=_FAKE_REQUEST,
    )


def _patch_auth_config(monkeypatch) -> None:
    """Подставляет OAuth-конфиг Google в настройки для тестов."""
    from core.config import get_settings
    from core.config.models import AuthConfig, AuthProviderConfig

    settings = get_settings()
    auth = AuthConfig(
        providers={
            "google": AuthProviderConfig(
                client_id="test-client-id",
                client_secret="test-secret",
                auth_url="https://accounts.google.com/o/oauth2/v2/auth",
                token_url="https://oauth2.googleapis.com/token",
            ),
        },
    )
    monkeypatch.setattr(settings, "auth", auth)


class FakeStorage:
    """Мок Storage для OAuth state (get/set/delete с force_global)."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    async def get(self, key: str, force_global: bool = False) -> str | None:
        return self._data.get(key)

    async def set(self, key: str, value: str, ttl: int | None = None, force_global: bool = False) -> bool:
        self._data[key] = value
        return True

    async def delete(self, key: str, force_global: bool = False) -> bool:
        return self._data.pop(key, None) is not None


@pytest.fixture()
def credential_repository(app) -> IntegrationCredentialRepository:
    from core.config import get_settings
    settings = get_settings()
    return IntegrationCredentialRepository(db_url=settings.database.shared_url)


@pytest.fixture()
def fake_storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture()
def oauth_service(credential_repository, fake_storage) -> OAuthService:
    return OAuthService(repository=credential_repository, storage=fake_storage)


class TestIntegrationCredentialRepository:
    @pytest.mark.asyncio
    async def test_upsert_and_get(self, credential_repository: IntegrationCredentialRepository, unique_id: str) -> None:
        now = datetime.now(timezone.utc)
        cred = IntegrationCredential(
            credential_id=f"cred-{unique_id}",
            company_id=f"company-{unique_id}",
            user_id=f"user-{unique_id}",
            provider=IntegrationProvider.GOOGLE,
            service="docs",
            access_token="access-123",
            refresh_token="refresh-456",
            expires_at=now + timedelta(hours=1),
            scope="https://www.googleapis.com/auth/documents",
            token_type="Bearer",
            metadata={"key": "value"},
            created_at=now,
            updated_at=now,
        )
        await credential_repository.upsert(cred)

        loaded = await credential_repository.get_by_user_provider_service(
            company_id=cred.company_id,
            user_id=cred.user_id,
            provider=IntegrationProvider.GOOGLE,
            service="docs",
        )
        assert loaded is not None
        assert loaded.credential_id == cred.credential_id
        assert loaded.access_token == "access-123"
        assert loaded.metadata == {"key": "value"}

    @pytest.mark.asyncio
    async def test_upsert_updates_existing(self, credential_repository: IntegrationCredentialRepository, unique_id: str) -> None:
        now = datetime.now(timezone.utc)
        cred = IntegrationCredential(
            credential_id=f"cred-{unique_id}",
            company_id=f"company-{unique_id}",
            user_id=f"user-{unique_id}",
            provider=IntegrationProvider.GOOGLE,
            service="calendar",
            access_token="old-token",
            created_at=now,
            updated_at=now,
        )
        await credential_repository.upsert(cred)

        updated = cred.model_copy(update={
            "access_token": "new-token",
            "updated_at": datetime.now(timezone.utc),
        })
        await credential_repository.upsert(updated)

        loaded = await credential_repository.get_by_user_provider_service(
            company_id=cred.company_id,
            user_id=cred.user_id,
            provider=IntegrationProvider.GOOGLE,
            service="calendar",
        )
        assert loaded.access_token == "new-token"

    @pytest.mark.asyncio
    async def test_list_by_user(self, credential_repository: IntegrationCredentialRepository, unique_id: str) -> None:
        now = datetime.now(timezone.utc)
        company_id = f"company-{unique_id}"
        user_id = f"user-{unique_id}"

        for svc in ("calendar", "docs"):
            await credential_repository.upsert(IntegrationCredential(
                credential_id=f"cred-{unique_id}-{svc}",
                company_id=company_id,
                user_id=user_id,
                provider=IntegrationProvider.GOOGLE,
                service=svc,
                access_token=f"token-{svc}",
                created_at=now,
                updated_at=now,
            ))

        items = await credential_repository.list_by_user(company_id=company_id, user_id=user_id)
        assert len(items) == 2
        services = {c.service for c in items}
        assert services == {"calendar", "docs"}

    @pytest.mark.asyncio
    async def test_delete_by_user_provider_service(self, credential_repository: IntegrationCredentialRepository, unique_id: str) -> None:
        now = datetime.now(timezone.utc)
        await credential_repository.upsert(IntegrationCredential(
            credential_id=f"cred-del-{unique_id}",
            company_id=f"company-{unique_id}",
            user_id=f"user-{unique_id}",
            provider=IntegrationProvider.GOOGLE,
            service="docs",
            access_token="token",
            created_at=now,
            updated_at=now,
        ))

        deleted = await credential_repository.delete_by_user_provider_service(
            company_id=f"company-{unique_id}",
            user_id=f"user-{unique_id}",
            provider=IntegrationProvider.GOOGLE,
            service="docs",
        )
        assert deleted is True

        loaded = await credential_repository.get_by_user_provider_service(
            company_id=f"company-{unique_id}",
            user_id=f"user-{unique_id}",
            provider=IntegrationProvider.GOOGLE,
            service="docs",
        )
        assert loaded is None

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, credential_repository: IntegrationCredentialRepository, unique_id: str) -> None:
        loaded = await credential_repository.get_by_user_provider_service(
            company_id=f"nonexistent-{unique_id}",
            user_id=f"nonexistent-{unique_id}",
            provider=IntegrationProvider.GOOGLE,
            service="docs",
        )
        assert loaded is None


class TestOAuthService:
    @pytest.mark.asyncio
    async def test_get_valid_token_returns_none_when_no_credential(
        self,
        oauth_service: OAuthService,
        unique_id: str,
    ) -> None:
        result = await oauth_service.get_valid_token(
            company_id=f"company-{unique_id}",
            user_id=f"user-{unique_id}",
            provider=IntegrationProvider.GOOGLE,
            service="docs",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_get_valid_token_returns_existing(
        self,
        oauth_service: OAuthService,
        credential_repository: IntegrationCredentialRepository,
        unique_id: str,
    ) -> None:
        now = datetime.now(timezone.utc)
        cred = IntegrationCredential(
            credential_id=f"cred-valid-{unique_id}",
            company_id=f"company-{unique_id}",
            user_id=f"user-{unique_id}",
            provider=IntegrationProvider.GOOGLE,
            service="docs",
            access_token="valid-token",
            expires_at=now + timedelta(hours=1),
            created_at=now,
            updated_at=now,
        )
        await credential_repository.upsert(cred)

        result = await oauth_service.get_valid_token(
            company_id=cred.company_id,
            user_id=cred.user_id,
            provider=IntegrationProvider.GOOGLE,
            service="docs",
        )
        assert result is not None
        assert result.access_token == "valid-token"

    @pytest.mark.asyncio
    async def test_build_auth_url_stores_state(
        self,
        oauth_service: OAuthService,
        fake_storage: FakeStorage,
        unique_id: str,
        monkeypatch,
    ) -> None:
        _patch_auth_config(monkeypatch)

        url = await oauth_service.build_auth_url(
            provider=IntegrationProvider.GOOGLE,
            service="docs",
            scopes=["https://www.googleapis.com/auth/documents"],
            user_id=f"user-{unique_id}",
            company_id=f"company-{unique_id}",
            redirect_uri="http://localhost/callback",
        )

        assert "accounts.google.com" in url
        assert "test-client-id" in url

        stored_keys = [k for k in fake_storage._data if k.startswith("integration_oauth_state:")]
        assert len(stored_keys) == 1

        state_data = json.loads(fake_storage._data[stored_keys[0]])
        assert state_data["provider"] == "google"
        assert state_data["service"] == "docs"
        assert state_data["user_id"] == f"user-{unique_id}"

    @pytest.mark.asyncio
    async def test_build_auth_url_default_redirect_uri_includes_service_path(
        self,
        oauth_service: OAuthService,
        fake_storage: FakeStorage,
        unique_id: str,
        monkeypatch,
    ) -> None:
        """Callback смонтирован как /{server.name}/api/v1/integrations/... (см. core.app.factory)."""
        from urllib.parse import parse_qs, urlparse

        from core.config import get_settings

        _patch_auth_config(monkeypatch)

        url = await oauth_service.build_auth_url(
            provider=IntegrationProvider.GOOGLE,
            service="docs",
            scopes=["https://www.googleapis.com/auth/documents"],
            user_id=f"user-{unique_id}",
            company_id=f"company-{unique_id}",
        )

        redirect_uri = parse_qs(urlparse(url).query)["redirect_uri"][0]
        segment = get_settings().server.name
        assert f"/{segment}/api/v1/integrations/oauth/callback" in redirect_uri

    @pytest.mark.asyncio
    async def test_is_expired(self) -> None:
        now = datetime.now(timezone.utc)
        expired = IntegrationCredential(
            credential_id="test",
            company_id="c",
            user_id="u",
            provider=IntegrationProvider.GOOGLE,
            service="docs",
            access_token="token",
            expires_at=now - timedelta(minutes=5),
            created_at=now,
            updated_at=now,
        )
        assert expired.is_expired() is True

        valid = expired.model_copy(update={"expires_at": now + timedelta(hours=1)})
        assert valid.is_expired() is False

        no_expiry = expired.model_copy(update={"expires_at": None})
        assert no_expiry.is_expired() is False

    @pytest.mark.asyncio
    async def test_complete_oauth_exchanges_code_and_saves_credential(
        self,
        oauth_service: OAuthService,
        fake_storage: FakeStorage,
        credential_repository: IntegrationCredentialRepository,
        unique_id: str,
        monkeypatch,
    ) -> None:
        _patch_auth_config(monkeypatch)

        state_payload = {
            "provider": "google",
            "service": "docs",
            "user_id": f"user-{unique_id}",
            "company_id": f"company-{unique_id}",
            "redirect_uri": "http://localhost/callback",
            "return_path": "/chat",
            "scopes": "https://www.googleapis.com/auth/documents",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        state_token = f"state-{unique_id}"
        await fake_storage.set(
            key=f"integration_oauth_state:{state_token}",
            value=json.dumps(state_payload),
        )

        token_resp = _make_token_response(access_token="acc-123", refresh_token="ref-456")
        monkeypatch.setattr(
            "core.integrations.oauth_service.get_httpx_client",
            lambda **kw: _fake_http_factory([token_resp], **kw),
        )

        credential, return_path, flow_ctx, post_origin = await oauth_service.complete_oauth(
            state_token=state_token,
            code="auth-code-xyz",
        )

        assert credential.access_token == "acc-123"
        assert credential.refresh_token == "ref-456"
        assert credential.provider == IntegrationProvider.GOOGLE
        assert credential.service == "docs"
        assert return_path == "/chat"
        assert flow_ctx is None
        assert post_origin is None

        loaded = await credential_repository.get_by_user_provider_service(
            company_id=f"company-{unique_id}",
            user_id=f"user-{unique_id}",
            provider=IntegrationProvider.GOOGLE,
            service="docs",
        )
        assert loaded is not None
        assert loaded.access_token == "acc-123"

    @pytest.mark.asyncio
    async def test_complete_oauth_with_flow_context(
        self,
        oauth_service: OAuthService,
        fake_storage: FakeStorage,
        unique_id: str,
        monkeypatch,
    ) -> None:
        _patch_auth_config(monkeypatch)

        flow_ctx_input = {"flow_id": "f1", "session_id": "s1"}
        state_payload = {
            "provider": "google",
            "service": "docs",
            "user_id": f"user-{unique_id}",
            "company_id": f"company-{unique_id}",
            "redirect_uri": "http://localhost/callback",
            "return_path": "/",
            "scopes": "",
            "flow_context": flow_ctx_input,
        }
        state_token = f"state-fc-{unique_id}"
        await fake_storage.set(
            key=f"integration_oauth_state:{state_token}",
            value=json.dumps(state_payload),
        )

        token_resp = _make_token_response()
        monkeypatch.setattr(
            "core.integrations.oauth_service.get_httpx_client",
            lambda **kw: _fake_http_factory([token_resp], **kw),
        )

        _, _, flow_ctx_out, post_o = await oauth_service.complete_oauth(
            state_token=state_token, code="code",
        )
        assert flow_ctx_out == flow_ctx_input
        assert post_o is None

    @pytest.mark.asyncio
    async def test_complete_oauth_post_auth_redirect_origin(
        self,
        oauth_service: OAuthService,
        fake_storage: FakeStorage,
        unique_id: str,
        monkeypatch,
    ) -> None:
        from core.config import get_settings

        _patch_auth_config(monkeypatch)
        settings = get_settings()
        monkeypatch.setattr(settings.server, "platform_public_base_url", "http://lvh.me:8002")

        state_payload = {
            "provider": "google",
            "service": "docs",
            "user_id": f"user-{unique_id}",
            "company_id": f"company-{unique_id}",
            "redirect_uri": "http://localhost/callback",
            "return_path": "/crm/spaces/x/integrations",
            "scopes": "",
            "post_auth_redirect_origin": "http://system.lvh.me:8002",
        }
        state_token = f"state-po-{unique_id}"
        await fake_storage.set(
            key=f"integration_oauth_state:{state_token}",
            value=json.dumps(state_payload),
        )

        token_resp = _make_token_response()
        monkeypatch.setattr(
            "core.integrations.oauth_service.get_httpx_client",
            lambda **kw: _fake_http_factory([token_resp], **kw),
        )

        _, _, _, post_origin = await oauth_service.complete_oauth(
            state_token=state_token, code="code",
        )
        assert post_origin == "http://system.lvh.me:8002"

    @pytest.mark.asyncio
    async def test_complete_oauth_expired_state(
        self,
        oauth_service: OAuthService,
        fake_storage: FakeStorage,
        unique_id: str,
    ) -> None:
        with pytest.raises(ValueError, match="invalid or expired"):
            await oauth_service.complete_oauth(
                state_token=f"nonexistent-{unique_id}",
                code="code",
            )

    @pytest.mark.asyncio
    async def test_complete_oauth_missing_refresh_token(
        self,
        oauth_service: OAuthService,
        fake_storage: FakeStorage,
        unique_id: str,
        monkeypatch,
    ) -> None:
        _patch_auth_config(monkeypatch)

        state_payload = {
            "provider": "google",
            "service": "docs",
            "user_id": f"user-{unique_id}",
            "company_id": f"company-{unique_id}",
            "redirect_uri": "http://localhost/callback",
            "return_path": "/",
            "scopes": "",
        }
        state_token = f"state-noref-{unique_id}"
        await fake_storage.set(
            key=f"integration_oauth_state:{state_token}",
            value=json.dumps(state_payload),
        )

        no_refresh_resp = httpx.Response(200, json={
            "access_token": "acc",
            "expires_in": 3600,
            "token_type": "Bearer",
        }, request=_FAKE_REQUEST)
        monkeypatch.setattr(
            "core.integrations.oauth_service.get_httpx_client",
            lambda **kw: _fake_http_factory([no_refresh_resp], **kw),
        )

        with pytest.raises(ValueError, match="missing refresh_token"):
            await oauth_service.complete_oauth(
                state_token=state_token, code="code",
            )

    @pytest.mark.asyncio
    async def test_refresh_token_success(
        self,
        oauth_service: OAuthService,
        credential_repository: IntegrationCredentialRepository,
        unique_id: str,
        monkeypatch,
    ) -> None:
        _patch_auth_config(monkeypatch)

        now = datetime.now(timezone.utc)
        cred = IntegrationCredential(
            credential_id=f"cred-ref-{unique_id}",
            company_id=f"company-{unique_id}",
            user_id=f"user-{unique_id}",
            provider=IntegrationProvider.GOOGLE,
            service="docs",
            access_token="old-access",
            refresh_token="refresh-valid",
            expires_at=now - timedelta(hours=1),
            created_at=now,
            updated_at=now,
        )
        await credential_repository.upsert(cred)

        token_resp = _make_token_response(access_token="refreshed-access")
        monkeypatch.setattr(
            "core.integrations.oauth_service.get_httpx_client",
            lambda **kw: _fake_http_factory([token_resp], **kw),
        )

        refreshed = await oauth_service.refresh_token(cred)
        assert refreshed.access_token == "refreshed-access"

        loaded = await credential_repository.get_by_user_provider_service(
            company_id=cred.company_id,
            user_id=cred.user_id,
            provider=IntegrationProvider.GOOGLE,
            service="docs",
        )
        assert loaded is not None
        assert loaded.access_token == "refreshed-access"

    @pytest.mark.asyncio
    async def test_refresh_token_invalid_grant_deletes_credential(
        self,
        oauth_service: OAuthService,
        credential_repository: IntegrationCredentialRepository,
        unique_id: str,
        monkeypatch,
    ) -> None:
        _patch_auth_config(monkeypatch)

        now = datetime.now(timezone.utc)
        cred = IntegrationCredential(
            credential_id=f"cred-inv-{unique_id}",
            company_id=f"company-{unique_id}",
            user_id=f"user-{unique_id}",
            provider=IntegrationProvider.GOOGLE,
            service="docs",
            access_token="old",
            refresh_token="revoked-refresh",
            expires_at=now - timedelta(hours=1),
            created_at=now,
            updated_at=now,
        )
        await credential_repository.upsert(cred)

        error_resp = _make_error_response("invalid_grant", "Token has been revoked")
        monkeypatch.setattr(
            "core.integrations.oauth_service.get_httpx_client",
            lambda **kw: _fake_http_factory([error_resp], **kw),
        )

        with pytest.raises(OAuthTokenRefreshError, match="invalid_grant"):
            await oauth_service.refresh_token(cred)

        loaded = await credential_repository.get_by_user_provider_service(
            company_id=cred.company_id,
            user_id=cred.user_id,
            provider=IntegrationProvider.GOOGLE,
            service="docs",
        )
        assert loaded is None

    @pytest.mark.asyncio
    async def test_refresh_token_missing_raises_and_deletes(
        self,
        oauth_service: OAuthService,
        credential_repository: IntegrationCredentialRepository,
        unique_id: str,
    ) -> None:
        now = datetime.now(timezone.utc)
        cred = IntegrationCredential(
            credential_id=f"cred-noref-{unique_id}",
            company_id=f"company-{unique_id}",
            user_id=f"user-{unique_id}",
            provider=IntegrationProvider.GOOGLE,
            service="docs",
            access_token="old",
            refresh_token=None,
            expires_at=now - timedelta(hours=1),
            created_at=now,
            updated_at=now,
        )
        await credential_repository.upsert(cred)

        with pytest.raises(OAuthTokenRefreshError, match="Missing refresh_token"):
            await oauth_service.refresh_token(cred)

        loaded = await credential_repository.get_by_user_provider_service(
            company_id=cred.company_id,
            user_id=cred.user_id,
            provider=IntegrationProvider.GOOGLE,
            service="docs",
        )
        assert loaded is None

    @pytest.mark.asyncio
    async def test_get_valid_token_auto_refreshes_expired(
        self,
        oauth_service: OAuthService,
        credential_repository: IntegrationCredentialRepository,
        unique_id: str,
        monkeypatch,
    ) -> None:
        _patch_auth_config(monkeypatch)

        now = datetime.now(timezone.utc)
        cred = IntegrationCredential(
            credential_id=f"cred-exp-{unique_id}",
            company_id=f"company-{unique_id}",
            user_id=f"user-{unique_id}",
            provider=IntegrationProvider.GOOGLE,
            service="docs",
            access_token="expired-access",
            refresh_token="good-refresh",
            expires_at=now - timedelta(minutes=10),
            created_at=now,
            updated_at=now,
        )
        await credential_repository.upsert(cred)

        token_resp = _make_token_response(access_token="fresh-access", refresh_token="good-refresh")
        monkeypatch.setattr(
            "core.integrations.oauth_service.get_httpx_client",
            lambda **kw: _fake_http_factory([token_resp], **kw),
        )

        result = await oauth_service.get_valid_token(
            company_id=cred.company_id,
            user_id=cred.user_id,
            provider=IntegrationProvider.GOOGLE,
            service="docs",
        )
        assert result is not None
        assert result.access_token == "fresh-access"


class TestAmoRefererParse:
    def test_parse_subdomain_amocrm_ru(self) -> None:
        assert parse_amocrm_subdomain_from_referer("foo.amocrm.ru") == "foo"
        assert parse_amocrm_subdomain_from_referer("https://bar.amocrm.ru") == "bar"

    def test_parse_subdomain_kommo(self) -> None:
        assert parse_amocrm_subdomain_from_referer("https://acc.kommo.com") == "acc"

    def test_parse_none_empty(self) -> None:
        assert parse_amocrm_subdomain_from_referer(None) is None
        assert parse_amocrm_subdomain_from_referer("") is None
