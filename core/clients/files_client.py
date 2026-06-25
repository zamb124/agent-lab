"""HTTP client for cross-process file operations via frontend."""

from __future__ import annotations

from typing import ClassVar

from core.clients.service_client import ServiceClient
from core.files.create_spec import FileCreateSpec
from core.files.models import FileResponse
from core.types import JsonObject, require_json_object


class FilesClient:
    _PREFIX: ClassVar[str] = "/frontend/api/v1/files"

    async def create(
        self,
        spec: FileCreateSpec,
        data: bytes,
        *,
        original_name: str,
        content_type: str,
    ) -> FileResponse:
        client = ServiceClient()
        files = {"file": (original_name, data, content_type)}
        form = {"spec": spec.model_dump_json()}
        response = await client.post(
            "frontend",
            f"{self._PREFIX}/",
            files=files,
            data=form,
            timeout=120.0,
        )
        return FileResponse.model_validate(response)

    async def register_s3(
        self,
        spec: FileCreateSpec,
        *,
        s3_key: str,
        s3_bucket: str,
        original_name: str,
        content_type: str,
        file_size: int,
    ) -> FileResponse:
        client = ServiceClient()
        body: JsonObject = {
            "spec": require_json_object(spec.model_dump(mode="json"), "spec"),
            "s3_key": s3_key,
            "s3_bucket": s3_bucket,
            "original_name": original_name,
            "content_type": content_type,
            "file_size": file_size,
        }
        response = await client.post(
            "frontend",
            f"{self._PREFIX}/register-s3",
            json=body,
            timeout=120.0,
        )
        return FileResponse.model_validate(response)
