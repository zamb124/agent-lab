"""MailClient — thin typed client for mail_* tools over MailService.

Доступен всем сервисам как typed-адаптер: резолюция отправителя идёт только
среди binding'ов, которые актор видит (``MailService.list_my_bindings`` →
``can_view`` через AuthzService), поэтому tool не может отправить из чужого
ящика. Админские операции (``create_mailbox``) вызывают
``require_company_admin`` — тот же гейт, что у REST-роута
``POST /{svc}/api/mail/bindings``. Публичная форма binding'а — только через
``MailService.public_binding`` (секреты стрипаются сериализатором модели).
"""

from __future__ import annotations

from core.context import get_context
from core.mail.enqueue import enqueue_mail_mark_seen
from core.mail.exceptions import MailConfigError, MailPermissionError
from core.mail.models import (
    MailAttachment,
    MailboxBinding,
    MailboxBindingCreatePayload,
    MailboxBindingHealthcheckPayload,
    MailboxBindingKind,
    MailboxBindingMemberPayload,
    MailboxBindingMemberRole,
    MailboxBindingPatchPayload,
    MailDraftSavePayload,
    MailFolderRole,
    MailMessageFlagPayload,
    MailMessageListPayload,
    MailMessageMovePayload,
    MailMessageSearchPayload,
    MailMessageStarPayload,
    MailSendPayload,
    MailSyncNowPayload,
    MailThreadPayload,
    PersonalMailboxConnectPayload,
)
from core.mail.service import MailService
from core.types import JsonObject


class MailClient:
    """mail_* tools → MailService (resolve accessible sender + thin pass-through)."""

    _service: MailService

    def __init__(self, service: MailService) -> None:
        self._service = service

    async def _public(self, binding: MailboxBinding) -> JsonObject:
        return (await self._service.public_binding(binding)).model_dump(mode="json")

    def _company_id(self) -> str:
        ctx = get_context()
        if ctx is None or ctx.active_company is None:
            raise MailConfigError("active_company is required for mail operations")
        return ctx.active_company.company_id

    # ------------------------------------------------------------------
    # Bindings
    # ------------------------------------------------------------------

    async def list_accessible_bindings(self) -> list[JsonObject]:
        bindings = await self._service.list_my_bindings()
        return [await self._public(binding) for binding in bindings]

    async def create_mailbox(
        self,
        *,
        kind: str = "role",
        local_part: str | None = None,
        user_id: str | None = None,
        email_address: str | None = None,
        password: str | None = None,
        provision: bool = True,
        sync_enabled: bool = True,
        is_default: bool | None = None,
    ) -> JsonObject:
        await self._service.require_company_admin()
        binding = await self._service.bind_mailbox(
            MailboxBindingCreatePayload(
                user_id=user_id,
                kind=MailboxBindingKind(kind),
                local_part=local_part,
                email_address=email_address,
                password=password,
                sync_enabled=sync_enabled,
                provision=provision,
                is_default=is_default,
            )
        )
        return await self._public(binding)

    async def connect_personal(
        self,
        *,
        email_address: str,
        password: str,
        imap_host: str,
        smtp_host: str,
        imap_port: int = 993,
        smtp_port: int = 465,
        use_ssl: bool = True,
        sync_enabled: bool = True,
    ) -> JsonObject:
        binding = await self._service.connect_personal_mailbox(
            PersonalMailboxConnectPayload(
                email_address=email_address,
                password=password,
                imap_host=imap_host,
                imap_port=imap_port,
                smtp_host=smtp_host,
                smtp_port=smtp_port,
                use_ssl=use_ssl,
                sync_enabled=sync_enabled,
            )
        )
        return await self._public(binding)

    async def patch_binding(
        self,
        mailbox_binding_id: str,
        *,
        sync_enabled: bool | None = None,
        password: str | None = None,
        imap_host: str | None = None,
        imap_port: int | None = None,
        smtp_host: str | None = None,
        smtp_port: int | None = None,
        use_ssl: bool | None = None,
        user_id: str | None = None,
        calendar_color: str | None = None,
    ) -> JsonObject:
        binding = await self._service.patch_binding(
            mailbox_binding_id,
            MailboxBindingPatchPayload(
                user_id=user_id,
                sync_enabled=sync_enabled,
                password=password,
                calendar_color=calendar_color,
                imap_host=imap_host,
                imap_port=imap_port,
                smtp_host=smtp_host,
                smtp_port=smtp_port,
                use_ssl=use_ssl,
            ),
        )
        return await self._public(binding)

    async def set_default_binding(self, mailbox_binding_id: str) -> JsonObject:
        binding = await self._service.set_default_binding(mailbox_binding_id)
        return await self._public(binding)

    async def healthcheck_binding(
        self,
        mailbox_binding_id: str,
        *,
        password: str | None = None,
        imap_host: str | None = None,
        imap_port: int | None = None,
        smtp_host: str | None = None,
        smtp_port: int | None = None,
        use_ssl: bool | None = None,
    ) -> JsonObject:
        health = await self._service.healthcheck_binding(
            mailbox_binding_id,
            MailboxBindingHealthcheckPayload(
                password=password,
                imap_host=imap_host,
                imap_port=imap_port,
                smtp_host=smtp_host,
                smtp_port=smtp_port,
                use_ssl=use_ssl,
            ),
        )
        return health.model_dump(mode="json")

    # ------------------------------------------------------------------
    # Role-mailbox members (sharing)
    # ------------------------------------------------------------------

    async def list_members(self, mailbox_binding_id: str) -> list[JsonObject]:
        members = await self._service.list_binding_members_by_user_id_asc(mailbox_binding_id)
        return [member.model_dump(mode="json") for member in members]

    async def add_member(
        self,
        mailbox_binding_id: str,
        *,
        user_id: str,
        role: str = "member",
    ) -> JsonObject:
        member = await self._service.add_binding_member(
            mailbox_binding_id,
            MailboxBindingMemberPayload(
                user_id=user_id,
                role=MailboxBindingMemberRole(role),
            ),
        )
        return member.model_dump(mode="json")

    async def remove_member(
        self,
        mailbox_binding_id: str,
        *,
        user_id: str,
    ) -> JsonObject:
        await self._service.remove_binding_member(mailbox_binding_id, user_id)
        return {
            "removed": True,
            "mailbox_binding_id": mailbox_binding_id,
            "user_id": user_id,
        }

    # ------------------------------------------------------------------
    # Folders & messages read
    # ------------------------------------------------------------------

    async def list_folders(self, mailbox_binding_id: str) -> JsonObject:
        result = await self._service.list_folders(mailbox_binding_id)
        return result.model_dump(mode="json")

    async def list_messages(
        self,
        *,
        mailbox_binding_id: str,
        folder: str = "INBOX",
        limit: int = 50,
        cursor: str | None = None,
    ) -> JsonObject:
        result = await self._service.list_messages(
            MailMessageListPayload(
                mailbox_binding_id=mailbox_binding_id,
                folder=folder,
                limit=limit,
                cursor=cursor,
            )
        )
        return result.model_dump(mode="json")

    async def search_messages(
        self,
        *,
        mailbox_binding_id: str,
        q: str,
        folder: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> JsonObject:
        result = await self._service.search_messages(
            MailMessageSearchPayload(
                mailbox_binding_id=mailbox_binding_id,
                q=q,
                folder=folder,
                limit=limit,
                cursor=cursor,
            )
        )
        return result.model_dump(mode="json")

    async def get_message(
        self,
        *,
        mailbox_binding_id: str,
        uid: str,
        folder: str = "INBOX",
    ) -> JsonObject:
        message = await self._service.get_message(
            mailbox_binding_id=mailbox_binding_id,
            uid=uid,
            folder=folder,
        )
        await enqueue_mail_mark_seen(
            company_id=self._company_id(),
            mailbox_binding_id=mailbox_binding_id,
            folder=folder,
            uid=uid,
        )
        return message.model_dump(mode="json")

    async def get_thread(
        self,
        *,
        mailbox_binding_id: str,
        uid: str,
        folder: str = "INBOX",
    ) -> JsonObject:
        result = await self._service.get_thread(
            MailThreadPayload(
                mailbox_binding_id=mailbox_binding_id,
                folder=folder,
                uid=uid,
            )
        )
        for marked_uid in result.marked_seen_uids:
            await enqueue_mail_mark_seen(
                company_id=self._company_id(),
                mailbox_binding_id=mailbox_binding_id,
                folder=folder,
                uid=marked_uid,
            )
        return result.model_dump(mode="json")

    async def sync_now(self, mailbox_binding_id: str) -> JsonObject:
        result = await self._service.request_sync_now(
            MailSyncNowPayload(mailbox_binding_id=mailbox_binding_id)
        )
        return result.model_dump(mode="json")

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def _resolve_sender_binding(
        self,
        *,
        mailbox_binding_id: str | None,
        from_local_part: str | None,
    ) -> MailboxBinding:
        bindings = await self._service.list_my_bindings()
        if mailbox_binding_id is not None and mailbox_binding_id.strip() != "":
            requested = mailbox_binding_id.strip()
            match = next(
                (b for b in bindings if b.mailbox_binding_id == requested),
                None,
            )
            if match is None:
                raise MailPermissionError(
                    f"mailbox_binding_id={requested!r} not found among accessible"
                    + " mailboxes (or no permission to send from it)"
                )
            return match
        if from_local_part is not None and from_local_part.strip() != "":
            wanted = from_local_part.strip().lower()
            matches = [b for b in bindings if b.local_part.lower() == wanted]
            role_match = next(
                (b for b in matches if b.kind == MailboxBindingKind.ROLE),
                None,
            )
            if role_match is not None:
                return role_match
            if matches:
                return matches[0]
            accessible = sorted(b.local_part for b in bindings)
            raise MailPermissionError(
                f"no accessible mailbox with local_part={wanted!r};"
                + f" accessible local_parts: {accessible!r}"
            )
        default = next((b for b in bindings if b.is_default), None)
        if default is not None:
            return default
        accessible = sorted(b.local_part for b in bindings)
        raise MailConfigError(
            "sender is not specified (mailbox_binding_id/from_local_part) and no"
            + f" default mailbox found; accessible local_parts: {accessible!r}"
        )

    async def send(
        self,
        *,
        to_addresses: list[str],
        subject: str,
        body_text: str,
        body_html: str | None = None,
        from_local_part: str | None = None,
        mailbox_binding_id: str | None = None,
        sender_display_name: str | None = None,
        in_reply_to: str | None = None,
        references: str | None = None,
        attachments: list[MailAttachment] | None = None,
    ) -> JsonObject:
        binding = await self._resolve_sender_binding(
            mailbox_binding_id=mailbox_binding_id,
            from_local_part=from_local_part,
        )
        from_address: str | None = None
        if sender_display_name is not None and sender_display_name.strip() != "":
            from_address = f"{sender_display_name.strip()} <{binding.email_address}>"
        result = await self._service.send_message(
            MailSendPayload(
                mailbox_binding_id=binding.mailbox_binding_id,
                to_addresses=to_addresses,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                from_address=from_address,
                in_reply_to=in_reply_to,
                references=references,
                attachments=list(attachments or []),
            )
        )
        return {
            "message_id": result.message_id,
            "accepted": list(result.accepted),
            "mailbox_binding_id": binding.mailbox_binding_id,
            "from_address": binding.email_address,
        }

    async def save_draft(
        self,
        *,
        mailbox_binding_id: str,
        to_addresses: list[str],
        subject: str,
        body_text: str,
        body_html: str | None = None,
        uid: str | None = None,
        in_reply_to: str | None = None,
        references: str | None = None,
    ) -> JsonObject:
        result = await self._service.save_draft(
            MailDraftSavePayload(
                mailbox_binding_id=mailbox_binding_id,
                to_addresses=to_addresses,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                uid=uid,
                in_reply_to=in_reply_to,
                references=references,
            )
        )
        return result.model_dump(mode="json")

    async def set_flags(
        self,
        *,
        mailbox_binding_id: str,
        uid: str,
        folder: str = "INBOX",
        seen: bool | None = None,
        flagged: bool | None = None,
    ) -> JsonObject:
        if seen is None and flagged is None:
            raise ValueError("set_flags: seen or flagged is required")
        unread: bool | None = None
        flag_payload = MailMessageFlagPayload(
            mailbox_binding_id=mailbox_binding_id,
            folder=folder,
            uid=uid,
        )
        if seen is True:
            unread = (await self._service.mark_message_seen(flag_payload)).unread
        elif seen is False:
            unread = (await self._service.mark_message_unseen(flag_payload)).unread
        flagged_result: bool | None = None
        if flagged is not None:
            flagged_result = (
                await self._service.star_message(
                    MailMessageStarPayload(
                        mailbox_binding_id=mailbox_binding_id,
                        folder=folder,
                        uid=uid,
                        flagged=flagged,
                    )
                )
            ).flagged
        return {"uid": uid, "unread": unread, "flagged": flagged_result}

    async def move_message(
        self,
        *,
        mailbox_binding_id: str,
        uid: str,
        folder: str = "INBOX",
        destination_folder: str | None = None,
        destination_role: str | None = None,
    ) -> JsonObject:
        if destination_role is not None and destination_role.strip() != "":
            resolved_destination = await self._service.resolve_folder_name_for_role(
                mailbox_binding_id,
                MailFolderRole(destination_role.strip().lower()),
            )
        elif destination_folder is not None and destination_folder.strip() != "":
            resolved_destination = destination_folder.strip()
        else:
            raise ValueError("move_message: destination_folder or destination_role is required")
        result = await self._service.move_message(
            MailMessageMovePayload(
                mailbox_binding_id=mailbox_binding_id,
                folder=folder,
                uid=uid,
                destination_folder=resolved_destination,
            )
        )
        return result.model_dump(mode="json")
