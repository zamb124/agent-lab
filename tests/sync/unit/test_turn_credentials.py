"""Unit-тесты генерации TURN credentials.

Чистая математика HMAC-SHA1 — никаких внешних зависимостей.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

import pytest

from core.calls.turn import generate_turn_credentials


def test_credentials_structure() -> None:
    creds = generate_turn_credentials(
        user_id="user123",
        turn_host="turn.example.com",
        turn_port=3478,
        turn_secret="mysecret",
        ttl=3600,
    )
    assert creds.username.endswith(":user123")
    assert len(creds.credential) > 0
    assert creds.ttl == 3600
    assert len(creds.uris) == 3
    assert any("stun:" in u for u in creds.uris)
    assert any("turn:" in u and "udp" in u for u in creds.uris)
    assert any("turn:" in u and "tcp" in u for u in creds.uris)


def test_credential_hmac_correct() -> None:
    secret = "supersecret"
    creds = generate_turn_credentials(
        user_id="alice",
        turn_host="turn.test",
        turn_port=3478,
        turn_secret=secret,
        ttl=86400,
    )
    username = creds.username
    expected_raw = hmac.new(
        secret.encode("utf-8"),
        username.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    expected = base64.b64encode(expected_raw).decode("utf-8")
    assert creds.credential == expected


def test_username_expires_in_future() -> None:
    before = int(time.time())
    creds = generate_turn_credentials(
        user_id="bob",
        turn_host="turn.test",
        turn_port=3478,
        turn_secret="secret",
        ttl=3600,
    )
    expires = int(creds.username.split(":")[0])
    assert expires >= before + 3600 - 2
    assert expires <= before + 3600 + 2


def test_uris_contain_host_and_port() -> None:
    creds = generate_turn_credentials(
        user_id="u",
        turn_host="coturn.myserver.io",
        turn_port=5349,
        turn_secret="s",
        ttl=60,
    )
    for uri in creds.uris:
        assert "coturn.myserver.io:5349" in uri


def test_missing_turn_host_raises() -> None:
    with pytest.raises(ValueError, match="turn_host"):
        generate_turn_credentials(
            user_id="u",
            turn_host="",
            turn_port=3478,
            turn_secret="s",
            ttl=60,
        )


def test_missing_turn_secret_raises() -> None:
    with pytest.raises(ValueError, match="turn_secret"):
        generate_turn_credentials(
            user_id="u",
            turn_host="turn.test",
            turn_port=3478,
            turn_secret="",
            ttl=60,
        )
