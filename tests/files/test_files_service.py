"""
Unit/integration tests FilesService и контракта FileCreateSpec.
"""

from __future__ import annotations

import pytest

from core.files.object_storage import PLATFORM_STORAGE_ID
from core.files.create_spec import FileCreateSpec, FileSourceKind, FileSourceRef
from core.files.models import FileRecord
from core.files.retention import FileRetentionKind, FileRetentionSpec
from tests.fixtures.s3 import require_s3_configured


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
async def test_files_service_create_persists_record(app, frontend_di):
    _ = app

    require_s3_configured()

    data = b"files service create payload"
    record = await frontend_di.files_service.create(
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
    assert record.metadata["source_kind"] == FileSourceKind.PLATFORM_AUXILIARY.value

    loaded = await frontend_di.files_service.get(record.file_id)
    assert loaded.file_id == record.file_id


def test_source_kind_metadata_value_accepts_enum_and_str() -> None:
    from core.files.service import _source_kind_metadata_value

    assert _source_kind_metadata_value(FileSourceKind.MAIL_MESSAGE) == "mail_message"
    assert _source_kind_metadata_value("mail_message") == "mail_message"


@pytest.mark.asyncio
async def test_files_service_get_missing_raises(app, frontend_di):
    _ = app
    with pytest.raises(ValueError, match="file not found"):
        await frontend_di.files_service.get("ffffffffffffffffffffffffffffffff")


@pytest.mark.asyncio
async def test_files_service_register_s3(app, s3_client, unique_id: str, frontend_di):
    _ = app
    from core.config import get_settings

    settings = get_settings()
    if settings.s3.bucket_name == "":
        pytest.fail("S3 bucket_name is required")

    s3_key = f"test/register-s3/{unique_id}.bin"
    payload = b"register s3 object bytes"
    _ = await s3_client.upload_bytes(payload, s3_key, content_type="application/octet-stream")

    record = await frontend_di.files_service.register_s3(
        _platform_auxiliary_spec(),
        s3_key=s3_key,
        storage_id=PLATFORM_STORAGE_ID,
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


def test_file_create_spec_requires_wiki_page_id():
    with pytest.raises(ValueError, match="wiki_page_id"):
        FileCreateSpec(
            source_kind=FileSourceKind.WIKI_PAGE,
            source_ref=FileSourceRef(namespace_id="knowledge"),
            retention=FileRetentionSpec(kind=FileRetentionKind.WIKI_PAGE),
        )


def test_file_create_spec_requires_wiki_namespace():
    with pytest.raises(ValueError, match="namespace_id"):
        FileCreateSpec(
            source_kind=FileSourceKind.WIKI_PAGE,
            source_ref=FileSourceRef(wiki_page_id="page-1"),
            retention=FileRetentionSpec(kind=FileRetentionKind.WIKI_PAGE),
        )


def test_file_create_spec_json_roundtrip():
    spec = _flow_session_spec(session_id="sess-1")
    restored = FileCreateSpec.model_validate_json(spec.model_dump_json())
    assert restored.source_ref.session_id == "sess-1"
    assert restored.source_kind == FileSourceKind.FLOW_SESSION


@pytest.mark.asyncio
async def test_frontend_upload_invalid_spec_422(frontend_client, auth_headers_system):
    r = await frontend_client.post(
        "/frontend/api/v1/files/uploads",
        headers={**auth_headers_system, "Content-Type": "application/json"},
        json={
            "spec": {
                "source_kind": "flow_session",
                "source_ref": {},
                "retention": {"kind": "flow_session"},
            },
            "original_name": "x.txt",
            "content_type": "text/plain",
            "file_size": 1,
        },
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_frontend_register_s3_http(frontend_client, auth_headers_system, s3_client, unique_id: str):
    from core.config import get_settings

    settings = get_settings()
    if settings.s3.bucket_name == "":
        pytest.fail("S3 bucket_name is required")

    s3_key = f"test/http-register/{unique_id}.txt"
    payload = b"http register s3"
    _ = await s3_client.upload_bytes(payload, s3_key, content_type="text/plain")

    body = {
        "spec": {
            "source_kind": "platform_auxiliary",
            "source_ref": {},
            "retention": {"kind": "platform_default"},
        },
        "s3_key": s3_key,
        "storage_id": PLATFORM_STORAGE_ID,
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
