"""HTTP client for cross-process file operations + get_bytes via shared FileRepository.

Upload/register идут на Files API **целевого сервиса** (не frontend-канон).
`get_bytes` читает shared FileRepository напрямую.
"""

from __future__ import annotations

from core.clients.service_client import ServiceClient
from core.config import get_settings
from core.context import get_context
from core.db.storage import Storage
from core.files.create_spec import FileCreateSpec
from core.files.file_repository import FileRepository
from core.files.models import FileRecord, FileResponse
from core.files.s3_client import S3ClientFactory
from core.files.urls import (
    files_api_prefix,
    normalize_files_route_segment,
    require_files_route_segment,
)
from core.types import JsonObject, require_json_object

# Public Files path segment → ServiceClient service name
_HTTP_SERVICE_BY_FILES_SEGMENT: dict[str, str] = {
    "documents": "office",
    "litserve": "provider" + "_litserve",
    "capability-gateway": "capability_gateway",
    "code-runner-python": "code_runner_python",
    "code-runner-node": "code_runner_node",
    "code-runner-go": "code_runner_go",
    "code-runner-csharp": "code_runner_csharp",
}


def _http_service_for_files_segment(route_segment: str) -> str:
    mapped = _HTTP_SERVICE_BY_FILES_SEGMENT.get(route_segment)
    if mapped is not None:
        return mapped
    return route_segment


class FilesClient:
    def __init__(
        self,
        *,
        service: str | None = None,
        service_client: ServiceClient | None = None,
        file_repository: FileRepository | None = None,
    ) -> None:
        """
        Args:
            service: имя процесса (`crm`, `office`) или public segment (`documents`).
                None → segment текущего процесса.
        """
        self._http: ServiceClient = (
            service_client if service_client is not None else ServiceClient()
        )
        self._file_repository: FileRepository | None = file_repository
        self._route_segment: str
        self._http_service: str
        if service is None:
            self._route_segment = require_files_route_segment()
        else:
            self._route_segment = normalize_files_route_segment(service)
        self._http_service = _http_service_for_files_segment(self._route_segment)

    def _prefix(self) -> str:
        return files_api_prefix(self._route_segment)

    def _require_file_repository(self) -> FileRepository:
        if self._file_repository is not None:
            return self._file_repository
        shared_url = get_settings().database.shared_url
        if shared_url is None or not shared_url.strip():
            raise ValueError("database.shared_url is required for FilesClient.get_bytes")
        self._file_repository = FileRepository(
            storage=Storage(db_url=shared_url, get_context_func=get_context)
        )
        return self._file_repository

    async def get_record(self, file_id: str) -> FileRecord:
        if file_id.strip() == "":
            raise ValueError("FilesClient.get_record: file_id required")
        record = await self._require_file_repository().get(file_id)
        if record is None:
            raise ValueError(f"File not found: {file_id}")
        return record

    async def create(
        self,
        spec: FileCreateSpec,
        data: bytes,
        *,
        original_name: str,
        content_type: str,
    ) -> FileResponse:
        if len(data) == 0:
            raise ValueError("FilesClient.create: empty data")
        if original_name.strip() == "":
            raise ValueError("FilesClient.create: original_name required")
        if content_type.strip() == "":
            raise ValueError("FilesClient.create: content_type required")

        prefix = self._prefix()
        init_payload: JsonObject = {
            "spec": require_json_object(spec.model_dump(mode="json"), "spec"),
            "original_name": original_name,
            "content_type": content_type,
            "file_size": len(data),
        }
        init_response = await self._http.post(
            self._http_service,
            f"{prefix}/uploads",
            json=init_payload,
            timeout=120.0,
        )
        init_body = require_json_object(init_response, "chunked upload init")
        upload_id = init_body.get("upload_id")
        if not isinstance(upload_id, str) or upload_id == "":
            raise ValueError("chunked upload init: upload_id required")
        chunk_size_raw = init_body.get("chunk_size_bytes")
        if not isinstance(chunk_size_raw, int) or chunk_size_raw < 1:
            raise ValueError("chunked upload init: chunk_size_bytes required")

        offset = 0
        part_number = 1
        while offset < len(data):
            end = min(offset + chunk_size_raw, len(data))
            part = data[offset:end]
            _ = await self._http.put(
                self._http_service,
                f"{prefix}/uploads/{upload_id}/parts/{part_number}",
                content=part,
                headers={"Content-Type": "application/octet-stream"},
                timeout=120.0,
            )
            offset = end
            part_number += 1

        complete_response = await self._http.post(
            self._http_service,
            f"{prefix}/uploads/{upload_id}/complete",
            timeout=120.0,
        )
        return FileResponse.model_validate(complete_response)

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
        body: JsonObject = {
            "spec": require_json_object(spec.model_dump(mode="json"), "spec"),
            "s3_key": s3_key,
            "s3_bucket": s3_bucket,
            "original_name": original_name,
            "content_type": content_type,
            "file_size": file_size,
        }
        response = await self._http.post(
            self._http_service,
            f"{self._prefix()}/register-s3",
            json=body,
            timeout=120.0,
        )
        return FileResponse.model_validate(response)

    async def get_bytes(self, file_id: str) -> bytes:
        record = await self.get_record(file_id)
        s3_bucket = record.s3_bucket
        s3_key = record.s3_key
        if s3_bucket == "" or s3_key == "":
            raise ValueError(f"File {file_id} has empty s3_bucket/s3_key")
        s3_client = S3ClientFactory.create_client_for_bucket(s3_bucket)
        try:
            return await s3_client.download_bytes(s3_key)
        finally:
            await s3_client.close()
