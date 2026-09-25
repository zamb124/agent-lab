"""Фикстуры S3 для тестов: явное закрытие aiobotocore/aiohttp-сессий."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

import pytest
import pytest_asyncio

from core.files.object_storage import PLATFORM_STORAGE_ID
from core.files.object_store.s3_client import S3Client, S3ClientFactory


def require_s3_configured() -> None:
    """Проверяет, что S3 включён и platform bucket задан, без открытия HTTP-сессии."""
    from core.config import get_settings

    settings = get_settings()
    if not settings.s3.enabled:
        raise ValueError("S3 отключен в конфигурации")
    if settings.s3.bucket_name == "":
        raise ValueError("s3.bucket_name is required")


@pytest_asyncio.fixture
async def s3_client() -> AsyncIterator[S3Client]:
    """S3Client для platform bucket; закрывает aiobotocore-сессию в teardown."""
    require_s3_configured()
    client = S3ClientFactory.create_platform_client()
    try:
        yield client
    finally:
        await client.close()


@pytest.fixture
def s3_client_for_bucket() -> Callable[[str], S3Client]:
    """Фабрика S3Client для platform storage_id/bucket_name; вызывающий код обязан await client.close()."""

    def _create(bucket_name: str) -> S3Client:
        require_s3_configured()
        if bucket_name not in (PLATFORM_STORAGE_ID,):
            from core.config import get_settings

            settings = get_settings()
            if bucket_name != settings.s3.bucket_name:
                raise ValueError(f"Bucket {bucket_name} is not the platform storage")
        return S3ClientFactory.create_platform_client()

    return _create
