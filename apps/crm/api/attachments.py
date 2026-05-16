"""
API для работы с вложениями (attachments).
"""

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile

from apps.crm.dependencies import ContainerDep

router = APIRouter(tags=["Attachments"])


@router.post("/entities/{entity_id}/attachments")
async def upload_attachment(
    entity_id: str,
    container: ContainerDep,
    file: Annotated[UploadFile, File()],
):
    """Загрузить вложение для entity"""
    if file.filename is None or not file.filename.strip():
        raise HTTPException(status_code=422, detail="filename is required")
    file_content = await file.read()

    result = await container.attachment_service.add_attachment(
        entity_id=entity_id,
        file_data=file_content,
        filename=file.filename,
    )

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
