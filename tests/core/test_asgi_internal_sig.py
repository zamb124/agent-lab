"""ASGI ServiceClient patch must verify internal context HMAC under target settings."""

from __future__ import annotations

import pytest

from core.clients.secrets_client import SecretsClient
from core.clients.service_client import ServiceClient
from core.config import get_settings
from core.config.models import AuthProviderConfig
from core.secrets.models import VariableResolveRequest


@pytest.mark.asyncio
async def test_asgi_internal_headers_survive_jwt_secret_monkeypatch(
    mock_context,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Caller may monkeypatch auth (e.g. OAuth providers) including jwt_secret_key.
    ASGI patch switches to app.state.settings for the target service; signature
    must still verify (re-sign after settings switch).
    """
    settings = get_settings()
    auth = settings.auth.model_copy(deep=True)
    auth.jwt_secret_key = "test-secret-key-32-bytes-minimum-!"
    auth.providers = {
        **auth.providers,
        "google": AuthProviderConfig(
            client_id="test-client-id",
            client_secret="test-secret",
            auth_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
        ),
    }
    monkeypatch.setattr(settings, "auth", auth)

    secrets = SecretsClient(ServiceClient())
    resolved = await secrets.resolve_bundle(VariableResolveRequest())
    assert isinstance(resolved.items, list)
