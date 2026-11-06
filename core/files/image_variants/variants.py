"""Реестр вариантов изображений и контракт их индекса в metadata записи.

Wire: `GET .../files/download/{file_id}?v={size}[!sq]`.
`{size}` — вписать в квадратный бокс с сохранением аспекта (без upscale),
`!sq` — center-crop cover к квадрату. Варианты всегда `image/webp`.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.files.models import FileRecord
from core.files.object_key import object_key
from core.files.types import FileCategory, mime_to_category
from core.types import JsonObject

IMAGE_VARIANT_SIZES: dict[str, int] = {"sm": 160, "md": 480, "lg": 1200}
IMAGE_VARIANT_METADATA_KEY = "image_variants"
IMAGE_VARIANT_CONTENT_TYPE = "image/webp"
_SQ_MODE = "sq"
_SQ_SUFFIX = "_sq"


@dataclass(frozen=True, slots=True)
class ImageVariantRequest:
    """Разобранный параметр `v`: размер из реестра и режим кадрирования."""

    size: str
    square: bool

    @property
    def name(self) -> str:
        """Имя варианта в индексе и в имени объекта: `sm` или `sm_sq`."""
        return f"{self.size}{_SQ_SUFFIX}" if self.square else self.size


def parse_variant_param(value: str) -> ImageVariantRequest:
    """`v` → `ImageVariantRequest`; неизвестный размер или режим — ValueError."""
    raw = value.strip().lower()
    if raw == "":
        raise ValueError("image variant parameter is empty")
    square = False
    size = raw
    if "!" in raw:
        size, mode = raw.split("!", 1)
        if mode != _SQ_MODE:
            raise ValueError(f"unknown image variant mode: {mode!r}")
        square = True
    if size not in IMAGE_VARIANT_SIZES:
        raise ValueError(f"unknown image variant size: {size!r}")
    return ImageVariantRequest(size=size, square=square)


def variant_metadata(record: FileRecord) -> JsonObject:
    raw = record.metadata.get(IMAGE_VARIANT_METADATA_KEY)
    return raw if isinstance(raw, dict) else {}


def variant_entry(record: FileRecord, name: str) -> JsonObject | None:
    """Запись варианта `name` в индексе; битая запись (без ключа) считается отсутствующей."""
    entry = variant_metadata(record).get(name)
    if not isinstance(entry, dict):
        return None
    key = entry.get("key")
    if not isinstance(key, str) or key == "":
        return None
    return entry


def variant_entry_key(entry: JsonObject) -> str:
    key = entry["key"]
    if not isinstance(key, str) or key == "":
        raise ValueError("image variant entry has no key")
    return key


def is_variantable(record: FileRecord) -> bool:
    """Растровое изображение с объектом в хранилище; svg не растеризуется."""
    return (
        record.storage_id != ""
        and record.s3_key != ""
        and mime_to_category(record.content_type) is FileCategory.IMAGE
        and record.content_type.lower() != "image/svg+xml"
    )


def variant_object_key(record: FileRecord, name: str) -> str:
    """Детерминированный ключ производного объекта: версия — checksum исходника."""
    if record.company_id is None or record.company_id == "":
        raise ValueError(f"file {record.file_id} has no company")
    if record.checksum is None or record.checksum == "":
        raise ValueError(f"file {record.file_id} has no checksum")
    return object_key(
        record.company_id,
        record.file_id,
        record.checksum[:16],
        f"v_{name}.webp",
    )


def variant_family_keys(record: FileRecord) -> list[str]:
    """Все производные ключи записи (семейство для delete/move/replace)."""
    keys: list[str] = []
    for entry in variant_metadata(record).values():
        if not isinstance(entry, dict):
            continue
        key = entry.get("key")
        if isinstance(key, str) and key != "" and key != record.s3_key:
            keys.append(key)
    return keys
