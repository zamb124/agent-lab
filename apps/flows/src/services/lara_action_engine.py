"""
Единый Action Engine для Lara (confirm-first lifecycle).
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any, Protocol
from collections.abc import Awaitable, Callable
from uuid import uuid4

from core.logging import get_logger

logger = get_logger(__name__)

ACTION_SCHEMA_VERSION = "1.0.0"

_APPLY_LOCK_TTL_SECONDS = 120
_APPLY_CONTENTION_POLL_SEC = 0.025
_APPLY_CONTENTION_MAX_POLLS = 80


class LaraActionRedisClient(Protocol):
    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, ttl: int | None = None) -> bool: ...

    async def set_nx(self, key: str, value: str, ttl_seconds: int) -> bool: ...

    async def delete(self, *keys: str) -> int: ...


class LaraActionEngine:
    """Серверный движок действий Lara c pending-actions в Redis."""

    def __init__(self, redis_client: LaraActionRedisClient, ttl_seconds: int = 3600):
        self._redis = redis_client
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _pending_key(company_id: str, pending_action_id: str) -> str:
        return f"assistant:pending_action:{company_id}:{pending_action_id}"

    @staticmethod
    def _apply_lock_key(company_id: str, pending_action_id: str) -> str:
        return f"assistant:pending_apply_lock:{company_id}:{pending_action_id}"

    @staticmethod
    def _validate_owner(action: dict[str, Any], company_id: str, user_id: str, context_id: str) -> None:
        owner = action.get("owner")
        if not isinstance(owner, dict):
            raise ValueError("Pending action owner is invalid")
        if owner.get("company_id") != company_id:
            raise PermissionError("Pending action company mismatch")
        if owner.get("user_id") != user_id:
            raise PermissionError("Pending action user mismatch")
        if owner.get("context_id") != context_id:
            raise PermissionError("Pending action context mismatch")

    async def preview_action(
        self,
        *,
        company_id: str,
        user_id: str,
        context_id: str,
        capability: str,
        operation: str,
        target: dict[str, Any],
        payload: dict[str, Any],
        preview: dict[str, Any],
        risk: str,
        requires_confirmation: bool = True,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if not company_id:
            raise ValueError("company_id is required")
        if not user_id:
            raise ValueError("user_id is required")
        if not context_id:
            raise ValueError("context_id is required")
        if not capability:
            raise ValueError("capability is required")
        if not operation:
            raise ValueError("operation is required")
        if not isinstance(target, dict):
            raise ValueError("target must be an object")
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        if not isinstance(preview, dict):
            raise ValueError("preview must be an object")

        action_id = str(uuid4())
        pending_action_id = str(uuid4())
        resolved_idempotency_key = idempotency_key or action_id
        now_iso = self._now_iso()
        action: dict[str, Any] = {
            "schema_version": ACTION_SCHEMA_VERSION,
            "action_id": action_id,
            "pending_action_id": pending_action_id,
            "action_kind": "apply",
            "idempotency_key": resolved_idempotency_key,
            "status": "previewed",
            "requires_confirmation": requires_confirmation,
            "capability": capability,
            "operation": operation,
            "target": target,
            "payload": payload,
            "preview": preview,
            "risk": risk,
            "owner": {
                "company_id": company_id,
                "user_id": user_id,
                "context_id": context_id,
            },
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        key = self._pending_key(company_id, pending_action_id)
        is_saved = await self._redis.set(key, json.dumps(action, ensure_ascii=False), ttl=self._ttl_seconds)
        if not is_saved:
            raise RuntimeError("Failed to persist pending action")
        logger.info(
            "lara_action_previewed action_id=%s pending_action_id=%s capability=%s operation=%s",
            action_id,
            pending_action_id,
            capability,
            operation,
        )
        return action

    async def get_action(self, *, company_id: str, pending_action_id: str) -> dict[str, Any]:
        key = self._pending_key(company_id, pending_action_id)
        raw = await self._redis.get(key)
        if raw is None:
            raise ValueError(f"Pending action '{pending_action_id}' not found or expired")
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("Pending action payload is invalid")
        return parsed

    async def _wait_apply_or_raise_contention(
        self,
        *,
        company_id: str,
        user_id: str,
        context_id: str,
        pending_action_id: str,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        for _ in range(_APPLY_CONTENTION_MAX_POLLS):
            await asyncio.sleep(_APPLY_CONTENTION_POLL_SEC)
            action = await self.get_action(company_id=company_id, pending_action_id=pending_action_id)
            self._validate_owner(action, company_id, user_id, context_id)
            st = action.get("status")
            if st == "applied":
                if idempotency_key and action.get("idempotency_key") != idempotency_key:
                    raise ValueError("idempotency_key mismatch for already applied action")
                return action
            if st != "previewed":
                raise ValueError(f"Unsupported pending action status: {action.get('status')}")
        raise ValueError("Timeout waiting for concurrent Lara pending-action apply")

    async def apply_action(
        self,
        *,
        company_id: str,
        user_id: str,
        context_id: str,
        pending_action_id: str,
        idempotency_key: str | None,
        apply_fn: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        lock_key = self._apply_lock_key(company_id, pending_action_id)
        lock_ok = await self._redis.set_nx(lock_key, "1", _APPLY_LOCK_TTL_SECONDS)
        if not lock_ok:
            return await self._wait_apply_or_raise_contention(
                company_id=company_id,
                user_id=user_id,
                context_id=context_id,
                pending_action_id=pending_action_id,
                idempotency_key=idempotency_key,
            )
        try:
            action = await self.get_action(company_id=company_id, pending_action_id=pending_action_id)
            self._validate_owner(action, company_id, user_id, context_id)

            if action.get("status") == "applied":
                if idempotency_key and action.get("idempotency_key") != idempotency_key:
                    raise ValueError("idempotency_key mismatch for already applied action")
                return action
            if action.get("status") != "previewed":
                raise ValueError(f"Unsupported pending action status: {action.get('status')}")

            resolved_idempotency_key = idempotency_key or action.get("idempotency_key")
            if resolved_idempotency_key != action.get("idempotency_key"):
                raise ValueError("idempotency_key mismatch")

            result = await apply_fn(action)
            if not isinstance(result, dict):
                raise ValueError("apply_fn must return an object")

            action["status"] = "applied"
            action["result"] = result
            action["applied_at"] = self._now_iso()
            action["updated_at"] = self._now_iso()
            key = self._pending_key(company_id, pending_action_id)
            is_saved = await self._redis.set(key, json.dumps(action, ensure_ascii=False), ttl=self._ttl_seconds)
            if not is_saved:
                raise RuntimeError("Failed to persist applied action")
            logger.info(
                "lara_action_applied action_id=%s pending_action_id=%s",
                action.get("action_id"),
                pending_action_id,
            )
            return action
        finally:
            await self._redis.delete(lock_key)

    async def reject_action(
        self,
        *,
        company_id: str,
        user_id: str,
        context_id: str,
        pending_action_id: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        action = await self.get_action(company_id=company_id, pending_action_id=pending_action_id)
        self._validate_owner(action, company_id, user_id, context_id)
        if action.get("status") == "applied":
            raise ValueError("Applied action cannot be rejected")
        action["status"] = "rejected"
        action["rejected_at"] = self._now_iso()
        action["updated_at"] = self._now_iso()
        action["reject_reason"] = reason or "rejected_by_user"
        key = self._pending_key(company_id, pending_action_id)
        is_saved = await self._redis.set(key, json.dumps(action, ensure_ascii=False), ttl=self._ttl_seconds)
        if not is_saved:
            raise RuntimeError("Failed to persist rejected action")
        logger.info(
            "lara_action_rejected action_id=%s pending_action_id=%s reason=%s",
            action.get("action_id"),
            pending_action_id,
            action["reject_reason"],
        )
        return action
