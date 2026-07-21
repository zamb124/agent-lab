"""Typed auth material for Google Docs / Sheets clients."""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

from pydantic import ConfigDict, model_validator

from core.models.base import StrictBaseModel


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
    variables: Mapping[str, object],
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


def _optional_nonempty_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip() != "":
        return value
    return None
