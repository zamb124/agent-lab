"""OAuth scopes registry for Google Workspace services used by Flows tools."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, Literal

GoogleWorkspaceOAuthService = Literal["workspace", "docs", "sheets"]

GOOGLE_SCOPE_DOCUMENTS: Final[str] = "https://www.googleapis.com/auth/documents"
GOOGLE_SCOPE_DRIVE: Final[str] = "https://www.googleapis.com/auth/drive"
GOOGLE_SCOPE_DRIVE_FILE: Final[str] = "https://www.googleapis.com/auth/drive.file"
GOOGLE_SCOPE_SPREADSHEETS: Final[str] = "https://www.googleapis.com/auth/spreadsheets"

GOOGLE_WORKSPACE_SCOPES: Final[tuple[str, ...]] = (
    GOOGLE_SCOPE_DOCUMENTS,
    GOOGLE_SCOPE_SPREADSHEETS,
    GOOGLE_SCOPE_DRIVE_FILE,
)

GOOGLE_SERVICE_SCOPES: Final[Mapping[GoogleWorkspaceOAuthService, tuple[str, ...]]] = {
    # Canonical: one Connect Google for docs + sheets tools.
    "workspace": GOOGLE_WORKSPACE_SCOPES,
    # Prior service keys still readable; new OAuth writes service=workspace.
    "docs": (GOOGLE_SCOPE_DOCUMENTS, GOOGLE_SCOPE_DRIVE),
    "sheets": (GOOGLE_SCOPE_SPREADSHEETS, GOOGLE_SCOPE_DRIVE_FILE),
}

GOOGLE_OAUTH_SERVICE_CANONICAL: Final[str] = "workspace"
GOOGLE_OAUTH_SERVICE_PRIOR_KEYS: Final[tuple[str, ...]] = ("docs", "sheets")


def scopes_for_google_service(service: str) -> list[str]:
    """
    Return OAuth scopes for a Google Workspace tool service.

    Unknown service raises ValueError (zero-guess).
    """
    if service == "workspace" or service == "docs" or service == "sheets":
        return list(GOOGLE_SERVICE_SCOPES[service])
    known = ", ".join(sorted(GOOGLE_SERVICE_SCOPES))
    raise ValueError(
        f"Unknown Google Workspace OAuth service {service!r}; known: {known}"
    )


def canonicalize_google_oauth_service(service: str) -> str:
    """Map purpose/prior service ids to the canonical OAuth service key."""
    if service in ("workspace", "docs", "sheets"):
        return GOOGLE_OAUTH_SERVICE_CANONICAL
    raise ValueError(
        f"Unknown Google Workspace OAuth service {service!r}; "
        + f"known: {', '.join(sorted(GOOGLE_SERVICE_SCOPES))}"
    )
