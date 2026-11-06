"""Ленивые варианты изображений: `?v={size}[!sq]` на download материализует производный WebP-объект."""

from core.files.image_variants.service import ImageVariantService, ResolvedImageVariant
from core.files.image_variants.variants import (
    IMAGE_VARIANT_CONTENT_TYPE,
    IMAGE_VARIANT_METADATA_KEY,
    IMAGE_VARIANT_SIZES,
    is_variantable,
    variant_entry,
    variant_family_keys,
    variant_object_key,
)

__all__ = [
    "IMAGE_VARIANT_CONTENT_TYPE",
    "IMAGE_VARIANT_METADATA_KEY",
    "IMAGE_VARIANT_SIZES",
    "ImageVariantService",
    "ResolvedImageVariant",
    "is_variantable",
    "variant_entry",
    "variant_family_keys",
    "variant_object_key",
]
