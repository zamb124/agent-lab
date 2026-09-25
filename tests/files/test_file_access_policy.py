"""Политика FileGate не смотрит в бакет: отказ до чтения байтов."""

from __future__ import annotations

import pytest

from core.errors.boundary import PlatformAccessDeniedError
from core.files.models import FileRecord, FileStatus
from core.files.object_storage import PLATFORM_STORAGE_ID
from core.files.object_store.policy import authorize_file
from core.files.object_store.principals import (
    AnonymousPrincipal,
    ExecutionPrincipal,
    SessionPrincipal,
    SignedFileGrant,
    SystemPrincipal,
)


def _record(*, company_id: str | None, is_public: bool, file_id: str = "file_policy") -> FileRecord:
    return FileRecord(
        file_id=file_id,
        original_name="a.txt",
        s3_key="files/a.txt",
        storage_id=PLATFORM_STORAGE_ID,
        content_type="text/plain",
        file_size=1,
        company_id=company_id,
        is_public=is_public,
        status=FileStatus.READY,
    )


@pytest.mark.asyncio
async def test_anonymous_cannot_read_private_file():
    with pytest.raises(PlatformAccessDeniedError):
        await authorize_file(_record(company_id="co", is_public=False), AnonymousPrincipal(), None)


@pytest.mark.asyncio
async def test_public_file_allows_anonymous():
    await authorize_file(_record(company_id="co", is_public=True), AnonymousPrincipal(), None)


@pytest.mark.asyncio
async def test_other_company_execution_is_denied():
    with pytest.raises(PlatformAccessDeniedError):
        await authorize_file(
            _record(company_id="co_a", is_public=False),
            ExecutionPrincipal(company_id="co_b", flow_id="flow"),
            None,
        )


@pytest.mark.asyncio
async def test_same_company_system_principal_is_allowed():
    await authorize_file(
        _record(company_id="co_a", is_public=False),
        SystemPrincipal(company_id="co_a"),
        None,
    )


@pytest.mark.asyncio
async def test_signed_grant_does_not_open_another_file():
    record = _record(company_id="co", is_public=False, file_id="file_one")
    with pytest.raises(PlatformAccessDeniedError):
        await authorize_file(
            record,
            SignedFileGrant(file_id="file_two", company_id="co"),
            None,
        )


@pytest.mark.asyncio
async def test_session_without_authz_is_rejected():
    with pytest.raises(ValueError):
        await authorize_file(
            _record(company_id="co", is_public=False),
            SessionPrincipal(user_id="user", company_id="co"),
            None,
        )
