"""
Тесты OAuthService и IntegrationCredentialRepository.

Используются реальные PostgreSQL (shared БД через conftest) для repository,
и mock-storage + mock-HTTP для OAuthService.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from core.integrations.models import IntegrationCredential, IntegrationProvider, OAuthProviderConfig
from core.integrations.oauth_service import OAuthService, OAuthTokenRefreshError
from core.integrations.repository import IntegrationCredentialRepository


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
        from core.config import models as config_models
        from core.config.base import BaseSettings

        monkeypatch.setattr(
            BaseSettings, "auth",
            property(lambda self: config_models.AuthConfig(
                providers={
                    "google": config_models.AuthProviderConfig(
                        client_id="test-client-id",
                        client_secret="test-secret",
                        auth_url="https://accounts.google.com/o/oauth2/v2/auth",
                        token_url="https://oauth2.googleapis.com/token",
                    ),
                },
            )),
        )

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
