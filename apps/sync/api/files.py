"""API роутер для файлов (Files)."""

from fastapi import APIRouter, HTTPException

from apps.sync.container import get_sync_container
from apps.sync.models.files import FileRead

router = APIRouter()


@router.get("/{file_id}")
async def get_file(file_id: str) -> FileRead:
    """Получение метаданных файла."""
    container = get_sync_container()
    file = await container.file_repository.get(file_id)
    if file is None:
        raise HTTPException(status_code=404, detail="File not found")
    return FileRead(
        id=file.file_id,
        original_name=file.original_name,
        mime_type=file.mime_type,
        size_bytes=file.size_bytes,
        storage_url=file.storage_url,
        checksum=file.checksum,
        created_at=file.created_at,
    )
