"""Пул S3-клиентов по (storage_id, credentials_version)."""

from __future__ import annotations

import asyncio

from core.files.object_store.resolved import ResolvedStorage
from core.files.object_store.s3_client import S3Client
from core.files.s3_sigv4_clock import ensure_sigv4_clock_aligned_with_endpoint

_clients: dict[tuple[str, int], S3Client] = {}
_lock = asyncio.Lock()


def build_client(resolved: ResolvedStorage) -> S3Client:
    ensure_sigv4_clock_aligned_with_endpoint(resolved.endpoint_url)
    return S3Client(
        bucket_name=resolved.bucket_name,
        access_key_id=resolved.access_key_id,
        secret_access_key=resolved.secret_access_key,
        region_name=resolved.region_name,
        endpoint_url=resolved.endpoint_url,
        provider_name=resolved.provider,
        bucket_config_key=resolved.storage_id,
    )


async def client_for(resolved: ResolvedStorage) -> S3Client:
    key = (resolved.storage_id, resolved.credentials_version)
    async with _lock:
        stale = [item for item in _clients if item[0] == resolved.storage_id and item != key]
        for item in stale:
            old = _clients.pop(item)
            await old.close()
        current = _clients.get(key)
        if current is None:
            current = build_client(resolved)
            _clients[key] = current
        return current
