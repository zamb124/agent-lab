"""Общие assert-хелперы для worktracker-тестов."""

from __future__ import annotations

from typing import Any


def assert_offset_page(payload: dict[str, Any]) -> None:
    assert "items" in payload
    assert "total" in payload
    assert "limit" in payload
    assert "offset" in payload
    assert isinstance(payload["items"], list)
    assert isinstance(payload["total"], int)
    assert isinstance(payload["limit"], int)
    assert isinstance(payload["offset"], int)


def assert_work_item_json(payload: dict[str, Any]) -> None:
    assert isinstance(payload.get("work_item_id"), str)
    assert isinstance(payload.get("title"), str)
    assert isinstance(payload.get("state"), str)
    assert isinstance(payload.get("kind"), str)
    assert isinstance(payload.get("variables"), dict)
    assert isinstance(payload.get("attachments"), list)


def assert_file_ref_json(payload: dict[str, Any]) -> None:
    assert isinstance(payload.get("file_id"), str)
    assert isinstance(payload.get("original_name"), str)
    assert isinstance(payload.get("content_type"), str)
    assert isinstance(payload.get("file_size"), int)
    assert isinstance(payload.get("url"), str)
