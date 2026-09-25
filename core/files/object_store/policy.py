"""Одна политика доступа к байтам файла."""

from __future__ import annotations

from core.authz.models import AuthzObject
from core.authz.service import AuthzService
from core.errors.boundary import PlatformAccessDeniedError
from core.files.create_spec import FileSourceKind
from core.files.models import FileRecord
from core.files.object_store.principals import (
    AnonymousPrincipal,
    FilePrincipal,
    SessionPrincipal,
    SignedFileGrant,
)
from core.types import JsonObject


def _source_kind(record: FileRecord) -> FileSourceKind | None:
    raw = record.metadata.get("source_kind")
    if not isinstance(raw, str) or raw == "":
        return None
    try:
        return FileSourceKind(raw)
    except ValueError:
        return None


def _source_ref(record: FileRecord) -> JsonObject:
    raw = record.metadata.get("source_ref")
    if isinstance(raw, dict):
        return raw
    return {}


def _ref_str(ref: JsonObject, key: str) -> str | None:
    value = ref.get(key)
    if isinstance(value, str) and value != "":
        return value
    return None


async def _parent_check(authz: AuthzService, record: FileRecord) -> None:
    kind = _source_kind(record)
    if kind is None:
        return
    ref = _source_ref(record)
    if kind is FileSourceKind.OFFICE_DOCUMENT:
        await authz.require_can_view(AuthzObject.office_document(record.file_id))
        return
    channel_id = _ref_str(ref, "channel_id")
    if kind in (
        FileSourceKind.SYNC_MESSAGE,
        FileSourceKind.SYNC_CALL_RECORDING,
        FileSourceKind.SYNC_SPEECH_SEGMENT,
        FileSourceKind.SYNC_CHANNEL_ASSET,
    ) and channel_id is not None:
        await authz.require_can_view(AuthzObject.sync_channel(channel_id))
        return
    entity_id = _ref_str(ref, "entity_id")
    if kind is FileSourceKind.CRM_ENTITY and entity_id is not None:
        await authz.require_can_view(AuthzObject.crm_entity(entity_id))
        return
    wiki_page_id = _ref_str(ref, "wiki_page_id")
    if kind is FileSourceKind.WIKI_PAGE and wiki_page_id is not None:
        await authz.require_can_view(AuthzObject.wiki_page(wiki_page_id))
        return
    work_queue_id = _ref_str(ref, "work_queue_id")
    if kind is FileSourceKind.WORK_ITEM and work_queue_id is not None:
        await authz.require_can_view(AuthzObject.work_queue(work_queue_id))
        return
    flow_id = _ref_str(ref, "flow_id")
    if kind in (FileSourceKind.FLOW_ASSET, FileSourceKind.FLOW_SESSION, FileSourceKind.CODE_AGENT_SOURCE):
        if flow_id is not None and record.company_id is not None:
            await authz.require_can_view(AuthzObject.flow(flow_id, company_id=record.company_id))
        return
    mailbox_binding_id = _ref_str(ref, "mailbox_binding_id")
    if kind is FileSourceKind.MAIL_MESSAGE and mailbox_binding_id is not None:
        await authz.require_can_view(AuthzObject.mailbox_binding(mailbox_binding_id))


async def authorize_file(
    record: FileRecord,
    principal: FilePrincipal,
    authz: AuthzService | None,
) -> None:
    if isinstance(principal, SignedFileGrant):
        if principal.file_id != record.file_id:
            raise PlatformAccessDeniedError("signed file grant does not match file_id")
        if record.company_id is not None and principal.company_id != record.company_id:
            raise PlatformAccessDeniedError("signed file grant company does not match file")
        return
    if record.is_public:
        return
    if isinstance(principal, AnonymousPrincipal):
        raise PlatformAccessDeniedError("anonymous access requires a public file")
    if record.company_id is None or record.company_id == "":
        raise PlatformAccessDeniedError("file has no company")
    if principal.company_id != record.company_id:
        raise PlatformAccessDeniedError("file belongs to another company")
    if isinstance(principal, SessionPrincipal):
        if authz is None:
            raise ValueError("SessionPrincipal requires AuthzService")
        await authz.require_can_view(AuthzObject.company(record.company_id))
        await _parent_check(authz, record)
        return
    return
