"""API tests for tool preview and contract endpoints."""

from __future__ import annotations


async def test_tools_preview_masks_secrets_and_returns_model_view(client, app) -> None:
    response = await client.post(
        "/flows/api/v1/tools/preview",
        json={
            "tool_id": "wiki_get_page",
            "model_args": {
                "wiki_page_id": "p1",
                "api_token": "super-secret",
            },
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    model_view = body["model_view"]
    assert model_view["name"] == "wiki_get_page"
    assert isinstance(model_view["description"], str)
    assert model_view["parameters"]["type"] == "object"
    assert model_view["parameters"]["additionalProperties"] is False

    plan = body["execution_plan"]
    assert plan["tool_id"] == "wiki_get_page"
    assert "read" in plan["effects"]
    assert plan["resolved_args_masked"]["wiki_page_id"] == "p1"
    assert plan["resolved_args_masked"]["api_token"] == "***"
    assert plan["requires_approval"] is False


async def test_tools_preview_unknown_tool_returns_404(client, app) -> None:
    response = await client.post(
        "/flows/api/v1/tools/preview",
        json={"tool_id": "definitely_missing_tool_xyz"},
    )
    assert response.status_code == 404


async def test_tools_contract_returns_definition_shape(client, app) -> None:
    response = await client.get("/flows/api/v1/tools/wiki_create_page/contract")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["definition_id"] == "wiki_create_page"
    assert body["machine_name"] == "wiki_create_page"
    assert body["executor_kind"] == "trusted_builtin"
    assert "create" in body["effects"]
    assert body["confirmation_floor"] == "preview"
    assert body["canonical_input_schema"]["type"] == "object"


async def test_get_builtin_tool_includes_contract_fields(client, app) -> None:
    response = await client.get("/flows/api/v1/tools/wiki_create_page")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tool_id"] == "wiki_create_page"
    assert body["builtin"] is True
    assert "create" in body["effects"]
    assert body["confirmation_floor"] == "preview"
    assert isinstance(body["parameters_schema"], dict)


async def test_tools_all_builtin_includes_effects(client, app) -> None:
    response = await client.get(
        "/flows/api/v1/tools/all?picker_category=code&limit=20&offset=0&q=wiki_create_page"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    matches = [item for item in body["items"] if item["tool_id"] == "wiki_create_page"]
    assert len(matches) == 1
    item = matches[0]
    assert item["builtin"] is True
    assert "create" in item["effects"]
    assert item["confirmation_floor"] == "preview"
