"""resolve_fcm_credentials: parsing service account JSON и push.fcm_project_id."""

import json

import pytest

from core.config.models import PushConfig
from core.push.fcm_credentials import resolve_fcm_credentials
from core.types import JsonObject, parse_json_object


def _push_config(fcm_credentials_json: str | JsonObject | None, fcm_project_id: str | None) -> PushConfig:
    return PushConfig(
        fcm_credentials_json=fcm_credentials_json,
        fcm_project_id=fcm_project_id,
    )


_SERVICE_ACCOUNT: JsonObject = parse_json_object(
    json.dumps(
        {
            "type": "service_account",
            "project_id": "humanitec-app",
            "client_email": "firebase-adminsdk-x@humanitec-app.iam.gserviceaccount.com",
            "private_key": "-----BEGIN PRIVATE KEY-----\nABC\n-----END PRIVATE KEY-----\n",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    )
)


def test_returns_none_when_credentials_missing():
    assert resolve_fcm_credentials(_push_config(None, None)) is None


def test_resolves_from_dict():
    push = _push_config(_SERVICE_ACCOUNT, None)
    r = resolve_fcm_credentials(push)
    assert r is not None
    assert r.project_id == "humanitec-app"
    assert r.client_email == _SERVICE_ACCOUNT["client_email"]
    assert "BEGIN PRIVATE" in r.private_key_pem
    assert r.token_uri == "https://oauth2.googleapis.com/token"


def test_resolves_from_json_string():
    push = _push_config(json.dumps(_SERVICE_ACCOUNT), None)
    r = resolve_fcm_credentials(push)
    assert r is not None
    assert r.project_id == "humanitec-app"


def test_push_project_id_overrides_service_account():
    push = _push_config(_SERVICE_ACCOUNT, "humanitec-app-override")
    r = resolve_fcm_credentials(push)
    assert r is not None
    assert r.project_id == "humanitec-app-override"


def test_raises_when_required_field_missing():
    incomplete = {**_SERVICE_ACCOUNT, "client_email": ""}
    with pytest.raises(ValueError, match="client_email"):
        resolve_fcm_credentials(_push_config(incomplete, None))
