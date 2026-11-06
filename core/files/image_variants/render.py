"""Рендер варианта: decode → EXIF → RGB → resize → WebP. Синхронно — вызывать через asyncio.to_thread."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO
from typing import Protocol

import pillow_heif
from PIL import Image, ImageOps

from core.imports import module_sdk


class _PillowHeifModule(Protocol):
    def register_heif_opener(self) -> None: ...


module_sdk(pillow_heif, _PillowHeifModule).register_heif_opener()

_WEBP_QUALITY = 80
_WEBP_METHOD = 6
_RGB_BACKGROUND = (255, 255, 255)


@dataclass(frozen=True, slots=True)
class RenderedImageVariant:
    name: str
    data: bytes
    width: int
    height: int
    sha256: str


def _to_rgb(image: Image.Image) -> Image.Image:
    """RGB без альфы: прозрачность кладётся на белый фон."""
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, _RGB_BACKGROUND)
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    if image.mode != "RGB":
        return image.convert("RGB")
    return image


def render_variant(
    data: bytes,
    *,
    name: str,
    size_px: int,
    square: bool,
) -> RenderedImageVariant:
    """Один вариант: contain в бокс `size_px` либо cover-кроп к квадрату. Upscale не выполняется."""
    try:
        image = Image.open(BytesIO(data))
    except Image.UnidentifiedImageError as exc:
        raise ValueError("file content is not a decodable image") from exc
    rgb = _to_rgb(ImageOps.exif_transpose(image))
    width, height = rgb.size
    if square:
        side = min(size_px, width, height)
        out = ImageOps.fit(rgb, (side, side), method=Image.Resampling.LANCZOS)
    else:
        out = rgb.copy()
        out.thumbnail((size_px, size_px), Image.Resampling.LANCZOS)
    buffer = BytesIO()
    out.save(buffer, format="WEBP", quality=_WEBP_QUALITY, method=_WEBP_METHOD)
    out_width, out_height = out.size
    payload = buffer.getvalue()
    return RenderedImageVariant(
        name=name,
        data=payload,
        width=out_width,
        height=out_height,
        sha256=hashlib.sha256(payload).hexdigest(),
    )
