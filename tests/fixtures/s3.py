"""Фикстуры S3 для тестов: явное закрытие aiobotocore/aiohttp-сессий."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

import pytest
import pytest_asyncio

from core.files.s3_client import S3Client, S3ClientFactory


def require_s3_configured() -> None:
    """Проверяет, что S3 включён и default bucket задан, без открытия HTTP-сессии."""
    from core.config import get_settings

    settings = get_settings()
    if not settings.s3.enabled:
        raise ValueError("S3 отключен в конфигурации")
    bucket = settings.s3.default_bucket
    if bucket == "":
        raise ValueError("S3 default_bucket is required")
    if bucket not in settings.s3.buckets:
        raise ValueError(f"Bucket {bucket} не найден в конфигурации")


@pytest_asyncio.fixture
async def s3_client() -> AsyncIterator[S3Client]:
    """S3Client для default bucket; закрывает aiobotocore-сессию в teardown."""
    require_s3_configured()
    client = S3ClientFactory.create_default_client()
    try:
        yield client
    finally:
        await client.close()


@pytest.fixture
def s3_client_for_bucket() -> Callable[[str], S3Client]:
    """Фабрика S3Client по ключу bucket; вызывающий код обязан await client.close()."""

    def _create(bucket_name: str) -> S3Client:
        require_s3_configured()
        return S3ClientFactory.create_client_for_bucket(bucket_name)

    return _create
