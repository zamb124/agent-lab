"""Регистрация записи встречи в FileRepository: GET .../files/download/{id} не 404."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from apps.sync.realtime.tasks import (
    _call_recording_s3_object_key,
    _register_platform_file_record_for_call_recording,
)
from core.config import get_settings
from core.files.s3_client import S3ClientFactory


def _skip_if_s3_unavailable() -> None:
    try:
        S3ClientFactory.create_default_client()
    except ValueError as exc:
        pytest.skip(f"S3 не настроен: {exc}")


@pytest.mark.asyncio
async def test_call_recording_register_platform_file_then_download_ok(
    sync_app,
    unique_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    _skip_if_s3_unavailable()

    company_id = f"rec_co_{unique_id}"
    call_id = uuid.uuid4().hex
    recording_id = uuid.uuid4().hex
    s3_key = _call_recording_s3_object_key(
        company_id=company_id,
        call_id=call_id,
        recording_id=recording_id,
    )
    payload = b"sync-test-recording-bytes"
    s3_client = S3ClientFactory.create_client_for_bucket(get_settings().s3.default_bucket)
    uploaded = await s3_client.upload_bytes(payload, s3_key, content_type="video/mp4")
    if not uploaded:
        await s3_client.close()
        pytest.skip("S3 upload_bytes не удалился")
    await s3_client.close()

    try:
        file_size = await _register_platform_file_record_for_call_recording(
            raw_file_id=recording_id,
            company_id=company_id,
            call_id=call_id,
            recording_id=recording_id,
            started_by_user_id=f"user_{unique_id}",
            raw_original_name=f"{recording_id}.mp4",
            raw_storage_url="https://example.invalid/egress-location",
        )
        assert file_size == len(payload)

        transport = ASGITransport(app=sync_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as http:
            dl = await http.get(
                f"/sync/api/v1/files/download/{recording_id}",
                headers=auth_headers_system,
            )
        assert dl.status_code == 200, dl.text
        assert dl.content == payload
    finally:
        cleanup = S3ClientFactory.create_client_for_bucket(get_settings().s3.default_bucket)
        await cleanup.delete_object(s3_key)
        await cleanup.close()
        from apps.sync.container import get_sync_container

        await get_sync_container().file_repository.delete(recording_id)
