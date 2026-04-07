"""
Единый OAuth2 flow: start, complete, refresh, get_valid_token.

Заменяет дублированную OAuth-логику в CalendarService и используется
тулами Google Docs, Calendar и любыми будущими интеграциями.
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import urlencode
from uuid import uuid4

from core.config import get_settings
from core.http.client import get_httpx_client
from core.integrations.models import (
    IntegrationCredential,
    IntegrationProvider,
    OAuthProviderConfig,
)
from core.logging import get_logger

if TYPE_CHECKING:
    from core.db.storage import Storage
    from core.integrations.repository import IntegrationCredentialRepository

logger = get_logger(__name__)

OAUTH_STATE_TTL = 600
OAUTH_STATE_PREFIX = "integration_oauth_state"
TOKEN_EXPIRY_BUFFER = timedelta(minutes=2)


class OAuthTokenRefreshError(Exception):
    """Refresh token отозван или невалиден, credential удалён из БД."""


class OAuthService:
    """
    Универсальный OAuth2 сервис для внешних интеграций.

    Тулы и сервисы вызывают его методы ЯВНО:
    - build_auth_url() — получить URL для авторизации пользователя
    - complete_oauth() — обменять code на токены после callback
    - get_valid_token() — получить credential из БД с auto-refresh
    - refresh_token() — принудительный refresh
    """

    def __init__(
        self,
        repository: IntegrationCredentialRepository,
        storage: Storage,
    ) -> None:
        self._repository = repository
        self._storage = storage

    def get_provider_config(self, provider: IntegrationProvider | str) -> OAuthProviderConfig:
        settings = get_settings()
        provider_key = provider.value if hasattr(provider, "value") else str(provider)
        auth_provider = settings.auth.providers.get(provider_key)
        if auth_provider is None or not auth_provider.enabled:
            raise ValueError(f"OAuth provider '{provider_key}' is disabled or not configured")
        if not auth_provider.client_id:
            raise ValueError(f"OAuth provider '{provider_key}': client_id is required")
        if not auth_provider.client_secret:
            raise ValueError(f"OAuth provider '{provider_key}': client_secret is required")
        if not auth_provider.auth_url:
            raise ValueError(f"OAuth provider '{provider_key}': auth_url is required")
        if not auth_provider.token_url:
            raise ValueError(f"OAuth provider '{provider_key}': token_url is required")
        return OAuthProviderConfig(
            provider=provider,
            client_id=auth_provider.client_id,
            client_secret=auth_provider.client_secret,
            auth_url=auth_provider.auth_url,
            token_url=auth_provider.token_url,
        )

    async def build_auth_url(
        self,
        *,
        provider: IntegrationProvider,
        service: str,
        scopes: list[str],
        user_id: str,
        company_id: str,
        redirect_uri: str | None = None,
        return_path: str = "/",
        flow_context: dict[str, Any] | None = None,
    ) -> str:
        """
        Генерирует OAuth authorization URL.

        State сохраняется в PostgreSQL Storage (force_global, TTL 600s).
        Если redirect_uri не указан, используется дефолтный callback интеграций.

        flow_context (если передан) содержит идентификаторы flow-сессии
        (flow_id, session_id, task_id, context_id, skill_id, channel, context_data)
        для auto-resume после OAuth callback.
        """
        if not return_path.startswith("/") or return_path.startswith("//"):
            raise ValueError("return_path must start with single '/'")

        oauth_config = self.get_provider_config(provider)

        if redirect_uri is None:
            settings = get_settings()
            base_url = settings.server.get_service_url()
            redirect_uri = f"{base_url}/api/v1/integrations/oauth/callback"

        state_token = secrets.token_urlsafe(32)
        state_key = f"{OAUTH_STATE_PREFIX}:{state_token}"
        state_payload: dict[str, Any] = {
            "provider": provider.value,
            "service": service,
            "user_id": user_id,
            "company_id": company_id,
            "redirect_uri": redirect_uri,
            "return_path": return_path,
            "scopes": " ".join(scopes),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if flow_context is not None:
            state_payload["flow_context"] = flow_context
        await self._storage.set(
            key=state_key,
            value=json.dumps(state_payload),
            ttl=OAUTH_STATE_TTL,
            force_global=True,
        )
        query = urlencode(
            {
                "client_id": oauth_config.client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": " ".join(scopes),
                "state": state_token,
                "access_type": "offline",
                "prompt": "consent",
                "include_granted_scopes": "true",
            }
        )
        logger.info(
            "OAuth auth URL built: provider=%s service=%s user=%s company=%s",
            provider.value, service, user_id, company_id,
        )
        return f"{oauth_config.auth_url}?{query}"

    async def complete_oauth(
        self,
        *,
        state_token: str,
        code: str,
    ) -> tuple[IntegrationCredential, str, dict[str, Any] | None]:
        """
        Обменивает authorization code на токены и сохраняет credential.

        Returns:
            (credential, return_path, flow_context)
            flow_context — None если OAuth инициирован без привязки к flow.
        """
        state_key = f"{OAUTH_STATE_PREFIX}:{state_token}"
        raw_state = await self._storage.get(key=state_key, force_global=True)
        if raw_state is None:
            raise ValueError("OAuth state is invalid or expired")
        await self._storage.delete(key=state_key, force_global=True)

        state_payload = json.loads(raw_state)
        if not isinstance(state_payload, dict):
            raise ValueError("OAuth state payload is invalid")

        provider_str = state_payload.get("provider")
        if not isinstance(provider_str, str) or provider_str == "":
            raise ValueError("OAuth state provider is required")
        provider = IntegrationProvider(provider_str)

        service = state_payload.get("service")
        if not isinstance(service, str) or service == "":
            raise ValueError("OAuth state service is required")
        user_id = state_payload.get("user_id")
        if not isinstance(user_id, str) or user_id == "":
            raise ValueError("OAuth state user_id is required")
        company_id = state_payload.get("company_id")
        if not isinstance(company_id, str) or company_id == "":
            raise ValueError("OAuth state company_id is required")
        redirect_uri = state_payload.get("redirect_uri")
        if not isinstance(redirect_uri, str) or redirect_uri == "":
            raise ValueError("OAuth state redirect_uri is required")
        return_path = state_payload.get("return_path")
        if not isinstance(return_path, str) or not return_path.startswith("/") or return_path.startswith("//"):
            raise ValueError("OAuth state return_path is invalid")
        scopes = state_payload.get("scopes", "")
        flow_context_raw = state_payload.get("flow_context")
        flow_context = flow_context_raw if isinstance(flow_context_raw, dict) else None

        oauth_config = self.get_provider_config(provider)
        async with get_httpx_client(timeout=30.0) as client:
            token_response = await client.post(
                oauth_config.token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": oauth_config.client_id,
                    "client_secret": oauth_config.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if token_response.status_code >= 400:
                logger.error(
                    "OAuth token exchange failed: provider=%s service=%s status=%d body=%s",
                    provider_str, service, token_response.status_code,
                    token_response.text[:500],
                )
            token_response.raise_for_status()
            token_payload = token_response.json()

        access_token = token_payload.get("access_token")
        if not isinstance(access_token, str) or access_token == "":
            raise ValueError("OAuth response missing access_token")
        refresh_token = token_payload.get("refresh_token")
        if not isinstance(refresh_token, str) or refresh_token == "":
            raise ValueError("OAuth response missing refresh_token")

        expires_at = None
        expires_in = token_payload.get("expires_in")
        if isinstance(expires_in, int) and expires_in > 0:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        scope = token_payload.get("scope")
        token_type = token_payload.get("token_type")

        now = datetime.now(timezone.utc)
        credential = IntegrationCredential(
            credential_id=uuid4().hex,
            company_id=company_id,
            user_id=user_id,
            provider=provider,
            service=service,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            scope=scope if isinstance(scope, str) else scopes if scopes else None,
            token_type=token_type if isinstance(token_type, str) else "Bearer",
            metadata={},
            created_at=now,
            updated_at=now,
        )

        existing = await self._repository.get_by_user_provider_service(
            company_id=company_id,
            user_id=user_id,
            provider=provider,
            service=service,
        )
        if existing:
            credential = credential.model_copy(
                update={
                    "credential_id": existing.credential_id,
                    "metadata": existing.metadata,
                    "created_at": existing.created_at,
                }
            )

        await self._repository.upsert(credential)
        logger.info(
            "OAuth credential saved: provider=%s service=%s user=%s company=%s",
            provider.value, service, user_id, company_id,
        )
        return credential, return_path, flow_context

    async def refresh_token(
        self,
        credential: IntegrationCredential,
    ) -> IntegrationCredential:
        """
        Обновляет access_token через refresh_token.

        При invalid_grant удаляет credential и бросает OAuthTokenRefreshError.
        """
        if not credential.refresh_token:
            logger.warning(
                "OAuth refresh impossible (no refresh_token), deleting credential: "
                "provider=%s service=%s user=%s",
                credential.provider, credential.service, credential.user_id,
            )
            await self._repository.delete_by_user_provider_service(
                company_id=credential.company_id,
                user_id=credential.user_id,
                provider=credential.provider,
                service=credential.service,
            )
            raise OAuthTokenRefreshError(
                f"Missing refresh_token: provider={credential.provider}, "
                f"service={credential.service}, user={credential.user_id}"
            )

        oauth_config = self.get_provider_config(credential.provider)
        async with get_httpx_client(timeout=30.0) as client:
            response = await client.post(
                oauth_config.token_url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": credential.refresh_token,
                    "client_id": oauth_config.client_id,
                    "client_secret": oauth_config.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if response.status_code >= 400:
            payload = {}
            content_type = response.headers.get("content-type", "")
            if content_type.startswith("application/json"):
                payload = response.json()
            oauth_error = payload.get("error") if isinstance(payload, dict) else None
            oauth_error_desc = payload.get("error_description") if isinstance(payload, dict) else None

            if oauth_error == "invalid_grant":
                logger.warning(
                    "OAuth refresh invalid_grant, deleting credential: "
                    "provider=%s service=%s user=%s desc=%s",
                    credential.provider, credential.service, credential.user_id,
                    oauth_error_desc,
                )
                await self._repository.delete_by_user_provider_service(
                    company_id=credential.company_id,
                    user_id=credential.user_id,
                    provider=credential.provider,
                    service=credential.service,
                )
                reason = f"invalid_grant:{oauth_error_desc}" if oauth_error_desc else "invalid_grant"
                raise OAuthTokenRefreshError(
                    f"Token refresh revoked: provider={credential.provider}, "
                    f"service={credential.service}, user={credential.user_id}, reason={reason}"
                )
            raise RuntimeError(
                f"Token refresh failed: provider={credential.provider}, "
                f"service={credential.service}, status={response.status_code}, "
                f"error={oauth_error}, description={oauth_error_desc}"
            )

        token_payload = response.json()
        access_token = token_payload.get("access_token")
        if not isinstance(access_token, str) or access_token == "":
            raise ValueError("Token refresh response missing access_token")

        expires_at = None
        expires_in = token_payload.get("expires_in")
        if isinstance(expires_in, int) and expires_in > 0:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        new_refresh = token_payload.get("refresh_token")
        if not isinstance(new_refresh, str) or new_refresh == "":
            new_refresh = credential.refresh_token

        token_type = token_payload.get("token_type")
        scope = token_payload.get("scope")

        refreshed = credential.model_copy(
            update={
                "access_token": access_token,
                "refresh_token": new_refresh,
                "expires_at": expires_at,
                "token_type": token_type if isinstance(token_type, str) else credential.token_type,
                "scope": scope if isinstance(scope, str) else credential.scope,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        await self._repository.upsert(refreshed)
        return refreshed

    async def get_valid_token(
        self,
        *,
        company_id: str,
        user_id: str,
        provider: IntegrationProvider,
        service: str,
    ) -> Optional[IntegrationCredential]:
        """
        Получает credential из БД. Если expired — auto-refresh.

        Returns:
            IntegrationCredential с актуальным access_token или None если нет записи.

        Raises:
            OAuthTokenRefreshError: при отозванном refresh_token (credential удалён).
        """
        credential = await self._repository.get_by_user_provider_service(
            company_id=company_id,
            user_id=user_id,
            provider=provider,
            service=service,
        )
        if credential is None:
            return None

        if credential.is_expired() or self._is_about_to_expire(credential):
            credential = await self.refresh_token(credential)
            logger.info(
                "OAuth token auto-refreshed: provider=%s service=%s user=%s",
                provider, service, user_id,
            )

        return credential

    @staticmethod
    def _is_about_to_expire(credential: IntegrationCredential) -> bool:
        if credential.expires_at is None:
            return False
        return credential.expires_at <= datetime.now(timezone.utc) + TOKEN_EXPIRY_BUFFER
