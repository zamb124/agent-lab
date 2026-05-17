"""REST-зеркало WS-команды `sync/files/upload_completed_requested`.

Бинарный upload — отдельный `POST /files/` (multipart). Эта команда
возвращает каноничные метаданные файла после загрузки, чтобы клиент
не парсил ответ multipart-эндпоинта вручную.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from apps.sync.dependencies import ContainerDep
from apps.sync.realtime.context import require_current_user
from apps.sync.realtime.operations import (
    FilesUploadCompletedPayload,
    FilesUploadCompletedResult,
    op_files_upload_completed,
)

router = APIRouter()


class _UploadCompletedBody(BaseModel):
    file_id: str = Field(min_length=1)


@router.post("/upload-completed", response_model=FilesUploadCompletedResult)
async def upload_completed(
    container: ContainerDep, body: _UploadCompletedBody
) -> FilesUploadCompletedResult:
    user = require_current_user()
    return await op_files_upload_completed(
        FilesUploadCompletedPayload(file_id=body.file_id),
        user=user,
        container=container,
    )
