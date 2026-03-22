"""
Стриминг файлов из S3 в HTTP-ответ.
"""

import asyncio
import logging
from typing import AsyncIterator

from fastapi.responses import StreamingResponse

from core.files.s3_client import S3Client

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 64 * 1024  # 64 KB


async def stream_s3_file(
    s3_client: S3Client,
    s3_key: str,
    content_type: str,
    bucket: str | None = None,
) -> StreamingResponse:
    """
    Стримит S3-объект как HTTP StreamingResponse.

    Скачивает тело целиком через get_object и отдаёт чанками,
    не держа весь файл в памяти дольше необходимого.

    Args:
        s3_client: Инициализированный S3Client.
        s3_key: Ключ объекта в S3.
        content_type: MIME-тип для заголовка Content-Type.
        bucket: Имя бакета (если None — используется дефолтный клиента).

    Returns:
        StreamingResponse с телом файла.
    """
    target_bucket = bucket or s3_client.bucket_name

    client = await s3_client._get_client()
    response = await client.get_object(Bucket=target_bucket, Key=s3_key)
    body = response["Body"]

    async def _iterate() -> AsyncIterator[bytes]:
        try:
            while True:
                chunk = await asyncio.wait_for(body.read(amt=_CHUNK_SIZE), timeout=30)
                if not chunk:
                    break
                yield chunk
        finally:
            body.close()
            await s3_client.close()

    return StreamingResponse(
        _iterate(),
        media_type=content_type,
    )
