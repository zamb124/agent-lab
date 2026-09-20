"""REST-зеркало WS-команды `sync/files/upload_completed_requested`.

Бинарный upload — chunked `POST/PUT /sync/api/v1/files/uploads*`.
Эта команда возвращает каноничные метаданные файла после complete,
чтобы клиент не парсил ответ Files API вручную.
"""

from fastapi import APIRouter

from apps.sync.dependencies import ContainerDep
from apps.sync.realtime.operations import (
    FilesUploadCompletedPayload,
    FilesUploadCompletedResult,
    op_files_upload_completed,
)
from core.context import require_context

router = APIRouter()


@router.post("/upload-completed", response_model=FilesUploadCompletedResult)
async def upload_completed(
    container: ContainerDep, body: FilesUploadCompletedPayload
) -> FilesUploadCompletedResult:
    user = require_context().user
    return await op_files_upload_completed(body, user=user, container=container)
