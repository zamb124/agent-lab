"""resolve_fcm_credentials: parsing service account JSON и push.fcm_project_id."""

import json
from types import SimpleNamespace

from core.push.fcm_credentials import resolve_fcm_credentials


def _settings(push: dict) -> SimpleNamespace:
    push_ns = SimpleNamespace(**push)
    return SimpleNamespace(push=push_ns)


_SERVICE_ACCOUNT = {
    "type": "service_account",
    "project_id": "humanitec-app",
    "client_email": "firebase-adminsdk-x@humanitec-app.iam.gserviceaccount.com",
    "private_key": "-----BEGIN PRIVATE KEY-----\nABC\n-----END PRIVATE KEY-----\n",
    "token_uri": "https://oauth2.googleapis.com/token",
}


def test_returns_none_when_credentials_missing():
    assert (
        resolve_fcm_credentials(
            _settings({"fcm_credentials_json": None, "fcm_project_id": None})
        )
        is None
    )


def test_resolves_from_dict():
    s = _settings(
        {
            "fcm_credentials_json": _SERVICE_ACCOUNT,
            "fcm_project_id": None,
        }
    )
    r = resolve_fcm_credentials(s)
    assert r is not None
    assert r.project_id == "humanitec-app"
    assert r.client_email == _SERVICE_ACCOUNT["client_email"]
    assert "BEGIN PRIVATE" in r.private_key_pem
    assert r.token_uri == "https://oauth2.googleapis.com/token"


def test_resolves_from_json_string():
    s = _settings(
        {
            "fcm_credentials_json": json.dumps(_SERVICE_ACCOUNT),
            "fcm_project_id": None,
        }
    )
    r = resolve_fcm_credentials(s)
    assert r is not None
    assert r.project_id == "humanitec-app"


def test_push_project_id_overrides_service_account():
    s = _settings(
        {
            "fcm_credentials_json": _SERVICE_ACCOUNT,
            "fcm_project_id": "humanitec-app-override",
        }
    )
    r = resolve_fcm_credentials(s)
    assert r is not None
    assert r.project_id == "humanitec-app-override"


def test_returns_none_when_required_field_missing():
    incomplete = {**_SERVICE_ACCOUNT, "client_email": ""}
    s = _settings(
        {
            "fcm_credentials_json": incomplete,
            "fcm_project_id": None,
        }
    )
    assert resolve_fcm_credentials(s) is None
