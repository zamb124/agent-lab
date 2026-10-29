"""Vision-resilience: транскод неудобных форматов и сжатие растров перед multimodal LLM."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import ModuleType
from typing import Protocol

import pillow_heif
from PIL import Image

from core.files.reader.exceptions import FileReadError
from core.files.reader.models import CompressionMode
from core.imports import module_sdk
from core.logging import get_logger

# cairosvg зависит от нативной libcairo — опциональной в рантайме flows/worker.
# Загрузка нативной библиотеки — внешняя техническая граница, поэтому импорт guarded:
# отсутствие libcairo делает SVG-транскод недоступным, не ломая остальной reader.
try:
    import cairosvg  # pyright: ignore[reportMissingImports]

    _cairosvg_raw: ModuleType | None = cairosvg
    _cairosvg_error: str = ""
except (ImportError, OSError) as exc:
    _cairosvg_raw = None
    _cairosvg_error = str(exc)

logger = get_logger(__name__)


class _CairoSvgModule(Protocol):
    def svg2png(self, *, bytestring: bytes) -> bytes: ...


class _PillowHeifModule(Protocol):
    def register_heif_opener(self) -> None: ...


module_sdk(pillow_heif, _PillowHeifModule).register_heif_opener()

if _cairosvg_raw is None:
    _cairosvg: _CairoSvgModule | None = None
    logger.warning("files.cairosvg.libcairo.svg", _cairosvg_error=_cairosvg_error)
else:
    _cairosvg = module_sdk(_cairosvg_raw, _CairoSvgModule)

_TRANSCODE_EXTENSIONS: frozenset[str] = frozenset({".heic", ".heif", ".avif", ".svg"})
_TRANSCODE_MIME_TYPES: frozenset[str] = frozenset(
    {"image/heic", "image/heif", "image/avif", "image/svg+xml"}
)
_JPEG_MIME: str = "image/jpeg"
_COMPRESS_TARGET_BYTES: int = 4 * 1024 * 1024
_COMPRESS_MAX_DIMENSION: int = 2048
_COMPRESS_QUALITY: int = 82


def needs_transcode(*, file_name: str, mime: str) -> bool:
    ext = Path(file_name).suffix.lower()
    return ext in _TRANSCODE_EXTENSIONS or mime.lower() in _TRANSCODE_MIME_TYPES


def transcode_to_jpeg(raw: bytes, *, file_name: str, mime: str) -> tuple[bytes, str]:
    """HEIC/HEIF/AVIF/SVG → JPEG. Прочие форматы возвращаются без изменений."""
    ext = Path(file_name).suffix.lower()
    is_svg = ext == ".svg" or mime.lower() == "image/svg+xml"
    if is_svg:
        if _cairosvg is None:
            raise FileReadError(
                "SVG transcode is unavailable: native libcairo (cairosvg) is missing at runtime"
            )
        png_bytes = _cairosvg.svg2png(bytestring=raw)
        image = Image.open(BytesIO(png_bytes))
    else:
        image = Image.open(BytesIO(raw))
    rgb = image.convert("RGB")
    buffer = BytesIO()
    rgb.save(buffer, format="JPEG", quality=_COMPRESS_QUALITY)
    return buffer.getvalue(), _JPEG_MIME


def compress_image(raw: bytes) -> tuple[bytes, str]:
    """Сжимает растр в JPEG с ограничением размера стороны; уменьшает payload перед LLM."""
    image = Image.open(BytesIO(raw))
    rgb = image.convert("RGB")
    width, height = rgb.size
    largest = max(width, height)
    if largest > _COMPRESS_MAX_DIMENSION:
        scale = _COMPRESS_MAX_DIMENSION / largest
        rgb = rgb.resize((max(int(width * scale), 1), max(int(height * scale), 1)))
    buffer = BytesIO()
    rgb.save(buffer, format="JPEG", quality=_COMPRESS_QUALITY)
    return buffer.getvalue(), _JPEG_MIME


def prepare_visual_payload(
    raw: bytes,
    *,
    file_name: str,
    mime: str,
    compression: CompressionMode,
) -> tuple[bytes, str]:
    """Готовит байты картинки к отправке в LLM: транскод неудобных форматов + опциональное сжатие."""
    payload = raw
    payload_mime = mime
    if needs_transcode(file_name=file_name, mime=mime):
        payload, payload_mime = transcode_to_jpeg(payload, file_name=file_name, mime=mime)
    if compression == CompressionMode.BEFORE_LLM or (
        compression == CompressionMode.ON_ERROR and len(payload) > _COMPRESS_TARGET_BYTES
    ):
        payload, payload_mime = compress_image(payload)
    return payload, payload_mime
