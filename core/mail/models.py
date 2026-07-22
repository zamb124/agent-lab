"""Доменные модели платформенной почты."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from core.models.base import StrictBaseModel


class MailProvider(StrEnum):
    ISPMANAGER = "ispmanager"
    GENERIC_IMAP_SMTP = "generic_imap_smtp"


class MailConnectionStatus(StrEnum):
    ACTIVE = "active"
    DEGRADED = "degraded"
    DISABLED = "disabled"


class MailConnectionScope(StrEnum):
    COMPANY = "company"
    PERSONAL = "personal"


class MailboxBindingKind(StrEnum):
    USER = "user"
    ROLE = "role"


class MailUserLocalPartStrategy(StrEnum):
    SLUG_UNIQUE = "slug_unique"


class MailFolderRole(StrEnum):
    INBOX = "inbox"
    SENT = "sent"
    DRAFTS = "drafts"
    TRASH = "trash"
    JUNK = "junk"
    ARCHIVE = "archive"
    OTHER = "other"


class MailRagIndexStatus(StrEnum):
    """Статус фоновой RAG-индексации письма (не блокирует local-first persist)."""

    READY = "ready"
    PENDING = "pending"
    FAILED = "failed"
    SKIPPED = "skipped"


class MailFolder(StrictBaseModel):
    name: str
    delimiter: str | None = None
    flags: list[str] = Field(default_factory=list)
    role: MailFolderRole = MailFolderRole.OTHER
    selectable: bool = True
    unseen_count: int = Field(default=0, ge=0)
    message_count: int = Field(default=0, ge=0)
    sort_index: int = Field(default=0)


class MailFolderListResult(StrictBaseModel):
    folders: list[MailFolder] = Field(default_factory=list)
    namespace_prefix: str = ""
    delimiter: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    missing_standard_roles: list[MailFolderRole] = Field(default_factory=list)
    stale: bool = False
    needs_sync: bool = False


class MailFoldersEnsurePayload(StrictBaseModel):
    mailbox_binding_id: str


class MailFoldersReorderPayload(StrictBaseModel):
    mailbox_binding_id: str
    folder_names: list[str] = Field(min_length=1)

class StoredMailAttachmentRef(StrictBaseModel):
    """Ссылка на вложение в локальном store (file_id после materialize)."""

    filename: str = Field(min_length=1)
    content_type: str = Field(min_length=1)
    size: int = Field(default=0, ge=0)
    file_id: str | None = None
    available: bool = True
    parse_error: str | None = None


class IspmanagerProvisionConfig(StrictBaseModel):
    base_url: str
    authinfo_user: str
    authinfo_password_encrypted: str | None = None


class CompanyMailConnection(StrictBaseModel):
    company_mail_connection_id: str
    company_id: str
    scope: MailConnectionScope = MailConnectionScope.COMPANY
    owner_user_id: str | None = None
    mail_domain: str
    provider: MailProvider
    imap_host: str
    imap_port: int = Field(ge=1, le=65535)
    smtp_host: str
    smtp_port: int = Field(ge=1, le=65535)
    use_ssl: bool = True
    supports_provision: bool
    status: MailConnectionStatus = MailConnectionStatus.ACTIVE
    ispmanager: IspmanagerProvisionConfig | None = None
    created_at: datetime
    updated_at: datetime


class CompanyMailConnectionUpsertPayload(StrictBaseModel):
    mail_domain: str
    provider: MailProvider
    imap_host: str
    imap_port: int = Field(ge=1, le=65535)
    smtp_host: str
    smtp_port: int = Field(ge=1, le=65535)
    use_ssl: bool = True
    ispmanager_base_url: str | None = None
    ispmanager_authinfo_user: str | None = None
    ispmanager_authinfo_password: str | None = None
    status: MailConnectionStatus = MailConnectionStatus.ACTIVE


class MailboxBinding(StrictBaseModel):
    mailbox_binding_id: str
    company_id: str
    company_mail_connection_id: str
    user_id: str | None = None
    kind: MailboxBindingKind
    email_address: str
    local_part: str
    sync_enabled: bool = True
    is_default: bool = False
    calendar_color: str = "default"
    password_encrypted: str | None = None
    created_at: datetime
    updated_at: datetime


class MailboxBindingCreatePayload(StrictBaseModel):
    user_id: str | None = None
    kind: MailboxBindingKind = MailboxBindingKind.USER
    local_part: str | None = None
    email_address: str | None = None
    password: str | None = None
    sync_enabled: bool = True
    provision: bool = True
    is_default: bool | None = None
    calendar_color: str | None = None


class PersonalMailboxConnectPayload(StrictBaseModel):
    email_address: str = Field(min_length=3)
    password: str = Field(min_length=1)
    imap_host: str = Field(min_length=1)
    imap_port: int = Field(ge=1, le=65535, default=993)
    smtp_host: str = Field(min_length=1)
    smtp_port: int = Field(ge=1, le=65535, default=465)
    use_ssl: bool = True
    sync_enabled: bool = True
    calendar_color: str | None = None


class PersonalMailboxHealthcheckPayload(StrictBaseModel):
    email_address: str = Field(min_length=3)
    password: str = Field(min_length=1)
    imap_host: str = Field(min_length=1)
    imap_port: int = Field(ge=1, le=65535, default=993)
    smtp_host: str = Field(min_length=1)
    smtp_port: int = Field(ge=1, le=65535, default=465)
    use_ssl: bool = True


class MailboxBindingHealthcheckPayload(StrictBaseModel):
    """Проверка login существующего binding; password/hosts опциональны (иначе stored)."""

    password: str | None = None
    imap_host: str | None = None
    imap_port: int | None = Field(default=None, ge=1, le=65535)
    smtp_host: str | None = None
    smtp_port: int | None = Field(default=None, ge=1, le=65535)
    use_ssl: bool | None = None


class MailboxBindingPatchPayload(StrictBaseModel):
    user_id: str | None = None
    sync_enabled: bool | None = None
    password: str | None = None
    calendar_color: str | None = None
    imap_host: str | None = None
    imap_port: int | None = Field(default=None, ge=1, le=65535)
    smtp_host: str | None = None
    smtp_port: int | None = Field(default=None, ge=1, le=65535)
    use_ssl: bool | None = None


class MailboxBindingPublic(StrictBaseModel):
    mailbox_binding_id: str
    company_id: str
    company_mail_connection_id: str
    connection_scope: MailConnectionScope
    user_id: str | None = None
    kind: MailboxBindingKind
    email_address: str
    local_part: str
    sync_enabled: bool
    is_default: bool
    calendar_color: str
    has_password: bool
    imap_host: str | None = None
    imap_port: int | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    use_ssl: bool | None = None
    created_at: datetime
    updated_at: datetime


class MailMessageListPayload(StrictBaseModel):
    mailbox_binding_id: str
    folder: str = "INBOX"
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = None


class MailMessageListItem(StrictBaseModel):
    uid: str
    message_id: str | None = None
    subject: str | None = None
    from_address: str | None = None
    to_addresses: list[str] = Field(default_factory=list)
    snippet: str | None = None
    attachment_count: int = 0
    unread: bool = True
    flagged: bool = False
    date: datetime | None = None
    in_reply_to: str | None = None
    references: str | None = None
    rag_index_status: MailRagIndexStatus = MailRagIndexStatus.SKIPPED


class MailMessageRagIndexPayload(StrictBaseModel):
    mailbox_binding_id: str
    folder: str = "INBOX"
    uid: str


class MailMessageRagIndexResult(StrictBaseModel):
    accepted: bool
    mailbox_binding_id: str
    folder: str
    uid: str
    rag_index_status: MailRagIndexStatus


class MailMessageListResult(StrictBaseModel):
    """List + sync meta (до CursorPage wrapper в API)."""

    items: list[MailMessageListItem] = Field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool = False
    needs_sync: bool = False


class MailMessageFlagPayload(StrictBaseModel):
    mailbox_binding_id: str
    folder: str = "INBOX"
    uid: str


class MailMessageFlagResult(StrictBaseModel):
    uid: str
    unread: bool


class MailSyncNowPayload(StrictBaseModel):
    mailbox_binding_id: str


class MailSyncNowResult(StrictBaseModel):
    accepted: bool
    mailbox_binding_id: str


class MailMessageMovePayload(StrictBaseModel):
    mailbox_binding_id: str
    folder: str
    uid: str
    destination_folder: str


class MailMessageMoveResult(StrictBaseModel):
    uid: str
    folder: str
    destination_folder: str
    destination_uid: str | None = None


class MailMessageStarPayload(StrictBaseModel):
    mailbox_binding_id: str
    folder: str = "INBOX"
    uid: str
    flagged: bool


class MailMessageStarResult(StrictBaseModel):
    uid: str
    flagged: bool


class MailDraftSavePayload(StrictBaseModel):
    mailbox_binding_id: str
    subject: str = ""
    body_text: str = ""
    body_html: str | None = None
    to_addresses: list[str] = Field(default_factory=list)
    uid: str | None = None
    in_reply_to: str | None = None
    references: str | None = None


class MailDraftSaveResult(StrictBaseModel):
    uid: str
    folder: str
    message_id: str | None = None


class MailMessageSearchPayload(StrictBaseModel):
    mailbox_binding_id: str
    q: str = Field(min_length=1)
    folder: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = None


class MailboxBindingMemberRole(StrEnum):
    MEMBER = "member"
    MANAGER = "manager"


class MailboxBindingMember(StrictBaseModel):
    mailbox_binding_id: str
    user_id: str
    company_id: str
    role: MailboxBindingMemberRole
    created_at: datetime


class MailboxBindingMemberPayload(StrictBaseModel):
    user_id: str
    role: MailboxBindingMemberRole = MailboxBindingMemberRole.MEMBER


class MailThreadPayload(StrictBaseModel):
    mailbox_binding_id: str
    folder: str = "INBOX"
    uid: str


class MailAttachmentPublic(StrictBaseModel):
    filename: str
    content_type: str
    size: int
    available: bool = True
    parse_error: str | None = None
    file_id: str | None = None
    content_base64: str | None = None


class InboundMailMessagePublic(StrictBaseModel):
    uid: str
    message_id: str | None = None
    subject: str | None = None
    from_address: str | None = None
    to_addresses: list[str] = Field(default_factory=list)
    body_text: str | None = None
    body_html: str | None = None
    unread: bool = True
    flagged: bool = False
    date: datetime | None = None
    in_reply_to: str | None = None
    references: str | None = None
    attachments: list[MailAttachmentPublic] = Field(default_factory=list)


class MailThreadMessagePublic(InboundMailMessagePublic):
    folder: str


class MailThreadResult(StrictBaseModel):
    thread_id: str
    subject: str | None = None
    participant_emails: list[str] = Field(default_factory=list)
    items: list[MailThreadMessagePublic] = Field(default_factory=list)
    # UID в payload.folder, которые локально помечены seen при открытии треда (для IMAP enqueue).
    marked_seen_uids: list[str] = Field(default_factory=list)


class CompanyMailConnectionPublic(StrictBaseModel):
    company_mail_connection_id: str
    company_id: str
    scope: MailConnectionScope
    owner_user_id: str | None = None
    mail_domain: str
    provider: MailProvider
    imap_host: str
    imap_port: int
    smtp_host: str
    smtp_port: int
    use_ssl: bool
    supports_provision: bool
    status: MailConnectionStatus
    has_ispmanager_auth: bool
    created_at: datetime
    updated_at: datetime


class MailboxSecret(StrictBaseModel):
    email_address: str
    password: str


class MailboxEnsureSpec(StrictBaseModel):
    mail_domain: str
    local_part: str
    password: str


class MailboxInfo(StrictBaseModel):
    email_address: str
    local_part: str
    mail_domain: str


class MailServerHealth(StrictBaseModel):
    provider: MailProvider
    provision_ok: bool
    imap_ok: bool
    smtp_ok: bool
    detail: str | None = None


class MailAttachment(StrictBaseModel):
    """Вложение письма (MIME part). content может быть пустым при list/ошибке разбора."""

    filename: str = Field(min_length=1)
    content_type: str = Field(min_length=1)
    content: bytes = Field(default=b"")
    size: int = Field(default=0, ge=0)
    available: bool = True
    parse_error: str | None = None


class MailSendPayload(StrictBaseModel):
    mailbox_binding_id: str
    to_addresses: list[str] = Field(min_length=1)
    subject: str
    body_text: str
    body_html: str | None = None
    message_id: str | None = None
    in_reply_to: str | None = None
    references: str | None = None
    attachments: list[MailAttachment] = Field(default_factory=list)


class OutboundMailMessage(StrictBaseModel):
    to_addresses: list[str] = Field(min_length=1)
    subject: str
    body_text: str
    body_html: str | None = None
    message_id: str | None = None
    from_address: str | None = None
    in_reply_to: str | None = None
    references: str | None = None
    attachments: list[MailAttachment] = Field(default_factory=list)


class MailSendResult(StrictBaseModel):
    message_id: str
    accepted: list[str]


class MailFetchQuery(StrictBaseModel):
    mailbox: str = "INBOX"
    subject_contains: str | None = None
    message_id: str | None = None
    limit: int = Field(default=20, ge=1, le=200)
    include_bodies: bool = True


class InboundMailMessage(StrictBaseModel):
    uid: str
    message_id: str | None = None
    subject: str | None = None
    from_address: str | None = None
    to_addresses: list[str] = Field(default_factory=list)
    body_text: str | None = None
    body_html: str | None = None
    unread: bool = True
    flagged: bool = False
    answered: bool = False
    draft: bool = False
    date: datetime | None = None
    in_reply_to: str | None = None
    references: str | None = None
    attachments: list[MailAttachment] = Field(default_factory=list)


class MailImapSystemFlag(StrEnum):
    SEEN = "\\Seen"
    FLAGGED = "\\Flagged"
    DELETED = "\\Deleted"
    ANSWERED = "\\Answered"
    DRAFT = "\\Draft"


class MailMessageFlags(StrictBaseModel):
    unread: bool = True
    flagged: bool = False
    answered: bool = False
    draft: bool = False
    deleted: bool = False


class MailUidSearchCriteria(StrictBaseModel):
    all_messages: bool = False
    uid_set: str | None = None
    text: str | None = None
    from_address: str | None = None
    subject: str | None = None
    header_name: str | None = None
    header_value: str | None = None


class MailUidMoveResult(StrictBaseModel):
    source_uid: str
    destination_folder: str
    destination_uid: str | None = None


class MailAppendResult(StrictBaseModel):
    folder: str
    uid: str | None = None
    message_id: str | None = None


class MailIdleWakeKind(StrEnum):
    EXISTS = "exists"
    RECENT = "recent"
    EXPUNGE = "expunge"
    TIMEOUT = "timeout"
    BYE = "bye"
    OTHER = "other"


class MailIdleWake(StrictBaseModel):
    kind: MailIdleWakeKind
    raw: str = ""


class MailReconcileResult(StrictBaseModel):
    connection_ensured: bool
    role_mailboxes_ensured: list[str]
    user_bindings_ensured: list[str]


class MailSyncErrorKind(StrEnum):
    AUTH = "auth"
    NETWORK = "network"
    VALIDATION = "validation"
    UNKNOWN = "unknown"


class MailboxSyncCursor(StrictBaseModel):
    mailbox_binding_id: str
    folder: str
    company_id: str
    uidvalidity: int
    last_uid: int
    backfill_completed: bool = False
    oldest_uid: int | None = None
    last_reconcile_at: datetime | None = None
    last_synced_at: datetime | None = None
    last_attempt_at: datetime | None = None
    last_error_kind: MailSyncErrorKind | None = None
    last_error_at: datetime | None = None
    last_error_message: str | None = None


class StoredMailMessage(StrictBaseModel):
    """Локальное письмо (body + attachments_json + RAG ids)."""

    mail_message_id: str
    company_id: str
    mailbox_binding_id: str
    user_id: str | None = None
    folder: str
    uid: int
    message_id: str | None = None
    thread_id: str
    subject: str = ""
    from_address: str = ""
    to_addresses: list[str] = Field(default_factory=list)
    cc_addresses: list[str] = Field(default_factory=list)
    date_at: datetime | None = None
    unread: bool = True
    flagged: bool = False
    answered: bool = False
    draft: bool = False
    has_attachments: bool = False
    snippet: str = ""
    body_text: str | None = None
    body_html: str | None = None
    attachments: list[StoredMailAttachmentRef] = Field(default_factory=list)
    in_reply_to: str | None = None
    references: str | None = None
    rag_document_id: str | None = None
    rag_namespace: str | None = None
    rag_index_status: MailRagIndexStatus = MailRagIndexStatus.SKIPPED
    synced_at: datetime
    created_at: datetime
    updated_at: datetime


class MailUidBatch(StrictBaseModel):
    """Результат инкрементального IMAP peek (заголовки, не полные тела)."""

    uidvalidity: int
    max_uid: int
    messages: list[InboundMailMessage] = Field(default_factory=list)


class MailSyncBindingResult(StrictBaseModel):
    mailbox_binding_id: str
    company_id: str
    user_id: str | None
    email_address: str
    new_messages: list[InboundMailMessage] = Field(default_factory=list)
    bootstrap: bool = False
    skipped_reason: str | None = None
    backfill_remaining: bool = False


class MailSyncLagStats(StrictBaseModel):
    """Метрики fairness drain для mail_sync_tick."""

    bindings_pending: int = 0
    max_lag_seconds: int = 0
    candidates_total: int = 0


class StoredMailboxFolder(StrictBaseModel):
    mailbox_binding_id: str
    folder_name: str
    company_id: str
    role: MailFolderRole = MailFolderRole.OTHER
    delimiter: str | None = None
    flags: list[str] = Field(default_factory=list)
    selectable: bool = True
    message_count: int = Field(default=0, ge=0)
    unseen_count: int = Field(default=0, ge=0)
    namespace_prefix: str = ""
    capabilities: list[str] = Field(default_factory=list)
    sort_index: int = 0
    updated_at: datetime
