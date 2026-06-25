"""Глобальный каталог HTTPS MCP серверов (official registry snapshot)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import ClassVar, Literal, Self, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "MCPAuthPolicy",
    "MCPCatalogEntry",
    "MCPCatalogHostClass",
    "MCPCatalogVerifyStatus",
    "compute_catalog_snapshot_hash",
]


class MCPCatalogVerifyStatus(str, Enum):
    VERIFIED = "verified"
    AUTH_REQUIRED = "auth_required"
    UNREACHABLE = "unreachable"
    PENDING = "pending"


class MCPAuthPolicy(str, Enum):
    NONE = "none"
    API_KEY = "api_key"
    OAUTH = "oauth"
    UNKNOWN = "unknown"


class MCPCatalogHostClass(str, Enum):
    DIRECT = "direct"
    SMITHERY_PROXY = "smithery_proxy"


def compute_catalog_snapshot_hash(
    *,
    title: str,
    description: str | None,
    upstream_url: str,
    transport_type: str,
    auth_template: dict[str, str],
    is_deprecated: bool,
    verify_status: MCPCatalogVerifyStatus,
) -> str:
    payload = {
        "title": title,
        "description": description,
        "upstream_url": upstream_url,
        "transport_type": transport_type,
        "auth_template": auth_template,
        "is_deprecated": is_deprecated,
        "verify_status": verify_status.value,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class MCPCatalogEntry(BaseModel):
    """Запись глобального MCP catalog (не per-company)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    catalog_id: str = Field(..., min_length=2, max_length=64)
    registry_name: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    description: str | None = Field(default=None)
    version: str | None = Field(default=None)
    upstream_url: str = Field(..., min_length=8)
    transport_type: Literal["http", "sse"] = Field(default="http")
    deployment_class: Literal["remote_https"] = Field(default="remote_https")
    host_class: MCPCatalogHostClass = Field(default=MCPCatalogHostClass.DIRECT)
    auth_policy: MCPAuthPolicy = Field(default=MCPAuthPolicy.UNKNOWN)
    auth_template: dict[str, str] = Field(default_factory=dict)
    required_variables: list[str] = Field(default_factory=list)
    verify_status: MCPCatalogVerifyStatus = Field(default=MCPCatalogVerifyStatus.PENDING)
    tool_count_snapshot: int = Field(default=0, ge=0)
    catalog_snapshot_hash: str = Field(..., min_length=64, max_length=64)
    platform_approved: bool = Field(default=False)
    is_deprecated: bool = Field(default=False)
    last_crawled_at: datetime | None = Field(default=None)
    last_verified_at: datetime | None = Field(default=None)

    def recompute_snapshot_hash(self) -> str:
        return compute_catalog_snapshot_hash(
            title=self.title,
            description=self.description,
            upstream_url=self.upstream_url,
            transport_type=self.transport_type,
            auth_template=self.auth_template,
            is_deprecated=self.is_deprecated,
            verify_status=self.verify_status,
        )


class MCPCatalogAllowlistItemPayload(BaseModel):
    """Строка YAML allowlist для MCP catalog crawler."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    catalog_id: str = Field(..., min_length=1)
    platform_approved: bool
    auth_template: dict[str, str] = Field(default_factory=dict)
    required_variables: list[str] = Field(default_factory=list)
    auth_policy: MCPAuthPolicy = MCPAuthPolicy.UNKNOWN
    registry_name: str | None = None
    upstream_url: str | None = None
    transport_type: Literal["http", "sse"] = "http"
    title: str | None = None
    description: str | None = None

    @field_validator("catalog_id", "registry_name", "title", mode="before")
    @classmethod
    def _strip_optional_strings(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("value must be a string")
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must be non-empty")
        return stripped

    @field_validator("required_variables", mode="before")
    @classmethod
    def _normalize_required_variables(cls, value: object) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("required_variables must be a list")
        normalized: list[str] = []
        for variable_name in cast(list[object], value):
            if not isinstance(variable_name, str) or not variable_name.strip():
                raise ValueError("required_variables entries must be non-empty strings")
            normalized.append(variable_name.strip())
        return normalized

    @field_validator("transport_type", mode="before")
    @classmethod
    def _normalize_transport_type(cls, value: object) -> object:
        if value is None:
            return "http"
        if not isinstance(value, str) or not value.strip():
            raise ValueError("transport_type must be a non-empty string")
        normalized = value.strip().lower()
        if normalized not in ("http", "sse"):
            raise ValueError("transport_type must be http or sse")
        return normalized

    @field_validator("upstream_url", mode="before")
    @classmethod
    def _normalize_upstream_url(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError("upstream_url must be a non-empty string")
        stripped = value.strip()
        if not stripped.startswith("https://"):
            raise ValueError("upstream_url must be https://")
        return stripped

    @model_validator(mode="after")
    def _require_registry_name_with_upstream(self) -> Self:
        if self.upstream_url is not None and self.registry_name is None:
            raise ValueError("registry_name required when upstream_url is set")
        return self
