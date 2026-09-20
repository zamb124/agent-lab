"""Пустой payload для op с обязательными полями — ws_invalid_payload."""

from __future__ import annotations

import pytest

from apps.worktracker.realtime.command_router import WORKTRACKER_OPERATIONS
from core.websocket import WsCommandError, validate_ws_payload

_NO_REQUIRED_FIELDS_OPS: frozenset[str] = frozenset(
    {
        "worktracker/work_items/list_requested",
        "worktracker/work_items/mine_summary_requested",
        "worktracker/boards/list_requested",
        "worktracker/work_queues/list_requested",
    }
)

_OPS_WITH_REQUIRED_FIELDS: list[str] = sorted(
    op for op in WORKTRACKER_OPERATIONS if op not in _NO_REQUIRED_FIELDS_OPS
)


@pytest.mark.parametrize("canonical_type", _OPS_WITH_REQUIRED_FIELDS)
def test_op_empty_payload_raises_ws_invalid_payload(canonical_type: str) -> None:
    operation = WORKTRACKER_OPERATIONS[canonical_type]
    with pytest.raises(WsCommandError) as exc_info:
        validate_ws_payload(operation.payload_model, {})
    assert exc_info.value.code == "ws_invalid_payload"


@pytest.mark.parametrize("canonical_type", sorted(_NO_REQUIRED_FIELDS_OPS))
def test_op_empty_payload_valid_when_all_fields_optional(canonical_type: str) -> None:
    operation = WORKTRACKER_OPERATIONS[canonical_type]
    parsed = validate_ws_payload(operation.payload_model, {})
    assert parsed is not None
