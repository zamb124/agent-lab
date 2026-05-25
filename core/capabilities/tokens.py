"""Подпись и проверка execution token для sandbox capability calls."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from core.capabilities.models import CapabilityExecutionContext
from core.config import get_settings


class CapabilityExecutionTokenClaims(BaseModel):
    """Claims, которые подписывает flows перед запуском code-runner."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    company_id: str = Field(..., min_length=1)
    user_id: str | None = None
    flow_id: str = Field(..., min_length=1)
    branch_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    task_id: str = Field(..., min_length=1)
    context_id: str = Field(..., min_length=1)
    channel: str = Field(..., min_length=1)
    request_id: str | None = None
    durable_execution_branch_id: str | None = Field(default=None, min_length=1)
    durable_node_schedule_sequence: int | None = Field(default=None, ge=0)
    durable_superstep_sequence: int | None = Field(default=None, ge=0)
    source_node_id: str | None = Field(default=None, min_length=1)
    source_tool_call_id: str | None = Field(default=None, min_length=1)
    exp: int = Field(..., gt=0)


def issue_execution_token(
    claims: CapabilityExecutionTokenClaims,
) -> str:
    payload = claims.model_dump(mode="json")
    payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload_part = _b64url_encode(payload_bytes)
    signature_part = _sign(payload_part)
    return f"{payload_part}.{signature_part}"


def verify_execution_token(token: str) -> CapabilityExecutionTokenClaims:
    parts = token.split(".")
    if len(parts) != 2:
        raise ValueError("Invalid execution token format")
    payload_part, signature_part = parts
    expected_signature = _sign(payload_part)
    if not hmac.compare_digest(signature_part, expected_signature):
        raise ValueError("Invalid execution token signature")
    payload_bytes = _b64url_decode(payload_part)
    claims = CapabilityExecutionTokenClaims.model_validate_json(payload_bytes)
    if claims.exp < int(time.time()):
        raise ValueError("Execution token expired")
    return claims


def verify_execution_context(context: CapabilityExecutionContext) -> None:
    claims = verify_execution_token(context.execution_token)
    mismatches: list[str] = []
    if claims.company_id != context.company_id:
        mismatches.append("company_id")
    if claims.user_id != context.user_id:
        mismatches.append("user_id")
    if claims.flow_id != context.flow_id:
        mismatches.append("flow_id")
    if claims.branch_id != context.branch_id:
        mismatches.append("branch_id")
    if claims.session_id != context.session_id:
        mismatches.append("session_id")
    if claims.task_id != context.task_id:
        mismatches.append("task_id")
    if claims.context_id != context.context_id:
        mismatches.append("context_id")
    if claims.channel != context.channel:
        mismatches.append("channel")
    if claims.request_id != context.request_id:
        mismatches.append("request_id")
    if claims.durable_execution_branch_id != context.durable_execution_branch_id:
        mismatches.append("durable_execution_branch_id")
    if claims.durable_node_schedule_sequence != context.durable_node_schedule_sequence:
        mismatches.append("durable_node_schedule_sequence")
    if claims.durable_superstep_sequence != context.durable_superstep_sequence:
        mismatches.append("durable_superstep_sequence")
    if claims.source_node_id != context.source_node_id:
        mismatches.append("source_node_id")
    if claims.source_tool_call_id != context.source_tool_call_id:
        mismatches.append("source_tool_call_id")
    if mismatches:
        joined = ", ".join(mismatches)
        raise ValueError(f"Execution token context mismatch: {joined}")


def execution_token_exp(ttl_seconds: int) -> int:
    if ttl_seconds <= 0:
        raise ValueError("ttl_seconds must be positive")
    return int(time.time()) + ttl_seconds


def _secret() -> bytes:
    settings = get_settings()
    secret = settings.auth.jwt_secret_key or settings.auth.secret_key
    if secret is None or not secret.strip():
        raise ValueError("auth.jwt_secret_key or auth.secret_key is required for capability execution tokens")
    return secret.encode("utf-8")


def _sign(payload_part: str) -> str:
    digest = hmac.new(_secret(), payload_part.encode("ascii"), hashlib.sha256).digest()
    return _b64url_encode(digest)


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))
