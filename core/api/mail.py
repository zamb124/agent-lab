"""HTTP API платформенной почты."""

from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from core.app_state import require_platform_app_state
from core.context import get_context
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID
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
    MailboxBindingPatchPayload,
    MailboxBindingPublic,
    MailFolderListResult,
    MailFoldersEnsurePayload,
    MailMessageFlagPayload,
    MailMessageFlagResult,
    MailMessageListItem,
    MailMessageListPayload,
    MailReconcileResult,
    MailSendPayload,
    MailSendResult,
    MailServerHealth,
    MailThreadPayload,
    MailThreadResult,
)
from core.mail.service import MailService, to_public_binding, to_public_connection
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
    except Exception as exc:
        _raise_http_for_mail_error(exc)
    return ListResponse(items=[to_public_binding(item) for item in bindings])


@router.get("/bindings/me", response_model=ListResponse[MailboxBindingPublic])
async def list_my_mail_bindings(
    mail_service: MailServiceDep,
) -> ListResponse[MailboxBindingPublic]:
    try:
        bindings = await mail_service.list_my_bindings()
    except Exception as exc:
        _raise_http_for_mail_error(exc)
    return ListResponse(items=[to_public_binding(item) for item in bindings])


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
    return to_public_binding(binding)


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
    return to_public_binding(binding)


@router.put("/bindings/{mailbox_binding_id}/default", response_model=MailboxBindingPublic)
async def set_default_mail_binding(
    mailbox_binding_id: str,
    mail_service: MailServiceDep,
) -> MailboxBindingPublic:
    try:
        binding = await mail_service.set_default_binding(mailbox_binding_id)
    except Exception as exc:
        _raise_http_for_mail_error(exc)
    return to_public_binding(binding)


@router.delete("/bindings/{mailbox_binding_id}", status_code=204)
async def delete_mail_binding(
    mailbox_binding_id: str,
    mail_service: MailServiceDep,
) -> None:
    try:
        mail_service.require_company_admin()
        await mail_service.unbind_mailbox(mailbox_binding_id)
    except Exception as exc:
        _raise_http_for_mail_error(exc)


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


@router.post("/messages/list", response_model=ListResponse[MailMessageListItem])
async def list_mail_messages(
    payload: MailMessageListPayload,
    mail_service: MailServiceDep,
) -> ListResponse[MailMessageListItem]:
    try:
        items = await mail_service.list_messages(payload)
    except Exception as exc:
        _raise_http_for_mail_error(exc)
    return ListResponse(items=items)


@router.post("/messages/thread", response_model=MailThreadResult)
async def get_mail_thread(
    payload: MailThreadPayload,
    mail_service: MailServiceDep,
) -> MailThreadResult:
    try:
        return await mail_service.get_thread(payload)
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
        return await mail_service.get_message(
            mailbox_binding_id=mailbox_binding_id,
            uid=uid,
            folder=folder,
        )
    except Exception as exc:
        _raise_http_for_mail_error(exc)


@router.post("/messages/mark_unseen", response_model=MailMessageFlagResult)
async def mark_mail_message_unseen(
    payload: MailMessageFlagPayload,
    mail_service: MailServiceDep,
) -> MailMessageFlagResult:
    try:
        return await mail_service.mark_message_unseen(payload)
    except Exception as exc:
        _raise_http_for_mail_error(exc)


@router.post("/messages/send", response_model=MailSendResult)
async def send_mail_message(
    payload: MailSendPayload,
    mail_service: MailServiceDep,
) -> MailSendResult:
    try:
        return await mail_service.send_message(payload)
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
