"""Deterministic, task-scoped A2UI representation negotiation."""

from __future__ import annotations

from collections.abc import Iterable

from core.a2a import (
    A2UI_EXTENSION_URI,
    A2UI_MIME_TYPE,
    A2UI_PLATFORM_CATALOG_ID,
    A2ARepresentation,
    A2ARepresentationSnapshot,
    parse_a2a_extensions_header,
)
from core.a2ui import DEFAULT_A2UI_CODEC_REGISTRY
from core.types import JsonObject


def _mime_allows_a2ui(accepted_output_modes: Iterable[str]) -> bool:
    modes = {item.strip().lower() for item in accepted_output_modes if item.strip()}
    if not modes:
        return True
    return bool(
        modes.intersection(
            {
                "*/*",
                "application/*",
                A2UI_MIME_TYPE,
            }
        )
    )


class A2ARepresentationSelector:
    """Select once before Task creation; callers persist the returned snapshot."""

    def select(
        self,
        *,
        activated_extensions: Iterable[str],
        message_metadata: JsonObject,
        accepted_output_modes: Iterable[str] = (),
    ) -> A2ARepresentationSnapshot:
        activated = tuple(dict.fromkeys(item.strip() for item in activated_extensions if item.strip()))
        if A2UI_EXTENSION_URI not in activated or not _mime_allows_a2ui(
            accepted_output_modes
        ):
            return A2ARepresentationSnapshot(
                negotiated_extensions=[],
            )

        codec = DEFAULT_A2UI_CODEC_REGISTRY.get(A2UI_EXTENSION_URI)
        try:
            _ = codec.validate_client_capabilities(
                message_metadata,
                required_catalog_id=A2UI_PLATFORM_CATALOG_ID,
            )
        except (TypeError, ValueError):
            return A2ARepresentationSnapshot(
                negotiated_extensions=[],
            )

        return A2ARepresentationSnapshot(
            representation=A2ARepresentation.A2UI_0_9_1,
            negotiated_extensions=[A2UI_EXTENSION_URI],
            extension_uri=A2UI_EXTENSION_URI,
            catalog_id=A2UI_PLATFORM_CATALOG_ID,
            output_mime_type=A2UI_MIME_TYPE,
        )


__all__ = ["A2ARepresentationSelector", "parse_a2a_extensions_header"]
