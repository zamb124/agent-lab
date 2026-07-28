"""HTTP API платформенной почты."""

from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from core.app_state import require_platform_app_state
from core.context import get_context
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID
from core.mail.enqueue import (
    enqueue_mail_archive,
    enqueue_mail_delete,
    enqueue_mail_mark_seen,
    enqueue_mail_mark_unseen,
    enqueue_mail_move,
    enqueue_mail_send,
    enqueue_mail_star,
    enqueue_mail_trash,
)
from core.mail.exceptions import (
    MailBindingNotFoundError,
    MailConfigError,
    MailConnectionNotFoundError,
    MailDeleteDeniedError,
    MailError,
    MailFolderCreateError,
    MailMailboxNotFoundError,
    MailMessageNotFoundError,
    MailPermissionError,
    MailProvisionUnsupportedError,
    MailSecretMissingError,
    MailSystemConnectionReadOnlyError,
)
from core.mail.models import (
    CompanyMailConnectionPublic,
    CompanyMailConnectionUpsertPayload,
    InboundMailMessagePublic,
    MailboxBindingCreatePayload,
    MailboxBindingHealthcheckPayload,
    MailboxBindingMember,
    MailboxBindingMemberPayload,
    MailboxBindingPatchPayload,
    MailboxBindingPublic,
    MailDraftSavePayload,
    MailDraftSaveResult,
    MailFolderListResult,
    MailFolderRole,
    MailFoldersEnsurePayload,
    MailFoldersReorderPayload,
    MailMessageFlagPayload,
    MailMessageFlagResult,
    MailMessageListPayload,
    MailMessageListResult,
    MailMessageMovePayload,
    MailMessageMoveResult,
    MailMessageRagIndexPayload,
    MailMessageRagIndexResult,
    MailMessageSearchPayload,
    MailMessageStarPayload,
    MailMessageStarResult,
    MailReconcileResult,
    MailSendPayload,
    MailSendResult,
    MailServerHealth,
    MailSyncNowPayload,
    MailSyncNowResult,
    MailThreadPayload,
    MailThreadResult,
    PersonalMailboxConnectPayload,
    PersonalMailboxHealthcheckPayload,
)
from core.mail.service import MailService, to_public_connection
from core.pagination import ListResponse

router = APIRouter(tags=["mail"])


def _get_mail_service(request: Request) -> MailService:
    return require_platform_app_state(request).container.mail_service


MailServiceDep = Annotated[MailService, Depends(_get_mail_service)]


def _raise_http_for_mail_error(error: Exception) -> NoReturn:
    if isinstance(error, MailConnectionNotFoundError):
        raise HTTPException(status_code=404, detail=str(error)) from error
    if isinstance(error, (MailBindingNotFoundError, MailMessageNotFoundError, MailMailboxNotFoundError)):
        raise HTTPException(status_code=404, detail=str(error)) from error
    if isinstance(
        error,
        (
            MailSystemConnectionReadOnlyError,
            MailDeleteDeniedError,
            MailPermissionError,
        ),
    ):
        raise HTTPException(status_code=403, detail=str(error)) from error
    if isinstance(
        error,
        (
            MailConfigError,
            MailProvisionUnsupportedError,
            MailSecretMissingError,
            MailFolderCreateError,
            ValueError,
        ),
    ):
        raise HTTPException(status_code=400, detail=str(error)) from error
    if isinstance(error, MailError):
        raise HTTPException(status_code=502, detail=str(error)) from error
    raise error


@router.get("/connection", response_model=CompanyMailConnectionPublic)
async def get_mail_connection(mail_service: MailServiceDep) -> CompanyMailConnectionPublic:
    try:
        connection = await mail_service.get_connection()
    except Exception as exc:
        _raise_http_for_mail_error(exc)
    if connection is None:
        raise HTTPException(status_code=404, detail="CompanyMailConnection not found")
    return to_public_connection(connection)


@router.put("/connection", response_model=CompanyMailConnectionPublic)
async def put_mail_connection(
    payload: CompanyMailConnectionUpsertPayload,
    mail_service: MailServiceDep,
) -> CompanyMailConnectionPublic:
    try:
        mail_service.require_company_admin()
        connection = await mail_service.upsert_connection(payload)
    except Exception as exc:
        _raise_http_for_mail_error(exc)
    return to_public_connection(connection)


@router.get("/bindings", response_model=ListResponse[MailboxBindingPublic])
async def list_mail_bindings(mail_service: MailServiceDep) -> ListResponse[MailboxBindingPublic]:
    try:
        mail_service.require_company_admin()
        bindings = await mail_service.list_bindings()
        items = [await mail_service.public_binding(item) for item in bindings]
    except Exception as exc:
        _raise_http_for_mail_error(exc)
    return ListResponse(items=items)


@router.get("/bindings/me", response_model=ListResponse[MailboxBindingPublic])
async def list_my_mail_bindings(
    mail_service: MailServiceDep,
) -> ListResponse[MailboxBindingPublic]:
    try:
        bindings = await mail_service.list_my_bindings()
        items = [await mail_service.public_binding(item) for item in bindings]
    except Exception as exc:
        _raise_http_for_mail_error(exc)
    return ListResponse(items=items)


@router.post("/bindings", response_model=MailboxBindingPublic)
async def create_mail_binding(
    payload: MailboxBindingCreatePayload,
    mail_service: MailServiceDep,
) -> MailboxBindingPublic:
    try:
        mail_service.require_company_admin()
        binding = await mail_service.bind_mailbox(payload)
    except Exception as exc:
        _raise_http_for_mail_error(exc)
    return await mail_service.public_binding(binding)


@router.post("/bindings/personal", response_model=MailboxBindingPublic)
async def connect_personal_mail_binding(
    payload: PersonalMailboxConnectPayload,
    mail_service: MailServiceDep,
) -> MailboxBindingPublic:
    try:
        binding = await mail_service.connect_personal_mailbox(payload)
    except Exception as exc:
        _raise_http_for_mail_error(exc)
    return await mail_service.public_binding(binding)


@router.post("/bindings/personal/healthcheck", response_model=MailServerHealth)
async def healthcheck_personal_mail_binding(
    payload: PersonalMailboxHealthcheckPayload,
    mail_service: MailServiceDep,
) -> MailServerHealth:
    try:
        return await mail_service.healthcheck_personal_credentials(payload)
    except Exception as exc:
        _raise_http_for_mail_error(exc)


@router.post(
    "/bindings/{mailbox_binding_id}/healthcheck",
    response_model=MailServerHealth,
)
async def healthcheck_mail_binding(
    mailbox_binding_id: str,
    payload: MailboxBindingHealthcheckPayload,
    mail_service: MailServiceDep,
) -> MailServerHealth:
    try:
        return await mail_service.healthcheck_binding(mailbox_binding_id, payload)
    except Exception as exc:
        _raise_http_for_mail_error(exc)


@router.patch("/bindings/{mailbox_binding_id}", response_model=MailboxBindingPublic)
async def patch_mail_binding(
    mailbox_binding_id: str,
    payload: MailboxBindingPatchPayload,
    mail_service: MailServiceDep,
) -> MailboxBindingPublic:
    try:
        binding = await mail_service.patch_binding(mailbox_binding_id, payload)
    except Exception as exc:
        _raise_http_for_mail_error(exc)
    return await mail_service.public_binding(binding)


@router.put("/bindings/{mailbox_binding_id}/default", response_model=MailboxBindingPublic)
async def set_default_mail_binding(
    mailbox_binding_id: str,
    mail_service: MailServiceDep,
) -> MailboxBindingPublic:
    try:
        binding = await mail_service.set_default_binding(mailbox_binding_id)
    except Exception as exc:
        _raise_http_for_mail_error(exc)
    return await mail_service.public_binding(binding)


@router.delete("/bindings/{mailbox_binding_id}", status_code=204)
async def delete_mail_binding(
    mailbox_binding_id: str,
    mail_service: MailServiceDep,
) -> None:
    try:
        await mail_service.unbind_mailbox(mailbox_binding_id)
    except Exception as exc:
        _raise_http_for_mail_error(exc)


@router.post(
    "/bindings/{mailbox_binding_id}/calendar/autolink",
    response_model=MailboxBindingPublic,
)
async def autolink_mail_binding_calendar(
    mailbox_binding_id: str,
    mail_service: MailServiceDep,
) -> MailboxBindingPublic:
    try:
        binding = await mail_service.relink_mailbox_calendar(mailbox_binding_id)
    except Exception as exc:
        _raise_http_for_mail_error(exc)
    return await mail_service.public_binding(binding)


@router.delete(
    "/bindings/{mailbox_binding_id}/calendar",
    response_model=MailboxBindingPublic,
)
async def unlink_mail_binding_calendar(
    mailbox_binding_id: str,
    mail_service: MailServiceDep,
) -> MailboxBindingPublic:
    try:
        binding = await mail_service.unlink_mailbox_calendar(mailbox_binding_id)
    except Exception as exc:
        _raise_http_for_mail_error(exc)
    return await mail_service.public_binding(binding)


@router.get("/folders", response_model=MailFolderListResult)
async def list_mail_folders(
    mail_service: MailServiceDep,
    mailbox_binding_id: Annotated[str, Query(min_length=1)],
) -> MailFolderListResult:
    try:
        return await mail_service.list_folders(mailbox_binding_id)
    except Exception as exc:
        _raise_http_for_mail_error(exc)


@router.post("/folders/ensure", response_model=MailFolderListResult)
async def ensure_mail_folders(
    payload: MailFoldersEnsurePayload,
    mail_service: MailServiceDep,
) -> MailFolderListResult:
    try:
        return await mail_service.ensure_standard_folders(payload.mailbox_binding_id)
    except Exception as exc:
        _raise_http_for_mail_error(exc)


@router.put("/folders/order", response_model=MailFolderListResult)
async def reorder_mail_folders(
    payload: MailFoldersReorderPayload,
    mail_service: MailServiceDep,
) -> MailFolderListResult:
    try:
        return await mail_service.reorder_folders(payload)
    except Exception as exc:
        _raise_http_for_mail_error(exc)


@router.post("/messages/list", response_model=MailMessageListResult)
async def list_mail_messages(
    payload: MailMessageListPayload,
    mail_service: MailServiceDep,
) -> MailMessageListResult:
    try:
        return await mail_service.list_messages(payload)
    except Exception as exc:
        _raise_http_for_mail_error(exc)


@router.post("/messages/search", response_model=MailMessageListResult)
async def search_mail_messages(
    payload: MailMessageSearchPayload,
    mail_service: MailServiceDep,
) -> MailMessageListResult:
    try:
        return await mail_service.search_messages(payload)
    except Exception as exc:
        _raise_http_for_mail_error(exc)


@router.post("/sync", response_model=MailSyncNowResult)
async def sync_mail_now(
    payload: MailSyncNowPayload,
    mail_service: MailServiceDep,
) -> MailSyncNowResult:
    try:
        return await mail_service.request_sync_now(payload)
    except Exception as exc:
        _raise_http_for_mail_error(exc)


@router.post("/messages/thread", response_model=MailThreadResult)
async def get_mail_thread(
    payload: MailThreadPayload,
    mail_service: MailServiceDep,
) -> MailThreadResult:
    try:
        result = await mail_service.get_thread(payload)
        ctx = get_context()
        if ctx is None or ctx.active_company is None:
            raise MailConfigError("active_company is required for mail operations")
        for uid in result.marked_seen_uids:
            await enqueue_mail_mark_seen(
                company_id=ctx.active_company.company_id,
                mailbox_binding_id=payload.mailbox_binding_id,
                folder=payload.folder,
                uid=uid,
            )
        return result
    except Exception as exc:
        _raise_http_for_mail_error(exc)


@router.get("/messages/{uid}", response_model=InboundMailMessagePublic)
async def get_mail_message(
    uid: str,
    mail_service: MailServiceDep,
    mailbox_binding_id: Annotated[str, Query(min_length=1)],
    folder: Annotated[str, Query()] = "INBOX",
) -> InboundMailMessagePublic:
    try:
        result = await mail_service.get_message(
            mailbox_binding_id=mailbox_binding_id,
            uid=uid,
            folder=folder,
        )
        ctx = get_context()
        if ctx is None or ctx.active_company is None:
            raise MailConfigError("active_company is required for mail operations")
        await enqueue_mail_mark_seen(
            company_id=ctx.active_company.company_id,
            mailbox_binding_id=mailbox_binding_id,
            folder=folder,
            uid=uid,
        )
        return result
    except Exception as exc:
        _raise_http_for_mail_error(exc)


@router.post("/messages/mark_unseen", response_model=MailMessageFlagResult)
async def mark_mail_message_unseen(
    payload: MailMessageFlagPayload,
    mail_service: MailServiceDep,
) -> MailMessageFlagResult:
    try:
        result = await mail_service.mark_message_unseen_local(payload)
        ctx = get_context()
        if ctx is None or ctx.active_company is None:
            raise MailConfigError("active_company is required for mail operations")
        await enqueue_mail_mark_unseen(
            company_id=ctx.active_company.company_id,
            mailbox_binding_id=payload.mailbox_binding_id,
            folder=payload.folder,
            uid=payload.uid,
        )
        return result
    except Exception as exc:
        _raise_http_for_mail_error(exc)


@router.post("/messages/mark_seen", response_model=MailMessageFlagResult)
async def mark_mail_message_seen(
    payload: MailMessageFlagPayload,
    mail_service: MailServiceDep,
) -> MailMessageFlagResult:
    try:
        result = await mail_service.mark_message_seen_local(payload)
        ctx = get_context()
        if ctx is None or ctx.active_company is None:
            raise MailConfigError("active_company is required for mail operations")
        await enqueue_mail_mark_seen(
            company_id=ctx.active_company.company_id,
            mailbox_binding_id=payload.mailbox_binding_id,
            folder=payload.folder,
            uid=payload.uid,
        )
        return result
    except Exception as exc:
        _raise_http_for_mail_error(exc)


@router.post("/messages/send", response_model=MailSendResult)
async def send_mail_message(
    payload: MailSendPayload,
    mail_service: MailServiceDep,
) -> MailSendResult:
    try:
        company_id = _require_company_context()
        send_payload = payload
        if payload.message_id is None or not payload.message_id.strip():
            message_id = await mail_service.allocate_outbound_message_id(
                payload.mailbox_binding_id,
                company_id=company_id,
            )
            send_payload = payload.model_copy(update={"message_id": message_id})
        result = await mail_service.prepare_send_local(send_payload, company_id=company_id)
        await enqueue_mail_send(
            company_id=company_id,
            payload=send_payload.model_dump(mode="json"),
        )
        return result
    except Exception as exc:
        _raise_http_for_mail_error(exc)


def _require_company_context() -> str:
    ctx = get_context()
    if ctx is None or ctx.active_company is None:
        raise MailConfigError("active_company is required for mail operations")
    return ctx.active_company.company_id


@router.post("/messages/move", response_model=MailMessageMoveResult)
async def move_mail_message(
    payload: MailMessageMovePayload,
    mail_service: MailServiceDep,
) -> MailMessageMoveResult:
    try:
        company_id = _require_company_context()
        result = await mail_service.move_message_local(payload)
        await enqueue_mail_move(
            company_id=company_id,
            payload=payload.model_dump(mode="json"),
        )
        return result
    except Exception as exc:
        _raise_http_for_mail_error(exc)


@router.post("/messages/trash", response_model=MailMessageMoveResult)
async def trash_mail_message(
    payload: MailMessageFlagPayload,
    mail_service: MailServiceDep,
) -> MailMessageMoveResult:
    try:
        company_id = _require_company_context()
        trash = await mail_service.resolve_folder_name_for_role(
            payload.mailbox_binding_id, MailFolderRole.TRASH
        )
        move_payload = MailMessageMovePayload(
            mailbox_binding_id=payload.mailbox_binding_id,
            folder=payload.folder,
            uid=payload.uid,
            destination_folder=trash,
        )
        result = await mail_service.move_message_local(move_payload)
        await enqueue_mail_trash(
            company_id=company_id,
            payload=payload.model_dump(mode="json"),
        )
        return result
    except Exception as exc:
        _raise_http_for_mail_error(exc)


@router.post("/messages/archive", response_model=MailMessageMoveResult)
async def archive_mail_message(
    payload: MailMessageFlagPayload,
    mail_service: MailServiceDep,
) -> MailMessageMoveResult:
    try:
        company_id = _require_company_context()
        archive = await mail_service.resolve_folder_name_for_role(
            payload.mailbox_binding_id, MailFolderRole.ARCHIVE
        )
        move_payload = MailMessageMovePayload(
            mailbox_binding_id=payload.mailbox_binding_id,
            folder=payload.folder,
            uid=payload.uid,
            destination_folder=archive,
        )
        result = await mail_service.move_message_local(move_payload)
        await enqueue_mail_archive(
            company_id=company_id,
            payload=payload.model_dump(mode="json"),
        )
        return result
    except Exception as exc:
        _raise_http_for_mail_error(exc)


@router.post("/messages/delete", response_model=MailMessageFlagResult)
async def delete_mail_message(
    payload: MailMessageFlagPayload,
    mail_service: MailServiceDep,
) -> MailMessageFlagResult:
    try:
        company_id = _require_company_context()
        result = await mail_service.delete_message_local(payload)
        await enqueue_mail_delete(
            company_id=company_id,
            payload=payload.model_dump(mode="json"),
        )
        return result
    except Exception as exc:
        _raise_http_for_mail_error(exc)


@router.post("/messages/star", response_model=MailMessageStarResult)
async def star_mail_message(
    payload: MailMessageStarPayload,
    mail_service: MailServiceDep,
) -> MailMessageStarResult:
    try:
        company_id = _require_company_context()
        result = await mail_service.star_message_local(payload)
        await enqueue_mail_star(
            company_id=company_id,
            payload=payload.model_dump(mode="json"),
        )
        return result
    except Exception as exc:
        _raise_http_for_mail_error(exc)


@router.post("/messages/rag-index", response_model=MailMessageRagIndexResult)
async def rag_index_mail_message(
    payload: MailMessageRagIndexPayload,
    mail_service: MailServiceDep,
) -> MailMessageRagIndexResult:
    try:
        return await mail_service.request_rag_index(payload)
    except Exception as exc:
        _raise_http_for_mail_error(exc)


@router.post("/messages/drafts", response_model=MailDraftSaveResult)
async def save_mail_draft(
    payload: MailDraftSavePayload,
    mail_service: MailServiceDep,
) -> MailDraftSaveResult:
    try:
        return await mail_service.save_draft(payload)
    except Exception as exc:
        _raise_http_for_mail_error(exc)


@router.get(
    "/bindings/{mailbox_binding_id}/members",
    response_model=ListResponse[MailboxBindingMember],
)
async def list_mail_binding_members(
    mailbox_binding_id: str,
    mail_service: MailServiceDep,
) -> ListResponse[MailboxBindingMember]:
    try:
        items = await mail_service.list_binding_members(mailbox_binding_id)
        return ListResponse(items=items)
    except Exception as exc:
        _raise_http_for_mail_error(exc)


@router.post(
    "/bindings/{mailbox_binding_id}/members",
    response_model=MailboxBindingMember,
)
async def add_mail_binding_member(
    mailbox_binding_id: str,
    payload: MailboxBindingMemberPayload,
    mail_service: MailServiceDep,
) -> MailboxBindingMember:
    try:
        return await mail_service.add_binding_member(mailbox_binding_id, payload)
    except Exception as exc:
        _raise_http_for_mail_error(exc)


@router.delete("/bindings/{mailbox_binding_id}/members/{user_id}", status_code=204)
async def remove_mail_binding_member(
    mailbox_binding_id: str,
    user_id: str,
    mail_service: MailServiceDep,
) -> None:
    try:
        await mail_service.remove_binding_member(mailbox_binding_id, user_id)
    except Exception as exc:
        _raise_http_for_mail_error(exc)


@router.post("/connection/healthcheck", response_model=MailServerHealth)
async def mail_connection_healthcheck(mail_service: MailServiceDep) -> MailServerHealth:
    try:
        mail_service.require_company_admin()
        return await mail_service.healthcheck()
    except Exception as exc:
        _raise_http_for_mail_error(exc)


@router.post("/system/reconcile", response_model=MailReconcileResult)
async def mail_system_reconcile(mail_service: MailServiceDep) -> MailReconcileResult:
    ctx = get_context()
    if ctx is None or ctx.active_company is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    if ctx.active_company.company_id != SYSTEM_COMPANY_ID:
        raise HTTPException(status_code=403, detail="system reconcile requires company_id=system")
    user_roles = ctx.user.companies.get(SYSTEM_COMPANY_ID, [])
    if "admin" not in user_roles:
        raise HTTPException(status_code=403, detail="system reconcile requires admin role")
    try:
        return await mail_service.reconcile_system()
    except Exception as exc:
        _raise_http_for_mail_error(exc)
