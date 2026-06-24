"""HTTP REST /worktracker/api/v1/boards."""

from __future__ import annotations

import pytest

from tests.worktracker.conftest import API_PREFIX
from tests.worktracker.helpers.assertions import assert_offset_page
from tests.worktracker.helpers.builders import build_board_payload

pytestmark = pytest.mark.asyncio

BOARDS = f"{API_PREFIX}/boards"


async def test_list_and_filter_boards_by_namespace(worktracker_client, unique_id: str) -> None:
    namespace = f"ns-{unique_id}"
    create_resp = await worktracker_client.post(
        BOARDS,
        json=build_board_payload(unique_id, namespace=namespace),
    )
    assert create_resp.status_code == 201

    all_boards = await worktracker_client.get(BOARDS)
    assert all_boards.status_code == 200
    assert_offset_page(all_boards.json())

    filtered = await worktracker_client.get(BOARDS, params={"namespace": namespace})
    assert filtered.status_code == 200
    ids = {item["board_id"] for item in filtered.json()["items"]}
    assert create_resp.json()["board_id"] in ids


async def test_get_board_happy_and_404(worktracker_client, worktracker_board) -> None:
    board_id = worktracker_board.board_id
    get_resp = await worktracker_client.get(f"{BOARDS}/{board_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["board_id"] == board_id

    missing = await worktracker_client.get(f"{BOARDS}/board_missing_999")
    assert missing.status_code == 404


async def test_create_board_custom_columns(worktracker_client, unique_id: str) -> None:
    response = await worktracker_client.post(
        BOARDS,
        json=build_board_payload(unique_id),
    )
    assert response.status_code == 201
    body = response.json()
    column_ids = {col["board_column_id"] for col in body["columns"]}
    assert column_ids == {"todo", "done"}


async def test_update_board_columns(worktracker_client, worktracker_board, unique_id: str) -> None:
    board_id = worktracker_board.board_id
    response = await worktracker_client.patch(
        f"{BOARDS}/{board_id}",
        json={
            "name": f"Updated board {unique_id}",
            "columns": [
                {
                    "board_column_id": "todo",
                    "label": "Backlog",
                    "state": "open",
                    "position": 0,
                },
                {
                    "board_column_id": "wip",
                    "label": "WIP",
                    "state": "in_progress",
                    "position": 1,
                },
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == f"Updated board {unique_id}"
    assert len(body["columns"]) == 2

    missing = await worktracker_client.patch(
        f"{BOARDS}/board_missing_999",
        json={"name": "x"},
    )
    assert missing.status_code == 404
