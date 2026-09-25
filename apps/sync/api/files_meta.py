"""REST-зеркало WS-команды `sync/files/upload_completed_requested`.

Бинарный upload — chunked `POST/PUT /sync/api/v1/files/uploads*`.
Эта команда возвращает каноничные метаданные файла после complete,
чтобы клиент не парсил ответ Files API вручную.
"""

from fastapi import APIRouter

from apps.sync.di import Di
from apps.sync.realtime.operations import (
    FilesUploadCompletedPayload,
    op_files_upload_completed,
)
from core.context import require_context
from core.files.file_ref import FileRef

router = APIRouter()


@router.post("/upload-completed", response_model=FileRef)
async def upload_completed(
    di: Di, body: FilesUploadCompletedPayload
) -> FileRef:
    user = require_context().user
    return await op_files_upload_completed(body, user=user, di=di)
