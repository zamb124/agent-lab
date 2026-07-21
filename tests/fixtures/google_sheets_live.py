"""Shared live Google Sheets credentials (OAuth token OR Service Account)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from core.clients.google_sheets_client import GoogleSheetsClient
from core.clients.google_workspace_auth import GoogleAuthMaterial
from core.config import get_settings
from core.types import require_json_object

_CREDS_PATH = Path(__file__).resolve().parents[2] / "google_service_account.json"

_creds_json: str | None = None
if _CREDS_PATH.exists():
    _creds_json = _CREDS_PATH.read_text(encoding="utf-8")

_impersonate_email: str | None = os.environ.get("GOOGLE_IMPERSONATE_EMAIL")


def _live_access_token() -> str | None:
    settings = get_settings()
    token = settings.google_workspace.live_test.access_token
    if token is not None and token.strip() != "":
        return token.strip()
    env_token = os.environ.get("GOOGLE_ACCESS_TOKEN")
    if env_token is not None and env_token.strip() != "":
        return env_token.strip()
    return None


def _oauth_ready() -> bool:
    return _live_access_token() is not None


def _sa_ready() -> bool:
    return _creds_json is not None and _impersonate_email is not None


def require_google_sheets_live_credentials() -> None:
    """
    Skip unless OAuth access token OR (SA JSON + GOOGLE_IMPERSONATE_EMAIL).

    Prefer live_test.access_token / GOOGLE_ACCESS_TOKEN for consumer Gmail;
    SA path needs Workspace domain-wide delegation.
    """
    if _oauth_ready() or _sa_ready():
        return
    reasons: list[str] = []
    if not _oauth_ready():
        reasons.append(
            "нет OAuth: google_workspace.live_test.access_token / GOOGLE_ACCESS_TOKEN"
        )
    if _creds_json is None:
        reasons.append(f"файл {_CREDS_PATH} не найден")
    if _impersonate_email is None:
        reasons.append("env GOOGLE_IMPERSONATE_EMAIL не задан (для SA path)")
    pytest.skip("; ".join(reasons))


def google_sheets_live_auth_material() -> GoogleAuthMaterial:
    """OAuth token preferred; else SA + impersonate."""
    require_google_sheets_live_credentials()
    token = _live_access_token()
    if token is not None:
        return GoogleAuthMaterial(access_token=token)
    if _creds_json is None or _impersonate_email is None:
        raise RuntimeError("SA live credentials missing after skip check")
    return GoogleAuthMaterial(
        credentials_json=_creds_json,
        subject=_impersonate_email,
    )


def google_sheets_credentials_json() -> str:
    require_google_sheets_live_credentials()
    if _creds_json is None:
        raise RuntimeError("google_service_account.json missing after skip check")
    return _creds_json


def google_sheets_impersonate_email() -> str:
    require_google_sheets_live_credentials()
    if _impersonate_email is None:
        raise RuntimeError("GOOGLE_IMPERSONATE_EMAIL missing after skip check")
    return _impersonate_email


def make_google_sheets_client() -> GoogleSheetsClient:
    material = google_sheets_live_auth_material()
    return GoogleSheetsClient(
        credentials_json=material.credentials_json,
        access_token=material.access_token,
        subject=material.subject,
    )


def sheets_execution_variables() -> dict[str, str]:
    """state.variables for sheets_* tools from live auth material."""
    material = google_sheets_live_auth_material()
    if material.access_token is not None and material.access_token.strip() != "":
        return {"google_access_token": material.access_token}
    if material.credentials_json is None:
        raise RuntimeError("live auth material missing credentials_json")
    variables = {"google_service_account": material.credentials_json}
    if material.subject is not None and material.subject.strip() != "":
        variables["google_impersonate_email"] = material.subject
    return variables


def google_sheets_service_account_client_email() -> str:
    """client_email from SA JSON (for share-by-email live asserts)."""
    if _creds_json is None:
        pytest.skip("SA JSON required for client_email asserts")
    payload = require_json_object(
        json.loads(_creds_json),
        "google.service_account",
    )
    email = payload.get("client_email")
    if not isinstance(email, str) or email == "":
        raise ValueError("service account JSON missing client_email")
    return email
