"""Typed auth material for Google Docs / Sheets clients."""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar, Protocol, cast

from google.auth.transport.requests import Request as AuthRequest
from google.oauth2 import service_account as sa
from pydantic import ConfigDict, model_validator

from core.models.base import StrictBaseModel
from core.types import JsonObject, JsonValue


class GoogleServiceAccountCredentials(Protocol):
    valid: bool
    token: str | None

    def refresh(self, request: AuthRequest) -> None: ...

    def with_subject(self, subject: str) -> GoogleServiceAccountCredentials: ...


class _FromServiceAccountInfo(Protocol):
    def __call__(
        self,
        info: JsonObject,
        *,
        scopes: list[str],
    ) -> GoogleServiceAccountCredentials: ...


def google_service_account_credentials(
    info: JsonObject,
    scopes: list[str],
) -> GoogleServiceAccountCredentials:
    from_service_account_info = cast(
        _FromServiceAccountInfo,
        sa.Credentials.from_service_account_info,
    )
    return from_service_account_info(info, scopes=scopes)


class GoogleAuthMaterial(StrictBaseModel):
    """
    Exactly one of access_token or credentials_json.

    subject — Workspace domain-wide delegation (SA only).
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    access_token: str | None = None
    credentials_json: str | None = None
    subject: str | None = None

    @model_validator(mode="after")
    def _xor_credentials(self) -> GoogleAuthMaterial:
        has_token = self.access_token is not None and self.access_token.strip() != ""
        has_sa = (
            self.credentials_json is not None and self.credentials_json.strip() != ""
        )
        if has_token and has_sa:
            raise ValueError("Pass access_token or credentials_json, not both")
        if not has_token and not has_sa:
            raise ValueError("Pass access_token or credentials_json")
        if self.subject is not None and self.subject.strip() != "" and not has_sa:
            raise ValueError("subject requires credentials_json")
        return self


def auth_material_from_execution_variables(
    variables: Mapping[str, JsonValue],
) -> GoogleAuthMaterial | None:
    """
    Explicit ExecutionState.variables override for Google auth.

    Returns None when no Google auth variables are set.
    """
    credentials_json = _optional_nonempty_str(variables.get("google_service_account"))
    access_token = _optional_nonempty_str(variables.get("google_access_token"))
    subject = _optional_nonempty_str(variables.get("google_impersonate_email"))
    if credentials_json is None and access_token is None:
        if subject is not None:
            raise ValueError(
                "google_impersonate_email requires google_service_account"
            )
        return None
    return GoogleAuthMaterial(
        access_token=access_token,
        credentials_json=credentials_json,
        subject=subject,
    )


def _optional_nonempty_str(value: JsonValue) -> str | None:
    if isinstance(value, str) and value.strip() != "":
        return value
    return None
