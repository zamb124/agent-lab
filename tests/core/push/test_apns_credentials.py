"""resolve_apns_credentials: push + fallback на auth.providers.apple."""

from types import SimpleNamespace

from core.push.apns_credentials import resolve_apns_credentials


def _settings(push: dict, apple: dict | None = None) -> SimpleNamespace:
    apple_cfg = None
    if apple is not None:
        apple_cfg = SimpleNamespace(**apple)
    providers = {"apple": apple_cfg} if apple_cfg is not None else {}
    auth = SimpleNamespace(providers=providers)
    push_ns = SimpleNamespace(**push)
    return SimpleNamespace(push=push_ns, auth=auth)


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


def test_fallback_apple_team_key_pem():
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
