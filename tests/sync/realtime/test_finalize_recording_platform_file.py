"""Регистрация записи встречи в FileRepository: GET .../files/download/{id} не 404."""

from __future__ import annotations

import uuid

import pytest
from httpx2 import ASGITransport, AsyncClient

from apps.sync.realtime.tasks import (
    _call_recording_s3_object_key,
    _register_platform_file_record_for_call_recording,
)
from apps.sync.services.sync_channel_access_service import SyncChannelAccessService
from core.config import get_settings
from core.files.object_storage import PLATFORM_STORAGE_ID
from tests.fixtures.s3 import require_s3_configured


@pytest.mark.asyncio
async def test_call_recording_register_platform_file_then_download_ok(
    frontend_app,
    s3_client_for_bucket,
    unique_id: str,
    company_id: str,
    sync_user_id: str,
    sync_auth_headers: dict[str, str],
) -> None:
    require_s3_configured()
    call_id = uuid.uuid4().hex
    recording_id = uuid.uuid4().hex
    s3_key = _call_recording_s3_object_key(
        company_id=company_id,
        call_id=call_id,
        recording_id=recording_id,
    )
    payload = b"sync-test-recording-bytes"
    if get_settings().s3.bucket_name == "":
        pytest.fail("S3 bucket_name is required")
    s3_client = s3_client_for_bucket(PLATFORM_STORAGE_ID)
    uploaded = await s3_client.upload_bytes(payload, s3_key, content_type="video/mp4")
    assert uploaded, "S3 upload_bytes вернул False"
    await s3_client.close()

    channel_id = f"ch-{unique_id}"
    access = SyncChannelAccessService(frontend_app.state.di.authz_service)
    await access.set_member(channel_id, user_id=sync_user_id, relation="member")

    try:
        file_size = await _register_platform_file_record_for_call_recording(
            files_service=frontend_app.state.di.files_service,
            raw_file_id=recording_id,
            company_id=company_id,
            channel_id=channel_id,
            call_id=call_id,
            recording_id=recording_id,
            started_by_user_id=sync_user_id,
            raw_original_name=f"{recording_id}.mp4",
            raw_storage_url="https://example.invalid/egress-location",
            storage_id=PLATFORM_STORAGE_ID,
        )
        assert file_size == len(payload)

        transport = ASGITransport(app=frontend_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as http:
            dl = await http.get(
                f"/frontend/api/v1/files/download/{recording_id}",
                headers=sync_auth_headers,
            )
        assert dl.status_code == 200, dl.text
        assert dl.content == payload
    finally:
        cleanup = s3_client_for_bucket(PLATFORM_STORAGE_ID)
        await cleanup.delete_file(s3_key)
        await cleanup.close()
        from core.files.models import FileRecord

        _ = await FileRecord.delete_by_id(recording_id)
