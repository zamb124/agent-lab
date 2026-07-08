"""LiveKit public URL host-aware для multi-brand apex."""

from __future__ import annotations

import pytest

from core.config import get_settings
from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.identity_models import User


@pytest.mark.parametrize("host,expected_url", [
    ("humanitec.ru", "wss://livekit.humanitec.ru"),
    ("linnex.io", "wss://livekit.linnex.io"),
    ("acme.linnex.io", "wss://livekit.linnex.io"),
])
def test_livekit_public_url_from_context_host(host: str, expected_url: str) -> None:
    from apps.sync.realtime.operations import _livekit_public_url

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
        assert _livekit_public_url(get_settings()) == expected_url
    finally:
        clear_context()
