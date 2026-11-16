"""Обновление flow сверяет base_version, только если поле передано."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


def _body(flow_id: str, name: str) -> dict[str, object]:
    return {
        "flow_id": flow_id,
        "name": name,
        "entry": "main",
        "nodes": {"main": {"type": "llm_node", "prompt": name, "tools": []}},
        "edges": [{"from_node": "main", "to_node": None}],
    }


async def test_update_without_base_version_overwrites(client, unique_id: str) -> None:
    flow_id = f"base_optional_{unique_id}"
    created = await client.post("/flows/api/v1/flows/", json=_body(flow_id, "first"))
    assert created.status_code == 200, created.text
    updated = await client.put(f"/flows/api/v1/flows/{flow_id}", json=_body(flow_id, "second"))
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "second"
    await client.delete(f"/flows/api/v1/flows/{flow_id}")


async def test_update_with_stale_base_version_conflicts(client, unique_id: str) -> None:
    flow_id = f"base_stale_{unique_id}"
    created = await client.post("/flows/api/v1/flows/", json=_body(flow_id, "first"))
    assert created.status_code == 200, created.text
    current = created.json()["version"]
    moved = await client.put(
        f"/flows/api/v1/flows/{flow_id}",
        json={**_body(flow_id, "second"), "base_version": current},
    )
    assert moved.status_code == 200, moved.text
    stale = await client.put(
        f"/flows/api/v1/flows/{flow_id}",
        json={**_body(flow_id, "third"), "base_version": current},
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["error_code"] == "flow_version_conflict"
    await client.delete(f"/flows/api/v1/flows/{flow_id}")
