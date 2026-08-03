"""Unit tests for ToolApprovalStore."""

from __future__ import annotations

import pytest

from apps.flows.src.services.tool_approval import (
    ToolApprovalStore,
    hash_tool_arguments,
)
from core.types import JsonObject


class InMemoryRedis:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, *, ttl: int) -> bool:
        _ = ttl
        self._store[key] = value
        return True

    async def delete(self, *keys: str) -> int:
        n = 0
        for key in keys:
            if key in self._store:
                del self._store[key]
                n += 1
        return n


def test_hash_tool_arguments_is_order_independent() -> None:
    left: JsonObject = {"b": 2, "a": 1}
    right: JsonObject = {"a": 1, "b": 2}
    assert hash_tool_arguments(left) == hash_tool_arguments(right)


@pytest.mark.asyncio
async def test_create_pending_get_and_consume() -> None:
    store = ToolApprovalStore(redis_client=InMemoryRedis(), ttl_seconds=60)
    args: JsonObject = {"entity_id": "e1", "text": "note"}
    pending = await store.create_pending(
        actor_user_id="u1",
        company_id="c1",
        tool_id="crm_create_note",
        definition_version="1",
        args=args,
    )
    assert pending.status == "pending"
    loaded = await store.get(company_id="c1", approval_id=pending.approval_id)
    assert loaded.argument_hash == hash_tool_arguments(args)

    consumed = await store.consume_for_apply(
        company_id="c1",
        approval_id=pending.approval_id,
        actor_user_id="u1",
        tool_id="crm_create_note",
        args=args,
    )
    assert consumed.status == "consumed"


@pytest.mark.asyncio
async def test_consume_rejects_argument_hash_mismatch() -> None:
    store = ToolApprovalStore(redis_client=InMemoryRedis(), ttl_seconds=60)
    pending = await store.create_pending(
        actor_user_id="u1",
        company_id="c1",
        tool_id="crm_create_note",
        definition_version="1",
        args={"text": "one"},
    )
    with pytest.raises(ValueError, match="argument_hash"):
        await store.consume_for_apply(
            company_id="c1",
            approval_id=pending.approval_id,
            actor_user_id="u1",
            tool_id="crm_create_note",
            args={"text": "two"},
        )


@pytest.mark.asyncio
async def test_consume_rejects_actor_mismatch() -> None:
    store = ToolApprovalStore(redis_client=InMemoryRedis(), ttl_seconds=60)
    pending = await store.create_pending(
        actor_user_id="u1",
        company_id="c1",
        tool_id="crm_create_note",
        definition_version="1",
        args={"text": "one"},
    )
    with pytest.raises(PermissionError, match="actor"):
        await store.consume_for_apply(
            company_id="c1",
            approval_id=pending.approval_id,
            actor_user_id="u2",
            tool_id="crm_create_note",
            args={"text": "one"},
        )


@pytest.mark.asyncio
async def test_invalidate_pending() -> None:
    store = ToolApprovalStore(redis_client=InMemoryRedis(), ttl_seconds=60)
    pending = await store.create_pending(
        actor_user_id="u1",
        company_id="c1",
        tool_id="crm_create_note",
        definition_version="1",
        args={"text": "one"},
    )
    invalidated = await store.invalidate(company_id="c1", approval_id=pending.approval_id)
    assert invalidated.status == "invalidated"
