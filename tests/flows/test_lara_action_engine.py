from __future__ import annotations

import pytest

from apps.flows.src.services.lara_action_engine import LaraActionEngine


class InMemoryRedis:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ttl: int | None = None) -> bool:
        _ = ttl
        self._store[key] = value
        return True


@pytest.mark.asyncio
async def test_preview_and_apply_idempotent() -> None:
    redis = InMemoryRedis()
    engine = LaraActionEngine(redis_client=redis, ttl_seconds=60)
    action = await engine.preview_action(
        company_id="c1",
        user_id="u1",
        context_id="ctx1",
        capability="flows.node",
        operation="patch",
        target={"flow_id": "f1", "node_id": "n1"},
        payload={"patch": {"prompt": "new"}},
        preview={"summary": "patch", "node_before": {}, "node_after": {"prompt": "new"}},
        risk="medium",
        idempotency_key="idem-1",
    )
    assert action["status"] == "previewed"
    pending_action_id = action["pending_action_id"]

    applied = await engine.apply_action(
        company_id="c1",
        user_id="u1",
        context_id="ctx1",
        pending_action_id=pending_action_id,
        idempotency_key="idem-1",
        apply_fn=lambda _: _apply_ok(),
    )
    assert applied["status"] == "applied"
    assert applied["result"]["ok"] is True

    replayed = await engine.apply_action(
        company_id="c1",
        user_id="u1",
        context_id="ctx1",
        pending_action_id=pending_action_id,
        idempotency_key="idem-1",
        apply_fn=lambda _: _apply_should_not_run(),
    )
    assert replayed["status"] == "applied"
    assert replayed["result"]["ok"] is True


async def _apply_ok() -> dict[str, bool]:
    return {"ok": True}


async def _apply_should_not_run() -> dict[str, bool]:
    raise AssertionError("apply_fn should not run on idempotent replay")


@pytest.mark.asyncio
async def test_owner_guard_rejects_different_user() -> None:
    redis = InMemoryRedis()
    engine = LaraActionEngine(redis_client=redis, ttl_seconds=60)
    action = await engine.preview_action(
        company_id="c1",
        user_id="u1",
        context_id="ctx1",
        capability="crm.note",
        operation="create",
        target={"service": "crm"},
        payload={"name": "n"},
        preview={"summary": "create"},
        risk="low",
    )
    with pytest.raises(PermissionError):
        await engine.reject_action(
            company_id="c1",
            user_id="u2",
            context_id="ctx1",
            pending_action_id=action["pending_action_id"],
        )
