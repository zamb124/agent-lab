"""Unit: A2A-Extensions header and Subscribe afterSequence metadata."""

from __future__ import annotations

import pytest

from core.a2a.extensions import (
    A2A_EXTENSIONS_HEADER,
    A2UI_EXTENSION_URI,
    extract_subscribe_after_sequence,
    parse_a2a_extensions_header,
    strip_subscribe_platform_metadata,
)


def test_a2a_extensions_header_constant() -> None:
    assert A2A_EXTENSIONS_HEADER == "A2A-Extensions"


def test_parse_a2a_extensions_header_order_and_dedupe() -> None:
    assert parse_a2a_extensions_header(
        f" {A2UI_EXTENSION_URI}, https://example.test/ext, {A2UI_EXTENSION_URI} "
    ) == (A2UI_EXTENSION_URI, "https://example.test/ext")
    assert parse_a2a_extensions_header(None) == ()
    assert parse_a2a_extensions_header("  , , ") == ()


def test_extract_subscribe_after_sequence_from_platform_ui() -> None:
    assert extract_subscribe_after_sequence({}) == 0
    assert (
        extract_subscribe_after_sequence(
            {"metadata": {"platformUi": {"afterSequence": 12}}}
        )
        == 12
    )
    # The cursor lives only under platformUi; a bare top-level key is ignored.
    assert extract_subscribe_after_sequence({"metadata": {"afterSequence": 3}}) == 0
    with pytest.raises(ValueError, match="non-negative int"):
        _ = extract_subscribe_after_sequence(
            {"metadata": {"platformUi": {"afterSequence": -1}}}
        )


def test_strip_subscribe_platform_metadata_keeps_proto_fields() -> None:
    stripped = strip_subscribe_platform_metadata(
        {"id": "task-1", "tenant": "acme", "metadata": {"platformUi": {"afterSequence": 1}}}
    )
    assert stripped == {"id": "task-1", "tenant": "acme"}
