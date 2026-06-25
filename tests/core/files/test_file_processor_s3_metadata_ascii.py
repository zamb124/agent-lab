from __future__ import annotations

from urllib.parse import quote

import pytest

import core.files.s3_client as s3_client_module
from core.files.create_spec import FileSourceKind
from core.files.registry import default_retention_for_source
from core.files.storage import FileStorage, retention_fields_from_spec
from core.types import JsonObject


class _FakeFileRepository:
    def __init__(self) -> None:
        self.records = []

    async def set(self, record) -> None:
        self.records.append(record)


class _FakeS3Client:
    provider_name = "test"
    endpoint_url = "http://s3.local"

    def __init__(self) -> None:
        self.last_metadata = None

    def require_bucket_config_key(self) -> str:
        return "files"

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
    repo = _FakeFileRepository()
    s3 = _FakeS3Client()

    monkeypatch.setattr(s3_client_module.S3ClientFactory, "create_default_client", lambda: s3)
    monkeypatch.setattr(s3_client_module.S3ClientFactory, "create_client_for_bucket", lambda _bucket: s3)

    storage = FileStorage(file_repository=repo)  # pyright: ignore[reportArgumentType]
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
    )

    assert record.metadata == metadata
    assert s3.last_metadata is not None
    assert s3.last_metadata["query"] == quote("лучшие статьи о кошках", safe="")
