"""Сценарии двух S3-хранилищ: probe, ротация, chunked, перенос, недоступность, доступ, egress."""

from __future__ import annotations

import asyncio
import hashlib
import subprocess
import uuid

import pytest

from apps.sync.realtime.tasks import _register_platform_file_record_for_call_recording
from core.capabilities.models import CapabilityCallRequest, CapabilityExecutionContext
from core.capabilities.tokens import (
    CapabilityExecutionTokenClaims,
    execution_token_exp,
    issue_execution_token,
)
from core.context import reset_context
from core.errors.boundary import (
    PlatformAccessDeniedError,
    PlatformConflictError,
    PlatformUnavailableError,
)
from core.files.chunked_upload import ChunkedUploadService
from core.files.company_storage_service import CompanyStorageService
from core.files.create_spec import FileCreateSpec, FileSourceKind
from core.files.models import FileRecord
from core.files.object_storage import PLATFORM_STORAGE_ID, ObjectStorage
from core.files.object_store.gate import FileGate
from core.files.object_store.pool import client_for
from core.files.object_store.principals import (
    AnonymousPrincipal,
    ExecutionPrincipal,
    SignedFileGrant,
    SystemPrincipal,
)
from core.files.object_store.resolver import resolve_storage_id
from core.files.storage_move import run_storage_migration_batch
from tests.files.test_company_object_storage import _bind_company, _ensure_bucket

_EXT = "http://127.0.0.1:19003"
_KEY = "extadmin"
_SECRET = "extadminsecret"
_EXT_CONTAINER = "agentlab_seaweedfs_ext_test"


def _spec(kind: str) -> FileCreateSpec:
    retention = "mail_attachment" if kind == "mail_message" else "generated_ephemeral"
    if kind == "sync_call_recording":
        return FileCreateSpec.model_validate(
            {
                "source_kind": kind,
                "source_ref": {"call_id": "call_scenario"},
                "retention": {"kind": "platform_default"},
            }
        )
    if kind == "platform_auxiliary":
        retention = "platform_default"
    return FileCreateSpec.model_validate(
        {
            "source_kind": kind,
            "source_ref": {},
            "retention": {"kind": retention},
        }
    )


async def _connect(service: CompanyStorageService, company_id: str, *, name: str, bucket: str):
    return await service.create(
        company_id,
        name=name,
        provider="seaweedfs",
        endpoint_url=_EXT,
        region_name="us-east-1",
        bucket_name=bucket,
        path_style=True,
        access_key_id=_KEY,
        secret_access_key=_SECRET,
    )


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_probe_rejects_bad_endpoint_without_active_row():
    company_id = f"co_{uuid.uuid4().hex[:10]}"
    service = CompanyStorageService()
    token = _bind_company(company_id)
    try:
        for endpoint, key in (
            ("http://192.0.2.1", _KEY),
            ("http://10.1.2.3", _KEY),
            ("http://seaweedfs.cluster.local", _KEY),
            (_EXT, "not-a-key"),
        ):
            with pytest.raises(ValueError):
                await service.probe(
                    provider="seaweedfs",
                    endpoint_url=endpoint,
                    region_name="us-east-1",
                    bucket_name="ext-a",
                    path_style=True,
                    access_key_id=key,
                    secret_access_key=_SECRET,
                )
        with pytest.raises(ValueError):
            await service.create(
                company_id,
                name="bad",
                provider="seaweedfs",
                endpoint_url=_EXT,
                region_name="us-east-1",
                bucket_name="ext-a",
                path_style=True,
                access_key_id="not-a-key",
                secret_access_key="not-a-secret",
            )
        assert await ObjectStorage.list_by_created_at_asc(company_id) == []
    finally:
        reset_context(token)


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_rotated_keys_still_read_the_old_file(frontend_di):
    await _ensure_bucket(_EXT, _KEY, _SECRET, "ext-a")
    company_id = f"co_{uuid.uuid4().hex[:10]}"
    service = CompanyStorageService()
    token = _bind_company(company_id)
    try:
        storage = await _connect(service, company_id, name="ext-a", bucket="ext-a")
        _ = await service.set_route(company_id, source_kind=None, storage_id=storage.storage_id)
        body = b"rotate-me"
        record = await frontend_di.files_service.create(
            _spec("generated_ephemeral"),
            body,
            original_name="rotate.txt",
            content_type="text/plain",
        )
        assert record.storage_id == storage.storage_id
        rotated = await service.rotate_credentials(
            company_id,
            storage.storage_id,
            access_key_id=_KEY,
            secret_access_key=_SECRET,
        )
        assert rotated.credentials_version == storage.credentials_version + 1
        handle = await FileGate().open_record(record, SystemPrincipal(company_id))
        assert await handle.read_bytes() == body
    finally:
        reset_context(token)


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_chunked_upload_stays_on_the_session_storage(frontend_di):
    await _ensure_bucket(_EXT, _KEY, _SECRET, "ext-a")
    await _ensure_bucket(_EXT, _KEY, _SECRET, "ext-b")
    company_id = f"co_{uuid.uuid4().hex[:10]}"
    service = CompanyStorageService()
    token = _bind_company(company_id)
    try:
        first = await _connect(service, company_id, name="ext-a", bucket="ext-a")
        second = await _connect(service, company_id, name="ext-b", bucket="ext-b")
        _ = await service.set_route(company_id, source_kind=None, storage_id=first.storage_id)
        chunked = ChunkedUploadService(
            files_route_segment="frontend",
            tree=frontend_di.document_tree_service,
        )
        body = b"chunked-pinned"
        started = await chunked.init_upload(
            spec=_spec("generated_ephemeral"),
            original_name="chunked.txt",
            content_type="text/plain",
            file_size=len(body),
        )
        _ = await service.set_route(company_id, source_kind=None, storage_id=second.storage_id)
        _ = await chunked.upload_part(started.upload_id, 1, body)
        record = await chunked.complete_upload(started.upload_id)
        assert record.storage_id == first.storage_id
        handle = await FileGate().open(record.file_id, SystemPrincipal(company_id))
        assert await handle.read_bytes() == body
    finally:
        reset_context(token)


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_migration_resumes_and_delete_follows_remaining_files(frontend_di):
    await _ensure_bucket(_EXT, _KEY, _SECRET, "ext-a")
    await _ensure_bucket(_EXT, _KEY, _SECRET, "ext-b")
    company_id = f"co_{uuid.uuid4().hex[:10]}"
    service = CompanyStorageService()
    token = _bind_company(company_id)
    try:
        source = await _connect(service, company_id, name="ext-a", bucket="ext-a")
        target = await _connect(service, company_id, name="ext-b", bucket="ext-b")
        _ = await service.set_route(company_id, source_kind=None, storage_id=source.storage_id)
        digest = ""
        for index in range(21):
            body = f"move-{index}".encode()
            record = await frontend_di.files_service.create(
                _spec("generated_ephemeral"),
                body,
                original_name=f"move-{index}.txt",
                content_type="text/plain",
            )
            assert record.storage_id == source.storage_id
            if index == 0:
                digest = hashlib.sha256(body).hexdigest()
                watched = record.file_id
        with pytest.raises(PlatformConflictError):
            await service.delete(company_id, source.storage_id)
        migration = await service.start_migration(
            company_id,
            source_storage_id=source.storage_id,
            target_storage_id=target.storage_id,
        )
        first = await run_storage_migration_batch(migration.storage_migration_id)
        assert first.state == "running"
        assert await FileRecord.count_for_storage(source.storage_id) > 0
        done = await run_storage_migration_batch(migration.storage_migration_id)
        assert done.state == "completed"
        moved = await FileRecord.get(watched)
        assert moved is not None
        assert moved.storage_id == target.storage_id
        handle = await FileGate().open_record(moved, SystemPrincipal(company_id))
        assert hashlib.sha256(await handle.read_bytes()).hexdigest() == digest
        assert await FileRecord.count_for_storage(source.storage_id) == 0
        _ = await service.set_route(company_id, source_kind=None, storage_id=target.storage_id)
        await service.delete(company_id, source.storage_id)
        assert await ObjectStorage.get(source.storage_id) is None
        assert await ObjectStorage.get(target.storage_id) is not None
    finally:
        reset_context(token)


@pytest.mark.asyncio
@pytest.mark.timeout(90)
async def test_stopped_company_s3_is_unavailable_and_skips_platform(frontend_di):
    await _ensure_bucket(_EXT, _KEY, _SECRET, "ext-a")
    company_id = f"co_{uuid.uuid4().hex[:10]}"
    service = CompanyStorageService()
    token = _bind_company(company_id)
    try:
        storage = await _connect(service, company_id, name="ext-a", bucket="ext-a")
        _ = await service.set_route(company_id, source_kind=None, storage_id=storage.storage_id)
        existing = await frontend_di.files_service.create(
            _spec("generated_ephemeral"),
            b"already-there",
            original_name="alive.txt",
            content_type="text/plain",
        )
        assert existing.storage_id == storage.storage_id
        platform_before = await FileRecord.count_for_storage(PLATFORM_STORAGE_ID)
        _ = subprocess.run(["docker", "stop", _EXT_CONTAINER], check=True)
        try:
            with pytest.raises(PlatformUnavailableError):
                await frontend_di.files_service.create(
                    _spec("generated_ephemeral"),
                    b"should-not-land",
                    original_name="miss.txt",
                    content_type="text/plain",
                )
            handle = await FileGate().open(existing.file_id, SystemPrincipal(company_id))
            with pytest.raises(PlatformUnavailableError):
                _ = await handle.read_bytes()
        finally:
            _ = subprocess.run(["docker", "start", _EXT_CONTAINER], check=True)
            ready = False
            for _attempt in range(30):
                try:
                    await _ensure_bucket(_EXT, _KEY, _SECRET, "ext-a")
                    ready = True
                    break
                except Exception:
                    await asyncio.sleep(1)
            if not ready:
                raise RuntimeError("seaweedfs-test-ext did not come back")
        assert await FileRecord.count_for_storage(PLATFORM_STORAGE_ID) == platform_before
    finally:
        reset_context(token)


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_file_gate_denies_foreign_principal_and_opens_public(frontend_di):
    company_id = f"co_{uuid.uuid4().hex[:10]}"
    token = _bind_company(company_id)
    try:
        private = await frontend_di.files_service.create(
            _spec("generated_ephemeral"),
            b"secret",
            original_name="private.txt",
            content_type="text/plain",
        )
        public = await frontend_di.files_service.create(
            FileCreateSpec.model_validate(
                {
                    "source_kind": "platform_auxiliary",
                    "source_ref": {},
                    "retention": {"kind": "platform_default"},
                    "post_create": {"is_public": True},
                }
            ),
            b"public",
            original_name="public.txt",
            content_type="text/plain",
        )
        with pytest.raises(PlatformAccessDeniedError):
            await FileGate().open(
                private.file_id,
                ExecutionPrincipal(company_id="co_other", flow_id="flow"),
            )
        with pytest.raises(PlatformAccessDeniedError):
            await FileGate().open(
                private.file_id,
                SignedFileGrant(file_id="file_other", company_id=company_id),
            )
        opened = await FileGate().open(public.file_id, AnonymousPrincipal())
        assert await opened.read_bytes() == b"public"
    finally:
        reset_context(token)


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_capability_get_bytes_denies_foreign_file(frontend_di, capability_gateway_di):
    company_id = f"co_{uuid.uuid4().hex[:10]}"
    token = _bind_company(company_id)
    try:
        record = await frontend_di.files_service.create(
            _spec("generated_ephemeral"),
            b"cap",
            original_name="cap.txt",
            content_type="text/plain",
        )
    finally:
        reset_context(token)
    claims = CapabilityExecutionTokenClaims(
        company_id="co_other",
        user_id="user_other",
        flow_id="flow_other",
        branch_id="main",
        session_id="flow_other:ctx",
        task_id="task",
        context_id="ctx",
        channel="a2a",
        request_id="cap-deny",
        exp=execution_token_exp(300),
    )
    request = CapabilityCallRequest(
        context=CapabilityExecutionContext(
            execution_token=issue_execution_token(claims),
            company_id=claims.company_id,
            user_id=claims.user_id,
            flow_id=claims.flow_id,
            branch_id=claims.branch_id,
            session_id=claims.session_id,
            task_id=claims.task_id,
            context_id=claims.context_id,
            channel=claims.channel,
            request_id=claims.request_id,
        ),
        name="files.get_bytes",
        kwargs={"file_id": record.file_id},
    )
    with pytest.raises(PlatformAccessDeniedError):
        _ = await capability_gateway_di.capability_registry._files_get_bytes(request)


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_call_recording_egress_pins_storage_id(frontend_di):
    await _ensure_bucket(_EXT, _KEY, _SECRET, "ext-a")
    await _ensure_bucket(_EXT, _KEY, _SECRET, "ext-b")
    company_id = f"co_{uuid.uuid4().hex[:10]}"
    service = CompanyStorageService()
    token = _bind_company(company_id)
    try:
        pinned = await _connect(service, company_id, name="ext-a", bucket="ext-a")
        later = await _connect(service, company_id, name="ext-b", bucket="ext-b")
        _ = await service.set_route(
            company_id,
            source_kind=FileSourceKind.SYNC_CALL_RECORDING,
            storage_id=pinned.storage_id,
        )
        target = await FileGate().egress_target(company_id, FileSourceKind.SYNC_CALL_RECORDING)
        assert target.bucket_name == "ext-a"
        assert target.storage_id == pinned.storage_id
        call_id = f"call_{uuid.uuid4().hex[:8]}"
        recording_id = f"rec_{uuid.uuid4().hex[:8]}"
        key = f"sync-recordings/{company_id}/{call_id}/{recording_id}.mp4"
        client = await client_for(await resolve_storage_id(pinned.storage_id))
        _ = await client.upload_bytes(data=b"recording-bytes", key=key, content_type="video/mp4")
        _ = await service.set_route(
            company_id,
            source_kind=FileSourceKind.SYNC_CALL_RECORDING,
            storage_id=later.storage_id,
        )
        _ = await _register_platform_file_record_for_call_recording(
            files_service=frontend_di.files_service,
            raw_file_id=f"file_{uuid.uuid4().hex[:12]}",
            company_id=company_id,
            channel_id=f"ch_{uuid.uuid4().hex[:8]}",
            call_id=call_id,
            recording_id=recording_id,
            started_by_user_id="user_recording",
            raw_original_name="call.mp4",
            raw_storage_url=f"{_EXT}/{key}",
            storage_id=pinned.storage_id,
        )
        stored = await FileRecord.objects.filter(company_id=company_id, original_name="call.mp4").all()
        assert len(stored) == 1
        assert stored[0].storage_id == pinned.storage_id
    finally:
        reset_context(token)
