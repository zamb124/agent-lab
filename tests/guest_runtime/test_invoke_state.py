from __future__ import annotations

import pytest

from apps.guest_runtime.services.farm_service import _guest_state_from_invoke


def test_guest_state_from_extra_keys() -> None:
    payload = {"text": "hello", "echo_ticket": "t-1", "ok": True}
    assert _guest_state_from_invoke(payload) == {"echo_ticket": "t-1", "ok": True}


def test_guest_state_from_state_object() -> None:
    payload = {"text": "hello", "state": {"echo_ticket": "t-1"}}
    assert _guest_state_from_invoke(payload) == {"echo_ticket": "t-1"}


def test_guest_state_merges_state_and_extras() -> None:
    payload = {"text": "hello", "state": {"a": 1}, "b": 2}
    assert _guest_state_from_invoke(payload) == {"a": 1, "b": 2}


def test_guest_state_overlap_raises() -> None:
    with pytest.raises(ValueError, match="overlaps extra keys"):
        _guest_state_from_invoke({"text": "hello", "state": {"a": 1}, "a": 2})
