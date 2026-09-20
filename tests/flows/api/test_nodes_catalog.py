"""HTTP contract: company NodeConfig catalog `/flows/api/v1/nodes`."""

from __future__ import annotations

import pytest


def _llm_node(node_id: str, *, name: str, prompt: str) -> dict[str, object]:
    return {
        "node_id": node_id,
        "type": "llm_node",
        "name": name,
        "description": "catalog node",
        "prompt": prompt,
    }


@pytest.mark.asyncio
async def test_nodes_catalog_crud(client, unique_id: str) -> None:
    node_id = f"node_{unique_id}"
    created = await client.post("/flows/api/v1/nodes", json=_llm_node(node_id, name="Echo", prompt="hi"))
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["node_id"] == node_id
    assert body["name"] == "Echo"
    assert body["type"] == "llm_node"
    assert body["prompt"] == "hi"
    assert body["local_variables"] == {}
    assert "variables" not in body

    listed = await client.get("/flows/api/v1/nodes")
    assert listed.status_code == 200, listed.text
    assert any(item["node_id"] == node_id for item in listed.json()["items"])

    fetched = await client.get(f"/flows/api/v1/nodes/{node_id}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["prompt"] == "hi"

    updated = await client.put(
        f"/flows/api/v1/nodes/{node_id}",
        json=_llm_node(node_id, name="Renamed", prompt="hello"),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Renamed"
    assert updated.json()["prompt"] == "hello"

    removed = await client.delete(f"/flows/api/v1/nodes/{node_id}")
    assert removed.status_code == 200, removed.text
    assert removed.json() == {"status": "deleted", "node_id": node_id}

    missing = await client.get(f"/flows/api/v1/nodes/{node_id}")
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_nodes_catalog_create_conflict_is_409(client, unique_id: str) -> None:
    node_id = f"node_dup_{unique_id}"
    first = await client.post("/flows/api/v1/nodes", json=_llm_node(node_id, name="One", prompt="a"))
    assert first.status_code == 200, first.text
    second = await client.post("/flows/api/v1/nodes", json=_llm_node(node_id, name="Two", prompt="b"))
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_nodes_catalog_unknown_is_404(client, unique_id: str) -> None:
    node_id = f"node_missing_{unique_id}"
    fetched = await client.get(f"/flows/api/v1/nodes/{node_id}")
    assert fetched.status_code == 404
    updated = await client.put(
        f"/flows/api/v1/nodes/{node_id}",
        json=_llm_node(node_id, name="Nope", prompt="x"),
    )
    assert updated.status_code == 404
    removed = await client.delete(f"/flows/api/v1/nodes/{node_id}")
    assert removed.status_code == 404


@pytest.mark.asyncio
async def test_nodes_catalog_unknown_tool_is_400(client, unique_id: str) -> None:
    node_id = f"node_tool_{unique_id}"
    created = await client.post(
        "/flows/api/v1/nodes",
        json={
            **_llm_node(node_id, name="With tool", prompt="hi"),
            "tools": [{"tool_id": f"missing_tool_{unique_id}"}],
        },
    )
    assert created.status_code == 400, created.text
    assert "not found" in created.json()["detail"]
