"""HTTP contract: shared resources catalog `/flows/api/v1/resources`."""

from __future__ import annotations

import pytest


def _llm_resource(resource_id: str, *, name: str) -> dict[str, object]:
    return {
        "resource_id": resource_id,
        "type": "llm",
        "name": name,
        "config": {"provider": "openrouter", "model": "openai/gpt-4o"},
    }


@pytest.mark.asyncio
async def test_resource_crud_llm(client, unique_id: str) -> None:
    resource_id = f"res_{unique_id}"
    created = await client.post("/flows/api/v1/resources", json=_llm_resource(resource_id, name="Test LLM"))
    assert created.status_code == 200, created.text
    assert created.json()["resource_id"] == resource_id
    assert created.json()["name"] == "Test LLM"

    found = False
    offset = 0
    while True:
        listed = await client.get(
            "/flows/api/v1/resources",
            params={"limit": 1000, "offset": offset},
        )
        assert listed.status_code == 200, listed.text
        items = listed.json()["items"]
        if any(item["resource_id"] == resource_id for item in items):
            found = True
            break
        if len(items) < 1000:
            break
        offset += 1000
    assert found

    fetched = await client.get(f"/flows/api/v1/resources/{resource_id}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["config"]["provider"] == "openrouter"

    updated = await client.put(
        f"/flows/api/v1/resources/{resource_id}",
        json={"name": "Renamed LLM"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Renamed LLM"
    assert updated.json()["config"]["model"] == "openai/gpt-4o"

    removed = await client.delete(f"/flows/api/v1/resources/{resource_id}")
    assert removed.status_code == 200, removed.text
    assert removed.json() == {"status": "deleted", "resource_id": resource_id}

    missing = await client.get(f"/flows/api/v1/resources/{resource_id}")
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_resource_create_conflict_is_409(client, unique_id: str) -> None:
    resource_id = f"res_dup_{unique_id}"
    first = await client.post("/flows/api/v1/resources", json=_llm_resource(resource_id, name="One"))
    assert first.status_code == 200, first.text
    second = await client.post("/flows/api/v1/resources", json=_llm_resource(resource_id, name="Two"))
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_resource_unknown_is_404(client, unique_id: str) -> None:
    resource_id = f"res_missing_{unique_id}"
    fetched = await client.get(f"/flows/api/v1/resources/{resource_id}")
    assert fetched.status_code == 404
    updated = await client.put(
        f"/flows/api/v1/resources/{resource_id}",
        json={"name": "Nope"},
    )
    assert updated.status_code == 404
