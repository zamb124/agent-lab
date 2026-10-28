"""HTTP contract: POST /flows/api/v1/llm-context/resolve-parent."""

from __future__ import annotations

import pytest

from apps.flows.src.models.resource import ResourceDefinition, ResourceType


@pytest.mark.asyncio
async def test_resolve_parent_returns_platform_defaults(client, unique_id):
    _ = unique_id
    response = await client.post(
        "/flows/api/v1/llm-context/resolve-parent",
        json={
            "llm_context_resource_key": None,
            "flow_resources": {},
            "node_resources": {},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["resolved"], dict)
    assert isinstance(body["profiles"], list)
    assert len(body["profiles"]) > 0
    assert isinstance(body["budgets"], list)
    assert len(body["budgets"]) > 0
    assert isinstance(body["resolved"].get("profile"), str)
    assert body["resolved"]["profile"] in body["profiles"]
    assert "mode" in body["resolved"]
    assert "memory" in body["resolved"]
    assert "retrieval" in body["resolved"]
    assert "budget" in body["resolved"]


@pytest.mark.asyncio
async def test_resolve_parent_applies_inline_resource(client, unique_id):
    response = await client.post(
        "/flows/api/v1/llm-context/resolve-parent",
        json={
            "llm_context_resource_key": "ctx",
            "flow_resources": {
                "ctx": {
                    "type": "llm_context",
                    "config": {
                        "memory": "session",
                        "retrieval": {"mode": "hybrid", "top_k": 17},
                    },
                },
            },
            "node_resources": {},
        },
    )
    assert response.status_code == 200, response.text
    resolved = response.json()["resolved"]
    assert resolved["memory"] == "session"
    assert resolved["retrieval"]["mode"] == "hybrid"
    assert resolved["retrieval"]["top_k"] == 17


@pytest.mark.asyncio
async def test_resolve_parent_applies_shared_resource(client, unique_id, di):
    resource_id = f"llm_ctx_{unique_id}"
    definition = ResourceDefinition(
        resource_id=resource_id,
        type=ResourceType.LLM_CONTEXT,
        name="Ctx",
        config={"memory": "off", "retrieval": {"mode": "off", "top_k": 3}},
    )
    await ResourceDefinition.set(definition)
    try:
        response = await client.post(
            "/flows/api/v1/llm-context/resolve-parent",
            json={
                "llm_context_resource_key": "ctx",
                "flow_resources": {
                    "ctx": {"resource_id": resource_id},
                },
                "node_resources": {},
            },
        )
        assert response.status_code == 200, response.text
        resolved = response.json()["resolved"]
        assert resolved["memory"] == "off"
        assert resolved["retrieval"]["mode"] == "off"
        assert resolved["retrieval"]["top_k"] == 3
    finally:
        await ResourceDefinition.delete_by_id(ResourceDefinition.resource_row_id_for_active_company(resource_id))


@pytest.mark.asyncio
async def test_resolve_parent_unknown_key_is_400(client, unique_id):
    _ = unique_id
    response = await client.post(
        "/flows/api/v1/llm-context/resolve-parent",
        json={
            "llm_context_resource_key": "missing_ctx",
            "flow_resources": {},
            "node_resources": {},
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_resolve_parent_empty_key_does_not_auto_infer(client, unique_id):
    """Без явного key — только platform+company, даже если в flow один context resource."""
    _ = unique_id
    with_key = await client.post(
        "/flows/api/v1/llm-context/resolve-parent",
        json={
            "llm_context_resource_key": "ctx",
            "flow_resources": {
                "ctx": {
                    "type": "llm_context",
                    "config": {"memory": "session", "retrieval": {"mode": "hybrid", "top_k": 99}},
                },
            },
            "node_resources": {},
        },
    )
    without_key = await client.post(
        "/flows/api/v1/llm-context/resolve-parent",
        json={
            "llm_context_resource_key": None,
            "flow_resources": {
                "ctx": {
                    "type": "llm_context",
                    "config": {"memory": "session", "retrieval": {"mode": "hybrid", "top_k": 99}},
                },
            },
            "node_resources": {},
        },
    )
    assert with_key.status_code == 200
    assert without_key.status_code == 200
    assert with_key.json()["resolved"]["retrieval"]["top_k"] == 99
    assert without_key.json()["resolved"]["retrieval"]["top_k"] != 99
