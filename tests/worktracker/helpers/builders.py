"""Payload builders для HTTP API worktracker."""

from __future__ import annotations

from typing import Any


def build_manual_work_item_payload(
    unique_id: str,
    *,
    title: str | None = None,
    variables: dict[str, Any] | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": title if title is not None else f"Task {unique_id}",
    }
    if variables is not None:
        payload["variables"] = variables
    if attachments is not None:
        payload["attachments"] = attachments
    return payload


def build_queue_payload(unique_id: str, *, name: str | None = None) -> dict[str, str]:
    return {
        "name": name if name is not None else f"Queue {unique_id}",
        "slug": f"q-{unique_id}",
    }


def build_board_payload(unique_id: str, *, namespace: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": f"Board {unique_id}",
        "columns": [
            {
                "board_column_id": "todo",
                "label": "To do",
                "state": "open",
                "position": 0,
            },
            {
                "board_column_id": "done",
                "label": "Done",
                "state": "done",
                "position": 1,
            },
        ],
    }
    if namespace is not None:
        payload["namespace"] = namespace
    return payload


def build_queue_assignment(work_queue_id: str) -> dict[str, Any]:
    return {
        "assignment": {
            "assignee_kind": "queue",
            "work_queue_id": work_queue_id,
        }
    }


def build_users_assignment(user_id: str) -> dict[str, Any]:
    return {
        "assignment": {
            "assignee_kind": "users",
            "user_ids": [user_id],
        }
    }
