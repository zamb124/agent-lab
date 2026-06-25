"""
Unit/integration tests FilesService и контракта FileCreateSpec.
"""

from __future__ import annotations

import json

import pytest

from core.files.create_spec import FileCreateSpec, FileSourceKind, FileSourceRef
from core.files.models import FileRecord
from core.files.retention import FileRetentionKind, FileRetentionSpec


def _platform_auxiliary_spec(*, is_public: bool = False) -> FileCreateSpec:
    return FileCreateSpec.model_validate(
        {
            "source_kind": "platform_auxiliary",
            "source_ref": {},
            "retention": {"kind": "platform_default"},
            "post_create": {"is_public": is_public},
        }
    )


def _flow_session_spec(*, session_id: str, flow_id: str = "flow_test") -> FileCreateSpec:
    return FileCreateSpec.model_validate(
        {
            "source_kind": "flow_session",
            "source_ref": {"session_id": session_id, "flow_id": flow_id},
            "retention": {"kind": "flow_session"},
        }
    )


@pytest.mark.asyncio
async def test_files_service_create_persists_record(app):
    _ = app
    from apps.frontend.container import get_frontend_container

    container = get_frontend_container()
    from core.files.s3_client import S3ClientFactory

    S3ClientFactory.create_default_client()

    data = b"files service create payload"
    record = await container.files_service.create(
        _platform_auxiliary_spec(is_public=True),
        data,
        original_name="svc.txt",
        content_type="text/plain",
    )
    assert isinstance(record, FileRecord)
    assert record.original_name == "svc.txt"
    assert record.file_size == len(data)
    assert record.url.startswith("/frontend/api/v1/files/download/")
    assert record.is_public is True

    loaded = await container.files_service.get(record.file_id)
    assert loaded.file_id == record.file_id


@pytest.mark.asyncio
async def test_files_service_get_missing_raises(app):
    _ = app
    from apps.frontend.container import get_frontend_container

    container = get_frontend_container()
    with pytest.raises(ValueError, match="file not found"):
        await container.files_service.get("ffffffffffffffffffffffffffffffff")


@pytest.mark.asyncio
async def test_files_service_register_s3(app, unique_id: str):
    _ = app
    from apps.frontend.container import get_frontend_container
    from core.config import get_settings
    from core.files.s3_client import S3ClientFactory

    S3ClientFactory.create_default_client()
    settings = get_settings()
    bucket = settings.s3.default_bucket
    if bucket is None or bucket == "":
        pytest.fail("S3 default_bucket is required")

    s3_key = f"test/register-s3/{unique_id}.bin"
    s3_client = S3ClientFactory.create_default_client()
    payload = b"register s3 object bytes"
    _ = await s3_client.upload_bytes(payload, s3_key, content_type="application/octet-stream")

    container = get_frontend_container()
    record = await container.files_service.register_s3(
        _platform_auxiliary_spec(),
        s3_key=s3_key,
        s3_bucket=bucket,
        original_name=f"{unique_id}.bin",
        content_type="application/octet-stream",
        file_size=len(payload),
    )
    assert record.s3_key == s3_key
    assert record.file_size == len(payload)


def test_file_create_spec_requires_flow_session_id():
    with pytest.raises(ValueError, match="session_id"):
        FileCreateSpec(
            source_kind=FileSourceKind.FLOW_SESSION,
            source_ref=FileSourceRef(flow_id="f1"),
            retention=FileRetentionSpec(kind=FileRetentionKind.FLOW_SESSION),
        )


def test_file_create_spec_requires_rag_namespace():
    with pytest.raises(ValueError, match="namespace_id"):
        FileCreateSpec(
            source_kind=FileSourceKind.RAG_DOCUMENT,
            source_ref=FileSourceRef(),
            retention=FileRetentionSpec(kind=FileRetentionKind.RAG_DOCUMENT),
        )


def test_file_create_spec_json_roundtrip():
    spec = _flow_session_spec(session_id="sess-1")
    restored = FileCreateSpec.model_validate_json(spec.model_dump_json())
    assert restored.source_ref.session_id == "sess-1"
    assert restored.source_kind == FileSourceKind.FLOW_SESSION


@pytest.mark.asyncio
async def test_frontend_upload_invalid_spec_422(frontend_client, auth_headers_system):
    import io

    r = await frontend_client.post(
        "/frontend/api/v1/files/",
        headers=auth_headers_system,
        data={"spec": json.dumps({"source_kind": "flow_session", "source_ref": {}, "retention": {"kind": "flow_session"}})},
        files={"file": ("x.txt", io.BytesIO(b"x"), "text/plain")},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_frontend_register_s3_http(frontend_client, auth_headers_system, unique_id: str):
    from core.config import get_settings
    from core.files.s3_client import S3ClientFactory

    S3ClientFactory.create_default_client()
    settings = get_settings()
    bucket = settings.s3.default_bucket
    if bucket is None or bucket == "":
        pytest.fail("S3 default_bucket is required")

    s3_key = f"test/http-register/{unique_id}.txt"
    payload = b"http register s3"
    s3_client = S3ClientFactory.create_default_client()
    _ = await s3_client.upload_bytes(payload, s3_key, content_type="text/plain")

    body = {
        "spec": {
            "source_kind": "platform_auxiliary",
            "source_ref": {},
            "retention": {"kind": "platform_default"},
        },
        "s3_key": s3_key,
        "s3_bucket": bucket,
        "original_name": f"{unique_id}.txt",
        "content_type": "text/plain",
        "file_size": len(payload),
    }
    r = await frontend_client.post(
        "/frontend/api/v1/files/register-s3",
        headers=auth_headers_system,
        json=body,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["file_id"]
    assert data["url"].startswith("/frontend/api/v1/files/download/")
