"""resolve_apns_credentials: push + auth.providers.apple."""

from core.config import BaseSettings
from core.config.models import AuthConfig, AuthProviderConfig, PushConfig
from core.push.apns_credentials import resolve_apns_credentials


def _settings(
    push: dict[str, str | bool | None],
    apple: dict[str, str] | None = None,
) -> BaseSettings:
    providers: dict[str, AuthProviderConfig] = {}
    if apple is not None:
        providers["apple"] = AuthProviderConfig(**apple)
    return BaseSettings(
        auth=AuthConfig(providers=providers),
        push=PushConfig(**push),
    )


def test_requires_bundle_id():
    assert resolve_apns_credentials(_settings({"apns_bundle_id": None})) is None


def test_from_push_only():
    s = _settings(
        {
            "apns_bundle_id": "ru.app.test",
            "apns_team_id": "T1",
            "apns_key_id": "K1",
            "apns_private_key": "-----BEGIN PRIVATE KEY-----\nABC\n-----END PRIVATE KEY-----",
            "apns_use_sandbox": True,
        }
    )
    r = resolve_apns_credentials(s)
    assert r is not None
    assert r.bundle_id == "ru.app.test"
    assert r.team_id == "T1"
    assert r.key_id == "K1"
    assert "BEGIN PRIVATE" in r.private_key_pem
    assert r.use_sandbox is True


def test_uses_apple_provider_team_key_pem():
    s = _settings(
        {
            "apns_bundle_id": "ru.app.test",
            "apns_team_id": None,
            "apns_key_id": None,
            "apns_private_key": None,
            "apns_use_sandbox": False,
        },
        apple={
            "apple_team_id": "TEAMX",
            "apple_key_id": "KEYX",
            "apple_private_key": "-----BEGIN PRIVATE KEY-----\nXYZ\n-----END PRIVATE KEY-----",
        },
    )
    r = resolve_apns_credentials(s)
    assert r is not None
    assert r.team_id == "TEAMX"
    assert r.key_id == "KEYX"
    assert "XYZ" in r.private_key_pem


def test_push_overrides_apple():
    s = _settings(
        {
            "apns_bundle_id": "b",
            "apns_team_id": "T_push",
            "apns_key_id": "K_push",
            "apns_private_key": "PEM_PUSH",
            "apns_use_sandbox": False,
        },
        apple={
            "apple_team_id": "T_apple",
            "apple_key_id": "K_apple",
            "apple_private_key": "PEM_APPLE",
        },
    )
    r = resolve_apns_credentials(s)
    assert r.team_id == "T_push"
    assert r.private_key_pem == "PEM_PUSH"
