from __future__ import annotations

from urllib.parse import quote

import pytest

import core.files.object_store.pool as pool_module
from core.files.create_spec import FileSourceKind
from core.files.object_storage import PLATFORM_STORAGE_ID
from core.files.object_store.resolved import ResolvedStorage
from core.files.registry import default_retention_for_source
from core.files.storage import FileStorage, retention_fields_from_spec
from core.types import JsonObject


class _FakeS3Client:
    provider_name = "test"
    endpoint_url = "http://s3.local"
    bucket_name = "test-bucket"

    def __init__(self) -> None:
        self.last_metadata = None

    def require_bucket_config_key(self) -> str:
        return PLATFORM_STORAGE_ID

    async def upload_bytes(self, *, data: bytes, key: str, metadata: dict[str, str], **kwargs) -> bool:
        for k, v in metadata.items():
            assert isinstance(k, str) and k != ""
            assert isinstance(v, str)
            v.encode("ascii")
        self.last_metadata = metadata
        return True

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_process_file_from_bytes_encodes_unicode_metadata_for_s3(monkeypatch) -> None:
    s3 = _FakeS3Client()

    async def _client_for(_resolved: ResolvedStorage) -> _FakeS3Client:
        return s3

    monkeypatch.setattr(pool_module, "client_for", _client_for)

    storage = FileStorage()
    retention = default_retention_for_source(FileSourceKind.GENERATED_EPHEMERAL)
    retention_kind, ttl_seconds = retention_fields_from_spec(retention)
    metadata: JsonObject = {"query": "лучшие статьи о кошках"}
    record = await storage.upload_bytes(
        data=b"<html></html>",
        original_name="snapshot.html",
        content_type="text/html",
        uploaded_by=None,
        company_id="system",
        is_public=False,
        retention_kind=retention_kind,
        ttl_seconds=ttl_seconds,
        metadata=metadata,
        source_kind=FileSourceKind.GENERATED_EPHEMERAL,
    )

    assert record.metadata == metadata
    assert s3.last_metadata is not None
    assert s3.last_metadata["query"] == quote("лучшие статьи о кошках", safe="")
