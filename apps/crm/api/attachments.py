"""
API для работы с вложениями (attachments).

Байты файла — только через chunked Files API. Сюда приходит уже существующий file_id.
"""

from fastapi import APIRouter, HTTPException

from apps.crm.dependencies import ContainerDep
from core.models import StrictBaseModel

router = APIRouter(tags=["Attachments"])


class AttachExistingFileRequest(StrictBaseModel):
    file_id: str


@router.post("/entities/{entity_id}/attachments")
async def attach_file(
    entity_id: str,
    body: AttachExistingFileRequest,
    container: ContainerDep,
):
    """Привязать уже загруженный файл к entity."""
    if body.file_id.strip() == "":
        raise HTTPException(status_code=422, detail="file_id is required")

    try:
        result = await container.attachment_service.add_attachment(
            entity_id=entity_id,
            file_id=body.file_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return result


@router.get("/entities/{entity_id}/attachments")
async def list_attachments(
    entity_id: str,
    container: ContainerDep,
):
    """Получить список вложений entity"""
    attachments = await container.attachment_service.get_attachments(entity_id=entity_id)
    return attachments


@router.delete("/entities/{entity_id}/attachments/{attachment_id}")
async def delete_attachment(
    entity_id: str,
    attachment_id: str,
    container: ContainerDep,
):
    """Удалить вложение"""
    success = await container.attachment_service.remove_attachment(
        entity_id=entity_id, document_id=attachment_id
    )

    if not success:
        raise HTTPException(status_code=404, detail="Attachment not found")

    return {"status": "deleted"}
