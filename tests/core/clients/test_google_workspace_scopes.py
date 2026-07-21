"""Unit tests for Google Workspace OAuth scopes registry."""

import pytest

from core.clients.google_workspace_scopes import (
    GOOGLE_OAUTH_SERVICE_CANONICAL,
    GOOGLE_SCOPE_DOCUMENTS,
    GOOGLE_SCOPE_DRIVE,
    GOOGLE_SCOPE_DRIVE_FILE,
    GOOGLE_SCOPE_SPREADSHEETS,
    canonicalize_google_oauth_service,
    scopes_for_google_service,
)


def test_scopes_for_workspace_canonical():
    assert scopes_for_google_service("workspace") == [
        GOOGLE_SCOPE_DOCUMENTS,
        GOOGLE_SCOPE_SPREADSHEETS,
        GOOGLE_SCOPE_DRIVE_FILE,
    ]


def test_scopes_for_docs_preserves_historical_oauth_drive():
    assert scopes_for_google_service("docs") == [
        GOOGLE_SCOPE_DOCUMENTS,
        GOOGLE_SCOPE_DRIVE,
    ]


def test_scopes_for_sheets():
    assert scopes_for_google_service("sheets") == [
        GOOGLE_SCOPE_SPREADSHEETS,
        GOOGLE_SCOPE_DRIVE_FILE,
    ]


def test_canonicalize_maps_prior_to_workspace():
    assert canonicalize_google_oauth_service("docs") == GOOGLE_OAUTH_SERVICE_CANONICAL
    assert canonicalize_google_oauth_service("sheets") == GOOGLE_OAUTH_SERVICE_CANONICAL
    assert canonicalize_google_oauth_service("workspace") == GOOGLE_OAUTH_SERVICE_CANONICAL


def test_scopes_unknown_service_raises():
    with pytest.raises(ValueError, match="Unknown Google Workspace OAuth service"):
        scopes_for_google_service("calendar")
