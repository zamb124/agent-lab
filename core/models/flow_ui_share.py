"""Strict contracts for revocable live Flow UI session sharing."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from core.models.base import StrictBaseModel

FlowUISharePermission = Literal["viewer", "editor"]


class FlowUIShareGrant(StrictBaseModel):
    grant_id: str = Field(min_length=24)
    company_id: str = Field(min_length=1)
    flow_id: str = Field(min_length=1)
    branch_id: str = Field(min_length=1)
    context_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    minimum_revision: int = Field(ge=1)
    permission: FlowUISharePermission
    redacted_value_paths: list[str] = Field(default_factory=list)
    created_by_user_id: str = Field(min_length=1)
    expires_at: datetime
    revoked_at: datetime | None = None
    created_at: datetime


class FlowUIShareCreateRequest(StrictBaseModel):
    flow_id: str = Field(min_length=1)
    context_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    minimum_revision: int = Field(ge=1)
    permission: FlowUISharePermission = "viewer"
    redacted_value_paths: list[str] = Field(default_factory=list)
    expires_in_seconds: int = Field(default=86_400, ge=300, le=2_592_000)


class FlowUIShareCreateResponse(StrictBaseModel):
    grant: FlowUIShareGrant
    share_url: str = Field(min_length=1)


class FlowUIShareExchangeResponse(StrictBaseModel):
    token: str = Field(min_length=1)
    token_type: Literal["Bearer"] = "Bearer"
    expires_at: datetime
    flow_id: str
    branch_id: str
    context_id: str
    document_id: str
    minimum_revision: int
    permission: FlowUISharePermission
    redacted_value_paths: list[str] = Field(default_factory=list)
    flows_base_url: str = Field(min_length=1)


__all__ = [
    "FlowUIShareCreateRequest",
    "FlowUIShareCreateResponse",
    "FlowUIShareExchangeResponse",
    "FlowUIShareGrant",
    "FlowUISharePermission",
]
