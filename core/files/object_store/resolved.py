"""Снимок подключения, по которому собирается S3-клиент."""

from __future__ import annotations

from dataclasses import dataclass

from core.config import get_settings
from core.files.object_storage import PLATFORM_STORAGE_ID, ObjectStorage
from core.secrets.crypto import decrypt_secret

PLATFORM_CREDENTIALS_VERSION = 0


@dataclass(frozen=True, slots=True)
class ResolvedStorage:
    storage_id: str
    endpoint_url: str
    region_name: str
    bucket_name: str
    access_key_id: str
    secret_access_key: str
    provider: str
    path_style: bool
    credentials_version: int


def resolve_platform_storage() -> ResolvedStorage:
    s3 = get_settings().s3
    if not s3.enabled:
        raise ValueError("S3 is disabled in configuration")
    if s3.endpoint_url is None or s3.endpoint_url == "":
        raise ValueError("s3.endpoint_url is not configured")
    if s3.access_key_id is None or s3.access_key_id == "":
        raise ValueError("s3.access_key_id is not configured")
    if s3.secret_access_key is None or s3.secret_access_key == "":
        raise ValueError("s3.secret_access_key is not configured")
    return ResolvedStorage(
        storage_id=PLATFORM_STORAGE_ID,
        endpoint_url=s3.endpoint_url,
        region_name=s3.region_name,
        bucket_name=s3.bucket_name,
        access_key_id=s3.access_key_id,
        secret_access_key=s3.secret_access_key,
        provider=s3.provider,
        path_style=s3.path_style,
        credentials_version=PLATFORM_CREDENTIALS_VERSION,
    )


def resolve_company_storage(row: ObjectStorage) -> ResolvedStorage:
    return ResolvedStorage(
        storage_id=row.storage_id,
        endpoint_url=row.endpoint_url,
        region_name=row.region_name,
        bucket_name=row.bucket_name,
        access_key_id=row.access_key_id,
        secret_access_key=decrypt_secret(row.secret_access_key_encrypted),
        provider=row.provider,
        path_style=row.path_style,
        credentials_version=row.credentials_version,
    )
