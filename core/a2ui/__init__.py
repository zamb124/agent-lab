"""Versioned A2UI codecs carried inside standard A2A data Parts."""

from core.a2ui.catalog import (
    LINNEX_PLATFORM_CATALOG,
    FlowUICatalogComponent,
    FlowUICatalogFunction,
    FlowUICatalogManifest,
    get_linnex_platform_catalog,
)
from core.a2ui.catalog_identity import (
    canonical_platform_catalog_id,
    validate_platform_catalog_id,
)
from core.a2ui.codec import (
    A2UIBatchApplyError,
    A2UIBatchApplyResult,
    A2UIClientAction,
    A2UIClientCapabilities,
    A2UIClientDataModel,
    A2UICodec,
    A2UICodecRegistry,
    A2UIDecodedInteraction,
)
from core.a2ui.v0_9_1 import A2UI091Codec

DEFAULT_A2UI_CODEC_REGISTRY = A2UICodecRegistry([A2UI091Codec()])

__all__ = [
    "A2UI091Codec",
    "A2UIBatchApplyError",
    "A2UIBatchApplyResult",
    "A2UIClientAction",
    "A2UIClientCapabilities",
    "A2UIClientDataModel",
    "A2UICodec",
    "A2UICodecRegistry",
    "A2UIDecodedInteraction",
    "DEFAULT_A2UI_CODEC_REGISTRY",
    "FlowUICatalogComponent",
    "FlowUICatalogFunction",
    "FlowUICatalogManifest",
    "LINNEX_PLATFORM_CATALOG",
    "canonical_platform_catalog_id",
    "get_linnex_platform_catalog",
    "validate_platform_catalog_id",
]
