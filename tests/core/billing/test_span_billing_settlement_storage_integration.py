"""
SpanBillingSettlement: реальный shared storage, без моков.
"""

from __future__ import annotations

import json

import pytest

from core.billing.span_billing_settlement import SpanBillingSettlement


@pytest.mark.asyncio
async def test_composite_mark_and_get(frontend_container, unique_id: str) -> None:
    st = SpanBillingSettlement(frontend_container.shared_storage)
    sid = f"ss_{unique_id}"
    rid = f"rr_{unique_id}"
    uid = f"usage_{unique_id}"
    assert await st.get_usage_id(sid, rid) is None
    await st.mark(sid, rid, uid)
    assert await st.get_usage_id(sid, rid) == uid
    raw = await frontend_container.shared_storage.get(f"billing:settled:{sid}:{rid}", force_global=True)
    assert raw == uid or json.loads(raw) == uid


@pytest.mark.asyncio
async def test_get_usage_id_composite_invalid_json_raises(frontend_container, unique_id: str) -> None:
    st = SpanBillingSettlement(frontend_container.shared_storage)
    sid = f"bad_{unique_id}"
    rid = f"r_{unique_id}"
    key = f"billing:settled:{sid}:{rid}"
    await frontend_container.shared_storage.set(key, "[1,2]", force_global=True)
    with pytest.raises(ValueError, match="ожидалась строка usage_id"):
        await st.get_usage_id(sid, rid)


@pytest.mark.asyncio
async def test_span_only_key_is_not_read(frontend_container, unique_id: str) -> None:
    st = SpanBillingSettlement(frontend_container.shared_storage)
    sid = f"span_only_{unique_id}"
    await frontend_container.shared_storage.set(f"billing:settled_span:{sid}", json.dumps("u"), force_global=True)
    assert await st.get_usage_id(sid, "rule") is None
