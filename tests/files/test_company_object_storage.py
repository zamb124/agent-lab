"""Компания пишет в платформенный MinIO, в своё хранилище и в разные бакеты по роду файла."""

from __future__ import annotations

import uuid

import aioboto3
import pytest

from core.context import set_context
from core.files.company_storage_service import CompanyStorageService
from core.files.create_spec import FileCreateSpec
from core.files.models import FileRecord
from core.files.object_storage import PLATFORM_STORAGE_ID, ObjectStorage
from core.files.object_store.ssrf import assert_company_endpoint
from core.models.context_models import Context
from core.models.identity_models import User
from tests.fixtures.ai_provider_defaults import make_test_company


def _spec(kind: str) -> FileCreateSpec:
    return FileCreateSpec.model_validate(
        {
            "source_kind": kind,
            "source_ref": {},
            "retention": {"kind": "generated_ephemeral" if kind == "generated_ephemeral" else "mail_attachment"},
        }
    )


async def _ensure_bucket(endpoint: str, access_key: str, secret: str, bucket: str) -> None:
    session = aioboto3.Session()
    async with session.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret,
        region_name="us-east-1",
    ) as client:
        try:
            await client.head_bucket(Bucket=bucket)
        except Exception:
            await client.create_bucket(Bucket=bucket)


def _bind_company(company_id: str):
    return set_context(
        Context(
            user=User(user_id=f"user_{company_id}", name="Storage Test"),
            active_company=make_test_company(company_id=company_id, name=company_id),
            session_id="storage-test",
            channel="test",
            metadata={},
        )
    )


@pytest.mark.asyncio
async def test_company_without_route_writes_platform_minio(frontend_di):
    company_id = f"co_{uuid.uuid4().hex[:10]}"
    token = _bind_company(company_id)
    try:
        record = await frontend_di.files_service.create(
            _spec("generated_ephemeral"),
            b"platform-default",
            original_name="default.txt",
            content_type="text/plain",
        )
    finally:
        from core.context import reset_context

        reset_context(token)
    assert record.storage_id == PLATFORM_STORAGE_ID


@pytest.mark.asyncio
async def test_company_route_writes_external_minio_and_kind_split(frontend_di):
    endpoint = "http://127.0.0.1:19003"
    access_key = "extadmin"
    secret = "extadminsecret"
    await _ensure_bucket(endpoint, access_key, secret, "ext-a")
    await _ensure_bucket(endpoint, access_key, secret, "ext-b")
    company_id = f"co_{uuid.uuid4().hex[:10]}"
    service = CompanyStorageService()
    token = _bind_company(company_id)
    try:
        default_storage = await service.create(
            company_id,
            name="ext-a",
            provider="minio",
            endpoint_url=endpoint,
            region_name="us-east-1",
            bucket_name="ext-a",
            path_style=True,
            access_key_id=access_key,
            secret_access_key=secret,
        )
        mail_storage = await service.create(
            company_id,
            name="ext-b",
            provider="minio",
            endpoint_url=endpoint,
            region_name="us-east-1",
            bucket_name="ext-b",
            path_style=True,
            access_key_id=access_key,
            secret_access_key=secret,
        )
        _ = await service.set_route(company_id, source_kind=None, storage_id=default_storage.storage_id)
        from core.files.create_spec import FileSourceKind

        _ = await service.set_route(
            company_id,
            source_kind=FileSourceKind.MAIL_MESSAGE,
            storage_id=mail_storage.storage_id,
        )
        default_file = await frontend_di.files_service.create(
            _spec("generated_ephemeral"),
            b"on-default-route",
            original_name="note.txt",
            content_type="text/plain",
        )
        mail_file = await frontend_di.files_service.create(
            _spec("mail_message"),
            b"on-mail-route",
            original_name="mail.txt",
            content_type="text/plain",
        )
    finally:
        from core.context import reset_context

        reset_context(token)
    assert default_file.storage_id == default_storage.storage_id
    assert mail_file.storage_id == mail_storage.storage_id
    assert await FileRecord.get(default_file.file_id) is not None


def test_private_storage_endpoint_is_rejected():
    with pytest.raises(ValueError):
        assert_company_endpoint("https://10.1.1.1")
    with pytest.raises(ValueError):
        assert_company_endpoint("http://10.1.1.1")
    with pytest.raises(ValueError):
        assert_company_endpoint("https://minio.platform.svc.cluster.local")


@pytest.mark.asyncio
async def test_delete_storage_with_files_conflicts(frontend_di):
    _ = frontend_di
    endpoint = "http://127.0.0.1:19003"
    company_id = f"co_{uuid.uuid4().hex[:10]}"
    service = CompanyStorageService()
    await _ensure_bucket(endpoint, "extadmin", "extadminsecret", "ext-a")
    token = _bind_company(company_id)
    try:
        storage = await service.create(
            company_id,
            name="held",
            provider="minio",
            endpoint_url=endpoint,
            region_name="us-east-1",
            bucket_name="ext-a",
            path_style=True,
            access_key_id="extadmin",
            secret_access_key="extadminsecret",
        )
        _ = await service.set_route(company_id, source_kind=None, storage_id=storage.storage_id)
        _ = await frontend_di.files_service.create(
            _spec("generated_ephemeral"),
            b"keep",
            original_name="keep.txt",
            content_type="text/plain",
        )
        from core.errors.boundary import PlatformConflictError

        with pytest.raises(PlatformConflictError):
            await service.delete(company_id, storage.storage_id)
    finally:
        from core.context import reset_context

        reset_context(token)
        _ = ObjectStorage
