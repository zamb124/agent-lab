"""POST /flow-ui/assist: structured output LLM по грамматике блоков, проверка запроса и ответа модели."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from core.types import JsonObject

ASSIST_URL = "/flows/api/v1/flow-ui/assist"


def _document() -> JsonObject:
    return {
        "start_page_id": "main",
        "pages": [
            {
                "page_id": "main",
                "title": "Заявка",
                "blocks": [
                    {"block_id": "title", "type": "heading", "text": "Заявка", "level": 2},
                    {"block_id": "email", "type": "text_input", "field": "email", "label": "Email"},
                    {
                        "block_id": "send",
                        "type": "button",
                        "label": "Отправить",
                        "action": {"name": "submit", "payload": {}},
                    },
                ],
            }
        ],
    }


def _request(*, flow_id: str, block_id: str | None = None, page_id: str = "main") -> JsonObject:
    body: JsonObject = {
        "flow_id": flow_id,
        "branch_id": "default",
        "instruction": "Добавь поле телефона",
        "document": _document(),
        "page_id": page_id,
    }
    if block_id is not None:
        body["block_id"] = block_id
    return body


@pytest.mark.asyncio
async def test_assist_describe_page_returns_llm_page(
    flows_client: AsyncClient, embed_test_auth, mock_llm_with_queue
):
    auth_headers, flow_id, _, _ = embed_test_auth
    page: JsonObject = {
        "page_id": "main",
        "title": "Заявка",
        "blocks": [
            {"block_id": "title", "type": "heading", "text": "Заявка", "level": 2},
            {"block_id": "email", "type": "text_input", "field": "email", "label": "Email"},
            {"block_id": "phone", "type": "text_input", "field": "phone", "label": "Телефон"},
            {
                "block_id": "send",
                "type": "button",
                "label": "Отправить",
                "action": {"name": "submit", "payload": {}},
            },
        ],
    }
    mock_llm_with_queue([{"type": "structured_output", "data": page}])

    response = await flows_client.post(
        ASSIST_URL, headers=auth_headers, json=_request(flow_id=flow_id)
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["scope"] == "page"
    assert payload["blocks"] == []
    assert [block["block_id"] for block in payload["page"]["blocks"]] == [
        "title",
        "email",
        "phone",
        "send",
    ]
    assert payload["page"]["blocks"][2]["type"] == "text_input"


@pytest.mark.asyncio
async def test_assist_rewrite_block_returns_replacement_blocks(
    flows_client: AsyncClient, embed_test_auth, mock_llm_with_queue
):
    auth_headers, flow_id, _, _ = embed_test_auth
    mock_llm_with_queue(
        [
            {
                "type": "structured_output",
                "data": {
                    "blocks": [
                        {
                            "block_id": "email",
                            "type": "text_input",
                            "field": "email",
                            "label": "Рабочий email",
                        },
                        {
                            "block_id": "phone",
                            "type": "text_input",
                            "field": "phone",
                            "label": "Телефон",
                        },
                    ]
                },
            }
        ]
    )

    response = await flows_client.post(
        ASSIST_URL, headers=auth_headers, json=_request(flow_id=flow_id, block_id="email")
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["scope"] == "block"
    assert payload["page"] is None
    assert [block["block_id"] for block in payload["blocks"]] == ["email", "phone"]


@pytest.mark.asyncio
async def test_assist_rejects_page_id_change_and_block_id_collision(
    flows_client: AsyncClient, embed_test_auth, mock_llm_with_queue
):
    auth_headers, flow_id, _, _ = embed_test_auth
    mock_llm_with_queue(
        [
            {"type": "structured_output", "data": {"page_id": "other", "title": "", "blocks": []}},
            {
                "type": "structured_output",
                "data": {
                    "blocks": [
                        {"block_id": "send", "type": "text", "markdown": "collides with the button"}
                    ]
                },
            },
        ]
    )

    renamed = await flows_client.post(
        ASSIST_URL, headers=auth_headers, json=_request(flow_id=flow_id)
    )
    assert renamed.status_code == 502, renamed.text
    assert renamed.json()["error_code"] == "upstream"
    assert "page_id changed to 'other'" in renamed.json()["detail"]

    collision = await flows_client.post(
        ASSIST_URL, headers=auth_headers, json=_request(flow_id=flow_id, block_id="email")
    )
    assert collision.status_code == 502, collision.text
    assert collision.json()["error_code"] == "upstream"
    assert "block_id 'send' collides" in collision.json()["detail"]


@pytest.mark.asyncio
async def test_assist_validates_page_and_block_against_document(
    flows_client: AsyncClient, embed_test_auth
):
    auth_headers, flow_id, _, _ = embed_test_auth

    unknown_page = await flows_client.post(
        ASSIST_URL, headers=auth_headers, json=_request(flow_id=flow_id, page_id="missing")
    )
    assert unknown_page.status_code == 422, unknown_page.text
    assert "is not in the document" in unknown_page.text

    unknown_block = await flows_client.post(
        ASSIST_URL, headers=auth_headers, json=_request(flow_id=flow_id, block_id="ghost")
    )
    assert unknown_block.status_code == 422, unknown_block.text
    assert "is not on page" in unknown_block.text


@pytest.mark.asyncio
async def test_assist_requires_authentication(flows_client: AsyncClient):
    response = await flows_client.post(ASSIST_URL, json=_request(flow_id="missing-live-flow"))
    assert response.status_code == 401, response.text
