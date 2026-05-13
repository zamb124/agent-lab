from __future__ import annotations

import asyncio

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

    async def set_nx(self, key: str, value: str, ttl_seconds: int) -> bool:
        _ = ttl_seconds
        if key in self._store:
            return False
        self._store[key] = value
        return True

    async def delete(self, *keys: str) -> int:
        n = 0
        for k in keys:
            if k in self._store:
                del self._store[k]
                n += 1
        return n


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
async def test_apply_rejects_wrong_idempotency_key_when_previewed() -> None:
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
        idempotency_key="golden",
    )
    pending_action_id = action["pending_action_id"]
    with pytest.raises(ValueError, match="idempotency_key mismatch"):
        await engine.apply_action(
            company_id="c1",
            user_id="u1",
            context_id="ctx1",
            pending_action_id=pending_action_id,
            idempotency_key="wrong",
            apply_fn=_apply_ok,
        )


@pytest.mark.asyncio
async def test_reject_action_marks_previewed_as_rejected() -> None:
    redis = InMemoryRedis()
    engine = LaraActionEngine(redis_client=redis, ttl_seconds=60)
    action = await engine.preview_action(
        company_id="c1",
        user_id="u1",
        context_id="ctx1",
        capability="crm.note",
        operation="create",
        target={"service": "crm"},
        payload={"name": "x"},
        preview={"summary": "x"},
        risk="low",
    )
    out = await engine.reject_action(
        company_id="c1",
        user_id="u1",
        context_id="ctx1",
        pending_action_id=action["pending_action_id"],
        reason="cancelled-by-test",
    )
    assert out["status"] == "rejected"


@pytest.mark.asyncio
async def test_apply_already_applied_rejects_wrong_idempotency_key() -> None:
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
        idempotency_key="golden",
    )
    pending_action_id = action["pending_action_id"]
    await engine.apply_action(
        company_id="c1",
        user_id="u1",
        context_id="ctx1",
        pending_action_id=pending_action_id,
        idempotency_key="golden",
        apply_fn=lambda _: _apply_ok(),
    )
    async def apply_should_fail() -> dict[str, bool]:
        raise AssertionError("apply_fn must not run when idempotency already applied")

    with pytest.raises(ValueError, match="idempotency_key mismatch for already applied"):
        await engine.apply_action(
            company_id="c1",
            user_id="u1",
            context_id="ctx1",
            pending_action_id=pending_action_id,
            idempotency_key="wrong-after-apply",
            apply_fn=apply_should_fail,
        )


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


@pytest.mark.asyncio
async def test_concurrent_apply_invokes_effect_once() -> None:
    redis = InMemoryRedis()
    engine = LaraActionEngine(redis_client=redis)
    gate = asyncio.Event()
    blocker = asyncio.Event()
    counts = {"n": 0}

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
        idempotency_key="golden",
    )
    pid = action["pending_action_id"]

    async def slow_apply(_: dict) -> dict[str, bool]:
        counts["n"] += 1
        gate.set()
        await blocker.wait()
        return {"ok": True}

    async def run_apply() -> dict:
        return await engine.apply_action(
            company_id="c1",
            user_id="u1",
            context_id="ctx1",
            pending_action_id=pid,
            idempotency_key="golden",
            apply_fn=slow_apply,
        )

    t_a = asyncio.create_task(run_apply())
    t_b = asyncio.create_task(run_apply())
    await asyncio.wait_for(gate.wait(), timeout=2)
    blocker.set()
    out_a, out_b = await asyncio.gather(t_a, t_b)
    assert counts["n"] == 1
    assert out_a["status"] == "applied"
    assert out_b["status"] == "applied"
    assert out_b["result"]["ok"] is True
