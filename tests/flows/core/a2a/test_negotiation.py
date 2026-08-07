from apps.flows.src.a2a.negotiation import A2ARepresentationSelector
from core.a2a import (
    A2UI_EXTENSION_URI,
    A2UI_MIME_TYPE,
    A2UI_PLATFORM_CATALOG_ID,
    A2ARepresentation,
    parse_a2a_extensions_header,
)


def _capabilities() -> dict[str, object]:
    return {
        "a2uiClientCapabilities": {
            "v0.9.1": {
                "supportedCatalogIds": [A2UI_PLATFORM_CATALOG_ID],
                "inlineCatalogs": [],
            }
        }
    }


def test_header_parser_is_ordered_and_deduplicated() -> None:
    assert parse_a2a_extensions_header(
        f" {A2UI_EXTENSION_URI}, https://example.test/ext, {A2UI_EXTENSION_URI} "
    ) == (A2UI_EXTENSION_URI, "https://example.test/ext")


def test_selector_negotiates_official_a2ui_data_part_representation() -> None:
    selected = A2ARepresentationSelector().select(
        activated_extensions=[A2UI_EXTENSION_URI],
        message_metadata=_capabilities(),
        accepted_output_modes=[A2UI_MIME_TYPE],
    )
    assert selected.representation == A2ARepresentation.A2UI_0_9_1
    assert selected.catalog_id == A2UI_PLATFORM_CATALOG_ID
    assert selected.negotiated_extensions == [A2UI_EXTENSION_URI]


def test_selector_falls_back_without_extension_or_valid_capabilities() -> None:
    selector = A2ARepresentationSelector()
    assert selector.select(
        activated_extensions=[],
        message_metadata=_capabilities(),
    ).representation == A2ARepresentation.GENERIC_A2A
    assert selector.select(
        activated_extensions=[A2UI_EXTENSION_URI],
        message_metadata={},
    ).representation == A2ARepresentation.GENERIC_A2A


def test_selector_respects_real_accepted_mime_types() -> None:
    selected = A2ARepresentationSelector().select(
        activated_extensions=[A2UI_EXTENSION_URI],
        message_metadata=_capabilities(),
        accepted_output_modes=["text/plain"],
    )
    assert selected.representation == A2ARepresentation.GENERIC_A2A
