"""ImageVariantService: ленивая материализация вариантов изображений при первом `?v=`."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from core.clients.redis_client import RedisClient
from core.errors.boundary import PlatformNotFoundError, PlatformUnavailableError
from core.files.image_variants.render import render_variant
from core.files.image_variants.variants import (
    IMAGE_VARIANT_CONTENT_TYPE,
    IMAGE_VARIANT_METADATA_KEY,
    IMAGE_VARIANT_SIZES,
    ImageVariantRequest,
    is_variantable,
    parse_variant_param,
    variant_entry,
    variant_entry_key,
    variant_metadata,
    variant_object_key,
)
from core.files.models import FileRecord
from core.files.object_store.gate import FileGate
from core.files.object_store.principals import SystemPrincipal

_LOCK_TTL_SECONDS = 60
_LOCK_WAIT_LIMIT_SECONDS = 25.0
_LOCK_POLL_SECONDS = 0.15


@dataclass(frozen=True, slots=True)
class ResolvedImageVariant:
    """Готовый к отдаче вариант: ключ объекта и его MIME."""

    key: str
    content_type: str


class ImageVariantService:
    """Вариант есть в индексе — отдать ключ; нет — срендерить, записать объект, проиндексировать."""

    def __init__(self, redis_client: RedisClient) -> None:
        self._redis: RedisClient = redis_client

    async def ensure_variant_key(self, record: FileRecord, v: str) -> ResolvedImageVariant:
        """Ключ объекта варианта для download `?v=`; материализует при первом обращении."""
        try:
            request = parse_variant_param(v)
        except ValueError as exc:
            raise PlatformNotFoundError(str(exc)) from exc
        if not is_variantable(record):
            raise PlatformNotFoundError(
                f"file {record.file_id} does not support image variants",
                error_code="image_variants_unsupported",
            )
        return await self._materialize(record, request)

    async def _materialize(
        self, record: FileRecord, request: ImageVariantRequest
    ) -> ResolvedImageVariant:
        """Один писатель на файл: per-file Redis lock сериализует merge индекса."""
        lock_key = f"files:imgvar:{record.file_id}"
        deadline = asyncio.get_running_loop().time() + _LOCK_WAIT_LIMIT_SECONDS
        while True:
            fresh = await FileRecord.get(record.file_id)
            if fresh is None:
                raise PlatformNotFoundError(f"file not found: {record.file_id}")
            entry = variant_entry(fresh, request.name)
            if entry is not None:
                return ResolvedImageVariant(
                    key=variant_entry_key(entry), content_type=IMAGE_VARIANT_CONTENT_TYPE
                )
            acquired = await self._redis.set_nx(lock_key, "1", _LOCK_TTL_SECONDS)
            if acquired:
                try:
                    return await self._render_store_index(fresh, request)
                finally:
                    _ = await self._redis.delete(lock_key)
            if asyncio.get_running_loop().time() >= deadline:
                raise PlatformUnavailableError(
                    "image variant materialization is busy",
                    error_code="image_variants_busy",
                )
            await asyncio.sleep(_LOCK_POLL_SECONDS)

    async def _render_store_index(
        self, record: FileRecord, request: ImageVariantRequest
    ) -> ResolvedImageVariant:
        name = request.name
        gate = FileGate()
        company_id = record.company_id
        if company_id is None or company_id == "":
            raise PlatformNotFoundError(
                f"file {record.file_id} does not support image variants",
                error_code="image_variants_unsupported",
            )
        handle = await gate.open_record(record, SystemPrincipal(company_id=company_id))
        data = await handle.read_bytes()
        rendered = await asyncio.to_thread(
            render_variant,
            data,
            name=name,
            size_px=IMAGE_VARIANT_SIZES[request.size],
            square=request.square,
        )
        key = variant_object_key(record, name)
        s3 = await gate.client_for_storage_id(record.storage_id, record=record)
        try:
            _ = await s3.upload_bytes(
                data=rendered.data,
                key=key,
                content_type=IMAGE_VARIANT_CONTENT_TYPE,
                public=record.is_public,
            )
        except Exception:
            _ = await s3.delete_file(key)
            raise
        indexed = record.model_copy(
            update={
                "metadata": {
                    **record.metadata,
                    IMAGE_VARIANT_METADATA_KEY: {
                        **variant_metadata(record),
                        name: {
                            "key": key,
                            "bytes": len(rendered.data),
                            "w": rendered.width,
                            "h": rendered.height,
                            "content_type": IMAGE_VARIANT_CONTENT_TYPE,
                        },
                    },
                }
            }
        )
        _ = await FileRecord.set(indexed)
        return ResolvedImageVariant(key=key, content_type=IMAGE_VARIANT_CONTENT_TYPE)
