"""Сборка MailServerPort из CompanyMailConnection."""

from __future__ import annotations

from core.ai.company_settings import decrypt_secret
from core.mail.exceptions import MailConfigError
from core.mail.models import CompanyMailConnection, MailProvider
from core.mail.ports import MailServerPort
from core.mail.providers.generic_imap_smtp import GenericImapSmtpMailServerPort
from core.mail.providers.ispmanager import IspmanagerMailServerPort
from core.mail.transport.imap_smtp import ImapSmtpTransport


def build_mail_server_port(
    connection: CompanyMailConnection,
    *,
    protected_local_parts: frozenset[str],
    delete_prefix_required: str | None = None,
    allow_delete: bool = True,
) -> MailServerPort:
    transport = ImapSmtpTransport(
        imap_host=connection.imap_host,
        imap_port=connection.imap_port,
        smtp_host=connection.smtp_host,
        smtp_port=connection.smtp_port,
        use_ssl=connection.use_ssl,
    )
    if connection.provider == MailProvider.GENERIC_IMAP_SMTP:
        return GenericImapSmtpMailServerPort(transport)

    if connection.provider != MailProvider.ISPMANAGER:
        raise MailConfigError(f"Unknown mail provider: {connection.provider}")

    if connection.ispmanager is None:
        raise MailConfigError("ISPmanager connection requires ispmanager config")
    password_encrypted = connection.ispmanager.authinfo_password_encrypted
    if password_encrypted is None or not password_encrypted.strip():
        raise MailConfigError("ISPmanager authinfo_password_encrypted is required")
    authinfo_password = decrypt_secret(password_encrypted)
    return IspmanagerMailServerPort(
        base_url=connection.ispmanager.base_url,
        authinfo_user=connection.ispmanager.authinfo_user,
        authinfo_password=authinfo_password,
        transport=transport,
        protected_local_parts=protected_local_parts,
        delete_prefix_required=delete_prefix_required,
        allow_delete=allow_delete,
    )
