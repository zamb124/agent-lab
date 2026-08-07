"""Canonical Linnex identities for optional A2UI over standard A2A Parts."""

from __future__ import annotations

from collections.abc import Mapping

from core.config.base import PLATFORM_DEFAULT_APEX
from core.types import JsonObject, JsonValue, require_json_object

A2A_EXTENSIONS_HEADER = "A2A-Extensions"
A2UI_EXTENSION_URI = "https://a2ui.org/a2a-extension/a2ui/v0.9.1"
# Catalog identity is derived from the primary apex only, never from request Host.
A2UI_PLATFORM_CATALOG_ID = f"https://{PLATFORM_DEFAULT_APEX}/a2ui/catalog/platform/v1"
A2UI_BASIC_CATALOG_ID = "https://a2ui.org/specification/v0_9_1/catalogs/basic/catalog.json"
A2UI_VERSION = "v0.9.1"
A2UI_MIME_TYPE = "application/a2ui+json"
A2UI_VERSIONED_MIME_TYPE = "application/vnd.a2ui+json;version=0.9.1"
A2UI_DATA_KEY = "a2ui"
PLATFORM_UI_SUBMIT_ACTION = "platform.ui.submit"
PLATFORM_UI_SYNC_ACTION = "platform.ui.sync"
PLATFORM_UI_BOOTSTRAP_ACTION = "platform.ui.bootstrap"
PLATFORM_UI_METADATA_KEY = "platformUi"
PLATFORM_SUBSCRIBE_AFTER_SEQUENCE_KEY = "afterSequence"


def is_a2ui_media_type(value: str) -> bool:
    return value.strip().lower() in {A2UI_MIME_TYPE, A2UI_VERSIONED_MIME_TYPE}


def parse_a2a_extensions_header(value: str | None) -> tuple[str, ...]:
    """Parse comma-separated ``A2A-Extensions`` activation URIs; order preserved."""
    if value is None:
        return ()
    ordered: list[str] = []
    seen: set[str] = set()
    for item in value.split(","):
        uri = item.strip()
        if not uri or uri in seen:
            continue
        ordered.append(uri)
        seen.add(uri)
    return tuple(ordered)


def extract_subscribe_after_sequence(params: Mapping[str, JsonValue]) -> int:
    """Read platform reconnect cursor from SubscribeToTask params metadata.

    Wire shape (not part of official SubscribeToTaskRequest protobuf)::

        params.metadata.platformUi.afterSequence

    Missing metadata means ``0`` (replay from the beginning of the ledger).
    """
    metadata_raw = params.get("metadata")
    if metadata_raw is None:
        return 0
    metadata = require_json_object(metadata_raw, "SubscribeToTask.params.metadata")
    platform_ui_raw = metadata.get(PLATFORM_UI_METADATA_KEY)
    if platform_ui_raw is None:
        return 0
    platform_ui = require_json_object(
        platform_ui_raw,
        "SubscribeToTask.params.metadata.platformUi",
    )
    after_sequence = platform_ui.get(PLATFORM_SUBSCRIBE_AFTER_SEQUENCE_KEY)
    if after_sequence is None:
        return 0
    if (
        not isinstance(after_sequence, int)
        or isinstance(after_sequence, bool)
        or after_sequence < 0
    ):
        raise ValueError(
            "SubscribeToTask metadata.platformUi.afterSequence must be a non-negative int"
        )
    return after_sequence


def strip_subscribe_platform_metadata(params: Mapping[str, JsonValue]) -> JsonObject:
    """Drop platform-only metadata before protobuf ParseDict of SubscribeToTask."""
    return {key: value for key, value in params.items() if key != "metadata"}


__all__ = [
    "A2A_EXTENSIONS_HEADER",
    "A2UI_BASIC_CATALOG_ID",
    "A2UI_DATA_KEY",
    "A2UI_EXTENSION_URI",
    "A2UI_MIME_TYPE",
    "A2UI_PLATFORM_CATALOG_ID",
    "A2UI_VERSION",
    "A2UI_VERSIONED_MIME_TYPE",
    "PLATFORM_SUBSCRIBE_AFTER_SEQUENCE_KEY",
    "PLATFORM_UI_BOOTSTRAP_ACTION",
    "PLATFORM_UI_METADATA_KEY",
    "PLATFORM_UI_SUBMIT_ACTION",
    "PLATFORM_UI_SYNC_ACTION",
    "extract_subscribe_after_sequence",
    "is_a2ui_media_type",
    "parse_a2a_extensions_header",
    "strip_subscribe_platform_metadata",
]
