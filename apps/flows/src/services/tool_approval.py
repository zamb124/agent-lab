"""Platform tool approval store (server-owned pending approvals).

LaraActionEngine remains the runtime path for Lara propose/apply until Phase 4 migration.
This store is the general-purpose replacement keyed by tool_id + argument hash + actor.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol
from uuid import uuid4

from pydantic import Field

from core.logging import get_logger
from core.models import StrictBaseModel
from core.types import JsonObject

logger = get_logger(__name__)

ToolApprovalStatus = Literal["pending", "consumed", "invalidated"]

_DEFAULT_TTL_SECONDS = 3600


class ToolApprovalRedisClient(Protocol):
    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, *, ttl: int) -> bool: ...

    async def delete(self, *keys: str) -> int: ...


class ToolApprovalRecord(StrictBaseModel):
    """Pending or resolved approval bound to actor, tool revision and argument hash."""

    approval_id: str = Field(..., min_length=1)
    actor_user_id: str = Field(..., min_length=1)
    company_id: str = Field(..., min_length=1)
    tool_id: str = Field(..., min_length=1)
    definition_version: str = Field(..., min_length=1)
    argument_hash: str = Field(..., min_length=1)
    created_at: str = Field(..., min_length=1)
    expires_at: str = Field(..., min_length=1)
    status: ToolApprovalStatus


def hash_tool_arguments(args: JsonObject) -> str:
    """SHA-256 of canonical JSON (sorted keys, compact separators)."""
    canonical = json.dumps(args, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ToolApprovalStore:
    """Redis-backed store for tool approval records."""

    def __init__(self, redis_client: ToolApprovalRedisClient, ttl_seconds: int = _DEFAULT_TTL_SECONDS):
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._redis: ToolApprovalRedisClient = redis_client
        self._ttl_seconds: int = ttl_seconds

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _key(company_id: str, approval_id: str) -> str:
        return f"tool:approval:{company_id}:{approval_id}"

    async def create_pending(
        self,
        *,
        actor_user_id: str,
        company_id: str,
        tool_id: str,
        definition_version: str,
        args: JsonObject,
    ) -> ToolApprovalRecord:
        if not actor_user_id.strip():
            raise ValueError("actor_user_id is required")
        if not company_id.strip():
            raise ValueError("company_id is required")
        if not tool_id.strip():
            raise ValueError("tool_id is required")
        if not definition_version.strip():
            raise ValueError("definition_version is required")

        now = self._now()
        expires = now + timedelta(seconds=self._ttl_seconds)
        record = ToolApprovalRecord(
            approval_id=str(uuid4()),
            actor_user_id=actor_user_id,
            company_id=company_id,
            tool_id=tool_id,
            definition_version=definition_version,
            argument_hash=hash_tool_arguments(args),
            created_at=now.isoformat(),
            expires_at=expires.isoformat(),
            status="pending",
        )
        key = self._key(company_id, record.approval_id)
        saved = await self._redis.set(key, record.model_dump_json(), ttl=self._ttl_seconds)
        if not saved:
            raise RuntimeError("Failed to persist tool approval")
        logger.info(
            "tool_approval_pending approval_id=%s tool_id=%s company_id=%s",
            record.approval_id,
            tool_id,
            company_id,
        )
        return record

    async def get(self, *, company_id: str, approval_id: str) -> ToolApprovalRecord:
        if not company_id.strip():
            raise ValueError("company_id is required")
        if not approval_id.strip():
            raise ValueError("approval_id is required")
        raw = await self._redis.get(self._key(company_id, approval_id))
        if raw is None:
            raise ValueError(f"Tool approval '{approval_id}' not found or expired")
        return ToolApprovalRecord.model_validate_json(raw)

    async def consume_for_apply(
        self,
        *,
        company_id: str,
        approval_id: str,
        actor_user_id: str,
        tool_id: str,
        args: JsonObject,
    ) -> ToolApprovalRecord:
        record = await self.get(company_id=company_id, approval_id=approval_id)
        if record.status != "pending":
            raise ValueError(f"Tool approval status is {record.status}, expected pending")
        if record.actor_user_id != actor_user_id:
            raise PermissionError("Tool approval actor mismatch")
        if record.tool_id != tool_id:
            raise ValueError("Tool approval tool_id mismatch")
        expected_hash = hash_tool_arguments(args)
        if record.argument_hash != expected_hash:
            raise ValueError("Tool approval argument_hash mismatch")

        consumed = record.model_copy(update={"status": "consumed"})
        key = self._key(company_id, approval_id)
        saved = await self._redis.set(key, consumed.model_dump_json(), ttl=self._ttl_seconds)
        if not saved:
            raise RuntimeError("Failed to persist consumed tool approval")
        logger.info(
            "tool_approval_consumed approval_id=%s tool_id=%s",
            approval_id,
            tool_id,
        )
        return consumed

    async def invalidate(self, *, company_id: str, approval_id: str) -> ToolApprovalRecord:
        record = await self.get(company_id=company_id, approval_id=approval_id)
        if record.status == "consumed":
            raise ValueError("Consumed tool approval cannot be invalidated")
        invalidated = record.model_copy(update={"status": "invalidated"})
        key = self._key(company_id, approval_id)
        saved = await self._redis.set(key, invalidated.model_dump_json(), ttl=self._ttl_seconds)
        if not saved:
            raise RuntimeError("Failed to persist invalidated tool approval")
        logger.info(
            "tool_approval_invalidated approval_id=%s tool_id=%s",
            approval_id,
            record.tool_id,
        )
        return invalidated
