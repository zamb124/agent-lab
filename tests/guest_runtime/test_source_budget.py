from __future__ import annotations

import pytest

from core.guest_runtime.source_budget import assert_source_bytes_within_cap


def test_assert_source_bytes_within_cap_accepts_equal_limit() -> None:
    assert_source_bytes_within_cap(existing_bytes=10, incoming_bytes=10, max_bytes=20)


def test_assert_source_bytes_within_cap_rejects_overflow() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        assert_source_bytes_within_cap(existing_bytes=10, incoming_bytes=11, max_bytes=20)
