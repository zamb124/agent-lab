"""LiveKit public URL host-aware для multi-brand apex."""

from __future__ import annotations

import pytest

from apps.sync.services.call_service import livekit_public_url
from core.config import get_settings
from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.identity_models import User


@pytest.mark.parametrize("host,expected_url", [
    ("linnex.io", "wss://livekit.linnex.io"),
    ("linnex.io", "wss://livekit.linnex.io"),
    ("acme.linnex.io", "wss://livekit.linnex.io"),
])
def test_livekit_public_url_from_context_host(host: str, expected_url: str) -> None:
    set_context(
        Context(
            user=User(user_id="livekit_brand_user", name="LiveKit Brand User"),
            host=host,
            session_id="test_session",
            channel="test",
            metadata={},
        )
    )
    try:
        assert livekit_public_url(get_settings()) == expected_url
    finally:
        clear_context()


def test_livekit_public_url_unknown_host_uses_configured() -> None:
    settings = get_settings()
    configured = settings.calls.livekit_public_url or settings.calls.livekit_url
    set_context(
        Context(
            user=User(user_id="livekit_brand_user", name="LiveKit Brand User"),
            host="evil.example.com",
            session_id="test_session",
            channel="test",
            metadata={},
        )
    )
    try:
        assert livekit_public_url(settings) == str(configured).strip()
    finally:
        clear_context()
