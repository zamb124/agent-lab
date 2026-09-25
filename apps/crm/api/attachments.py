"""REST-зеркало вложений: те же `op_*`, что и Centrifugo RPC `platform.event`.

Байты файла — только через chunked Files API. Сюда приходит уже существующий file_id.
"""

from fastapi import APIRouter, Response

from apps.crm.di import Di
from apps.crm.models.api import (
    AttachmentAttachRequest,
    AttachmentAttachResponse,
    EntityAttachment,
)
from apps.crm.realtime.operations import (
    CrmAttachmentsAttachPayload,
    CrmAttachmentsRemovePayload,
    CrmEntityIdPayload,
    op_attachments_attach,
    op_attachments_list,
    op_attachments_remove,
)
from core.context import require_context
from core.pagination import ListResponse

router = APIRouter(tags=["Attachments"])


@router.post("/entities/{entity_id}/attachments", response_model=AttachmentAttachResponse)
async def attach_file(
    entity_id: str,
    body: AttachmentAttachRequest,
    di: Di,
) -> AttachmentAttachResponse:
    return await op_attachments_attach(
        CrmAttachmentsAttachPayload(entity_id=entity_id, file_id=body.file_id),
        user=require_context().user,
        di=di,
    )


@router.get(
    "/entities/{entity_id}/attachments",
    response_model=ListResponse[EntityAttachment],
)
async def list_attachments(
    entity_id: str,
    di: Di,
) -> ListResponse[EntityAttachment]:
    return await op_attachments_list(
        CrmEntityIdPayload(entity_id=entity_id),
        user=require_context().user,
        di=di,
    )


@router.delete("/entities/{entity_id}/attachments/{attachment_id}", status_code=204)
async def delete_attachment(
    entity_id: str,
    attachment_id: str,
    di: Di,
) -> Response:
    await op_attachments_remove(
        CrmAttachmentsRemovePayload(entity_id=entity_id, attachment_id=attachment_id),
        user=require_context().user,
        di=di,
    )
    return Response(status_code=204)
