"""IMAP LIST/NAMESPACE/SPECIAL-USE parser + ensure (без alias resolve)."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.files.create_spec import FileCreateSpec, FileSourceKind, FileSourceRef
from core.files.registry import default_retention_for_source
from core.mail.exceptions import MailMailboxNotFoundError
from core.mail.imap_folders import (
    build_mail_folder_list_result_by_role_and_name_asc,
    parse_imap_list_lines,
    parse_namespace_personal_prefix,
    role_from_flags,
    standard_folder_name,
)
from core.mail.models import (
    CompanyMailConnectionUpsertPayload,
    MailAttachment,
    MailboxBindingCreatePayload,
    MailboxBindingKind,
    MailboxSecret,
    MailFetchQuery,
    MailFolder,
    MailFolderRole,
    MailMessageListPayload,
    MailProvider,
    MailSendPayload,
)
from core.mail.service import MailService
from tests.core.mail.fakes import RecordingMailServerPort

FIXTURES = Path(__file__).parent / "fixtures" / "imap_list"


def _load_fixture(name: str) -> list[str]:
    text = (FIXTURES / name).read_text(encoding="utf-8")
    return [line for line in text.splitlines() if line.strip()]


def test_parse_aioimaplib_stripped_list_and_namespace() -> None:
    entries = parse_imap_list_lines(_load_fixture("aioimaplib_stripped.txt"))
    prefix, delim = parse_namespace_personal_prefix(
        _load_fixture("aioimaplib_namespace.txt")
    )
    assert prefix == ""
    assert delim == "."
    result = build_mail_folder_list_result_by_role_and_name_asc(
        list_entries=entries,
        namespace_prefix=prefix,
        namespace_delimiter=delim,
        capabilities=["IMAP4rev1", "NAMESPACE"],
    )
    names = {folder.name for folder in result.folders}
    assert names == {"INBOX", "Sent", "Drafts", "Trash"}
    assert result.missing_standard_roles == []
    by_role = {folder.role: folder.name for folder in result.folders}
    assert by_role[MailFolderRole.INBOX] == "INBOX"
    assert by_role[MailFolderRole.SENT] == "Sent"
    assert [folder.role for folder in result.folders] == [
        MailFolderRole.INBOX,
        MailFolderRole.SENT,
        MailFolderRole.DRAFTS,
        MailFolderRole.TRASH,
    ]

    entries = parse_imap_list_lines(_load_fixture("dovecot_special_use.txt"))
    result = build_mail_folder_list_result_by_role_and_name_asc(
        list_entries=entries,
        namespace_prefix="",
        namespace_delimiter="/",
        capabilities=["IMAP4rev1", "SPECIAL-USE", "NAMESPACE"],
    )
    by_role = {folder.role: folder.name for folder in result.folders}
    assert by_role[MailFolderRole.INBOX] == "INBOX"
    assert by_role[MailFolderRole.SENT] == "Sent"
    assert by_role[MailFolderRole.DRAFTS] == "Drafts"
    assert by_role[MailFolderRole.TRASH] == "Trash"
    assert result.missing_standard_roles == []


def test_parse_courier_canonical_names_without_special_use() -> None:
    lines = _load_fixture("courier_no_special_use.txt")
    entries = parse_imap_list_lines(lines)
    prefix, delim = parse_namespace_personal_prefix(lines)
    assert prefix == "INBOX."
    assert delim == "."
    result = build_mail_folder_list_result_by_role_and_name_asc(
        list_entries=entries,
        namespace_prefix=prefix,
        namespace_delimiter=delim,
        capabilities=["IMAP4rev1", "NAMESPACE"],
    )
    by_role = {folder.role: folder.name for folder in result.folders}
    assert by_role[MailFolderRole.INBOX] == "INBOX"
    assert by_role[MailFolderRole.SENT] == "INBOX.Sent"
    assert by_role[MailFolderRole.DRAFTS] == "INBOX.Drafts"
    assert by_role[MailFolderRole.TRASH] == "INBOX.Trash"
    assert result.missing_standard_roles == []


def test_sent_exists_without_special_use_not_missing() -> None:
    entries = parse_imap_list_lines(
        [
            '* LIST (\\HasNoChildren) "/" INBOX',
            '* LIST (\\HasNoChildren) "/" Sent',
        ]
    )
    result = build_mail_folder_list_result_by_role_and_name_asc(
        list_entries=entries,
        namespace_prefix="",
        namespace_delimiter="/",
        capabilities=["IMAP4rev1"],
    )
    sent = next(folder for folder in result.folders if folder.name == "Sent")
    assert sent.role == MailFolderRole.SENT
    assert MailFolderRole.SENT not in result.missing_standard_roles
    assert MailFolderRole.DRAFTS in result.missing_standard_roles
    assert MailFolderRole.TRASH in result.missing_standard_roles


def test_parse_regru_cyrillic_special_use() -> None:
    entries = parse_imap_list_lines(_load_fixture("regru_cyrillic_special_use.txt"))
    result = build_mail_folder_list_result_by_role_and_name_asc(
        list_entries=entries,
        namespace_prefix="",
        namespace_delimiter="/",
        capabilities=["SPECIAL-USE"],
    )
    sent = next(folder for folder in result.folders if folder.role == MailFolderRole.SENT)
    assert sent.name == "Отправленные"
    assert result.missing_standard_roles == []


def test_parse_noselect_parent() -> None:
    entries = parse_imap_list_lines(_load_fixture("noselect_parent.txt"))
    result = build_mail_folder_list_result_by_role_and_name_asc(
        list_entries=entries,
        namespace_prefix="",
        namespace_delimiter="/",
        capabilities=["SPECIAL-USE"],
    )
    parent = next(folder for folder in result.folders if folder.name == "[Gmail]")
    assert parent.selectable is False
    assert "\\NOSELECT" in {flag.upper() for flag in parent.flags}
    selectable = [folder for folder in result.folders if folder.selectable]
    assert all(folder.name != "[Gmail]" for folder in selectable)


def test_parse_namespace_inbox_prefix() -> None:
    lines = _load_fixture("namespace_inbox_prefix.txt")
    prefix, delim = parse_namespace_personal_prefix(lines)
    assert prefix == "INBOX."
    assert delim == "."
    assert standard_folder_name(role=MailFolderRole.SENT, namespace_prefix=prefix) == "INBOX.Sent"


def test_role_from_flags_inbox_and_special_use() -> None:
    assert role_from_flags(name="INBOX", flags=frozenset()) == MailFolderRole.INBOX
    assert role_from_flags(name="X", flags=frozenset({"\\SENT"})) == MailFolderRole.SENT
    assert role_from_flags(name="X", flags=frozenset()) == MailFolderRole.OTHER
    assert (
        role_from_flags(name="Sent", flags=frozenset(), namespace_prefix="")
        == MailFolderRole.SENT
    )
    assert (
        role_from_flags(name="Отправленные", flags=frozenset(), namespace_prefix="")
        == MailFolderRole.OTHER
    )


@pytest.mark.asyncio
async def test_recording_port_select_exact_name_only(
    recording_mail_port: RecordingMailServerPort,
) -> None:
    recording_mail_port.imap_folders = [
        MailFolder(name="INBOX", role=MailFolderRole.INBOX, selectable=True),
        MailFolder(
            name="Отправленные",
            role=MailFolderRole.SENT,
            flags=["\\Sent"],
            selectable=True,
        ),
    ]
    secret = MailboxSecret(email_address="a@b.c", password="x")
    listed = await recording_mail_port.list_imap_folders(secret)
    assert any(folder.name == "Отправленные" for folder in listed.folders)

    recording_mail_port.select_fail_names.add("Sent")
    with pytest.raises(MailMailboxNotFoundError):
        _ = await recording_mail_port.fetch_messages(
            secret,
            MailFetchQuery(mailbox="Sent", limit=10),
        )
    fetched = await recording_mail_port.fetch_messages(
        secret,
        MailFetchQuery(mailbox="Отправленные", limit=10),
    )
    assert fetched == []
    assert recording_mail_port.fetch_messages_calls[-1][1] == "Отправленные"


@pytest.mark.asyncio
async def test_ensure_standard_folders_creates_missing(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    unique_id: str,
) -> None:
    company_id = f"mailfolders_{unique_id}"
    _ = await mail_service.upsert_connection(
        CompanyMailConnectionUpsertPayload(
            mail_domain=f"{unique_id}.example.com",
            provider=MailProvider.ISPMANAGER,
            imap_host="imap.example.com",
            imap_port=993,
            smtp_host="smtp.example.com",
            smtp_port=465,
            use_ssl=True,
            ispmanager_base_url="https://panel.example.com:1500/ispmgr",
            ispmanager_authinfo_user="admin",
            ispmanager_authinfo_password="secret-pass",
        ),
        company_id=company_id,
    )
    binding = await mail_service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.USER,
            user_id="test_user",
            local_part=f"alice.{unique_id}",
            password="mailbox-pass-1",
            provision=True,
        ),
        company_id=company_id,
    )
    recording_mail_port.imap_folders = [
        MailFolder(name="INBOX", role=MailFolderRole.INBOX, selectable=True),
    ]
    recording_mail_port.namespace_prefix = ""

    before = await mail_service.refresh_folders_from_imap(
        binding.mailbox_binding_id,
        company_id=company_id,
    )
    assert MailFolderRole.SENT in before.missing_standard_roles

    after = await mail_service.ensure_standard_folders(
        binding.mailbox_binding_id,
        company_id=company_id,
    )
    assert after.missing_standard_roles == []
    created_names = {name for name, _role in recording_mail_port.create_imap_folder_calls}
    assert created_names == {"Sent", "Drafts", "Trash"}

    again = await mail_service.ensure_standard_folders(
        binding.mailbox_binding_id,
        company_id=company_id,
    )
    assert again.missing_standard_roles == []
    assert len(recording_mail_port.create_imap_folder_calls) == 3


@pytest.mark.asyncio
async def test_list_messages_404_on_unknown_exact_folder(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    unique_id: str,
) -> None:
    company_id = f"mailfolders404_{unique_id}"
    _ = await mail_service.upsert_connection(
        CompanyMailConnectionUpsertPayload(
            mail_domain=f"{unique_id}.example.com",
            provider=MailProvider.ISPMANAGER,
            imap_host="imap.example.com",
            imap_port=993,
            smtp_host="smtp.example.com",
            smtp_port=465,
            use_ssl=True,
            ispmanager_base_url="https://panel.example.com:1500/ispmgr",
            ispmanager_authinfo_user="admin",
            ispmanager_authinfo_password="secret-pass",
        ),
        company_id=company_id,
    )
    binding = await mail_service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.USER,
            user_id="test_user",
            local_part=f"bob.{unique_id}",
            password="mailbox-pass-1",
            provision=True,
        ),
        company_id=company_id,
    )
    # Local-first: unknown/empty folder returns empty page, no IMAP SELECT.
    listed = await mail_service.list_messages(
        MailMessageListPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder="Sent",
            limit=10,
        ),
        company_id=company_id,
    )
    assert listed.items == []
    assert listed.needs_sync is True
    assert recording_mail_port.fetch_messages_calls == []


@pytest.mark.asyncio
async def test_send_appends_copy_to_sent_folder(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    mail_member_context,
    unique_id: str,
) -> None:
    company_id = f"mailsent_{unique_id}"
    user_id = f"user_{unique_id}"
    _ = await mail_member_context(company_id=company_id, user_id=user_id)
    _ = await mail_service.upsert_connection(
        CompanyMailConnectionUpsertPayload(
            mail_domain=f"{unique_id}.example.com",
            provider=MailProvider.ISPMANAGER,
            imap_host="imap.example.com",
            imap_port=993,
            smtp_host="smtp.example.com",
            smtp_port=465,
            use_ssl=True,
            ispmanager_base_url="https://panel.example.com:1500/ispmgr",
            ispmanager_authinfo_user="admin",
            ispmanager_authinfo_password="secret-pass",
        ),
        company_id=company_id,
    )
    binding = await mail_service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.USER,
            user_id=user_id,
            local_part=f"carol.{unique_id}",
            password="mailbox-pass-1",
            provision=True,
        ),
        company_id=company_id,
    )
    _ = await mail_service.send_message(
        MailSendPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            to_addresses=["peer@example.com"],
            subject=f"hello-{unique_id}",
            body_text="body",
        ),
        company_id=company_id,
    )
    assert recording_mail_port.append_sent_calls
    assert recording_mail_port.append_sent_calls[-1][1] == "Sent"
    _ = await mail_service.sync_binding(binding, max_new_messages=50)
    sent_messages = await mail_service.list_messages(
        MailMessageListPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder="Sent",
            limit=20,
        ),
        company_id=company_id,
    )
    assert len(sent_messages.items) == 1
    assert sent_messages.items[0].subject == f"hello-{unique_id}"
    inbox_messages = await mail_service.list_messages(
        MailMessageListPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            folder="INBOX",
            limit=20,
        ),
        company_id=company_id,
    )
    assert inbox_messages.items == []


@pytest.mark.asyncio
async def test_send_multipart_html_and_attachment(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    mail_member_context,
    di,
    unique_id: str,
) -> None:
    company_id = f"mailhtml_{unique_id}"
    user_id = "test_user"
    _ = await mail_member_context(company_id=company_id, user_id=user_id)
    _ = await mail_service.upsert_connection(
        CompanyMailConnectionUpsertPayload(
            mail_domain=f"{unique_id}.example.com",
            provider=MailProvider.ISPMANAGER,
            imap_host="imap.example.com",
            imap_port=993,
            smtp_host="smtp.example.com",
            smtp_port=465,
            use_ssl=True,
            ispmanager_base_url="https://panel.example.com:1500/ispmgr",
            ispmanager_authinfo_user="admin",
            ispmanager_authinfo_password="secret-pass",
        ),
        company_id=company_id,
    )
    binding = await mail_service.bind_mailbox(
        MailboxBindingCreatePayload(
            kind=MailboxBindingKind.USER,
            user_id=user_id,
            local_part=f"dave.{unique_id}",
            password="mailbox-pass-1",
            provision=True,
        ),
        company_id=company_id,
    )
    file_record = await di.files_service.create(
        FileCreateSpec(
            source_kind=FileSourceKind.PLATFORM_AUXILIARY,
            source_ref=FileSourceRef(),
            retention=default_retention_for_source(FileSourceKind.PLATFORM_AUXILIARY),
        ),
        b"hello-attach",
        original_name="note.txt",
        content_type="text/plain",
    )
    _ = await mail_service.send_message(
        MailSendPayload(
            mailbox_binding_id=binding.mailbox_binding_id,
            to_addresses=["peer@example.com"],
            subject=f"html-{unique_id}",
            body_text="plain body",
            body_html="<p><strong>html</strong> body</p>",
            attachments=[
                MailAttachment(
                    filename="note.txt",
                    content_type="text/plain",
                    file_id=file_record.file_id,
                )
            ],
        ),
        company_id=company_id,
    )
    assert recording_mail_port.last_sent_body_html == "<p><strong>html</strong> body</p>"
    assert recording_mail_port.sent
    outbound = recording_mail_port.sent[-1][1]
    assert outbound.body_html == "<p><strong>html</strong> body</p>"
    assert len(outbound.attachments) == 1
    assert outbound.attachments[0].filename == "note.txt"
    assert outbound.attachments[0].content == b"hello-attach"
