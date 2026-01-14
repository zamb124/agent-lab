"""
API для работы с вложениями (attachments).
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from apps.crm.services.attachment_service import AttachmentService
from apps.crm.container import get_crm_container

router = APIRouter(tags=["Attachments"])


def get_attachment_service() -> AttachmentService:
    """Получить сервис вложений"""
    container = get_crm_container()
    return container.attachment_service


@router.post("/entities/{entity_id}/attachments")
async def upload_attachment(
    entity_id: str,
    file: UploadFile = File(...),
    service: AttachmentService = Depends(get_attachment_service)
):
    """Загрузить вложение для entity"""
    file_content = await file.read()
    
    result = await service.add_attachment(
        entity_id=entity_id,
        file_data=file_content,
        filename=file.filename
    )
    
    return result


@router.get("/entities/{entity_id}/attachments")
async def list_attachments(
    entity_id: str,
    service: AttachmentService = Depends(get_attachment_service)
):
    """Получить список вложений entity"""
    attachments = await service.get_attachments(
        entity_id=entity_id
    )
    return attachments


@router.delete("/entities/{entity_id}/attachments/{attachment_id}")
async def delete_attachment(
    entity_id: str,
    attachment_id: str,
    service: AttachmentService = Depends(get_attachment_service)
):
    """Удалить вложение"""
    success = await service.remove_attachment(
        entity_id=entity_id,
        document_id=attachment_id
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Attachment not found")
    
    return {"status": "deleted"}

