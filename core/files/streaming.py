"""
Стриминг файлов из S3 в HTTP-ответ.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse

from core.files.http_range import RangeNotSatisfiableError, normalize_s3_byte_range
from core.files.s3_client import S3Client

_CHUNK_SIZE = 64 * 1024  # 64 KB


async def stream_s3_file(
    s3_client: S3Client,
    s3_key: str,
    content_type: str,
    bucket: str | None = None,
    range_header: str | None = None,
) -> StreamingResponse:
    """
    Стримит S3-объект как HTTP StreamingResponse.

    Выставляет Accept-Ranges и Content-Length для полного ответа; поддерживает
    один byte-range (ответ 206), как ожидают медиаплееры Safari.
    """
    target_bucket = s3_client.bucket_name if bucket is None else bucket
    if target_bucket == "":
        raise ValueError("Bucket не указан")

    try:
        metadata = await s3_client.get_object_metadata(s3_key, bucket=target_bucket)
    except BaseException:
        await s3_client.close()
        raise
    total_size = metadata.content_length
    try:
        span = normalize_s3_byte_range(range_header, total_size)
    except RangeNotSatisfiableError:
        await s3_client.close()
        raise

    if span is None:
        try:
            body = await s3_client.open_object_body(s3_key, bucket=target_bucket)
        except BaseException:
            await s3_client.close()
            raise

        async def _iterate_full() -> AsyncIterator[bytes]:
            try:
                while True:
                    chunk = await asyncio.wait_for(body.read(amt=_CHUNK_SIZE), timeout=30)
                    if not chunk:
                        break
                    yield chunk
            finally:
                body.close()
                await s3_client.close()

        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(total_size),
        }
        return StreamingResponse(
            _iterate_full(),
            media_type=content_type,
            headers=headers,
        )

    start, end = span
    byte_range = f"bytes={start}-{end}"
    try:
        body = await s3_client.open_object_body(
            s3_key,
            bucket=target_bucket,
            byte_range=byte_range,
        )
    except BaseException:
        await s3_client.close()
        raise
    part_len = end - start + 1
    content_range = f"bytes {start}-{end}/{total_size}"

    async def _iterate_partial() -> AsyncIterator[bytes]:
        try:
            while True:
                chunk = await asyncio.wait_for(body.read(amt=_CHUNK_SIZE), timeout=30)
                if not chunk:
                    break
                yield chunk
        finally:
            body.close()
            await s3_client.close()

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(part_len),
        "Content-Range": content_range,
    }
    return StreamingResponse(
        _iterate_partial(),
        status_code=206,
        media_type=content_type,
        headers=headers,
    )
