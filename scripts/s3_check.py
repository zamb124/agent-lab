"""
 * @file: s3_check.py
 * @description: Быстрая проверка функций S3 клиента с таймаутами (upload, exists, download, metadata, delete)
 * @dependencies: app.core.core_clients.s3_client.S3ClientFactory, aioboto3
 * @created: 2025-10-31
"""

import asyncio
import uuid

from app.core.core_clients.s3_client import S3ClientFactory


async def run_step(step_name: str, coro, timeout_seconds: int = 20):
    try:
        print(f"➡️ {step_name}...")
        result = await asyncio.wait_for(coro, timeout=timeout_seconds)
        print(f"✅ {step_name}: {result}")
        return result
    except Exception as e:
        print(f"❌ {step_name} failed: {e}")
        raise


async def main():
    client = S3ClientFactory.create_client_for_bucket("vkbucket")
    key = f"test/smoke_{uuid.uuid4().hex[:8]}.txt"
    data = b"s3 smoke test"

    try:
        await run_step(
            "upload_bytes",
            client.upload_bytes(data=data, key=key, content_type="text/plain"),
        )

        await run_step("object_exists", client.object_exists(key))

        downloaded = await run_step("download_bytes", client.download_bytes(key))
        assert downloaded == data, "downloaded content mismatch"

        await run_step("get_object_metadata", client.get_object_metadata(key))

    finally:
        try:
            await run_step("delete_object", client.delete_object(key))
        finally:
            await client.close()


if __name__ == "__main__":
    asyncio.run(main())


