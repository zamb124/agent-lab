"""Разбор REST envelope в код выхода CLI."""

from __future__ import annotations

from platform_sdk.errors import error_from_envelope


def test_conflict_envelope_exits_6() -> None:
    error = error_from_envelope(
        409,
        {
            "error_code": "flow_version_conflict",
            "error_detail": "flow version conflict",
            "error_params": {"current_version": "1"},
            "request_id": "req",
            "trace_id": "trace",
        },
    )
    assert error.exit_code == 6
    assert error.error_code == "flow_version_conflict"
    assert error.hint is not None
    assert error.payload()["request_id"] == "req"
