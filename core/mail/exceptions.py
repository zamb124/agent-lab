"""Типизированные ошибки почтового слоя."""

from __future__ import annotations

from typing import Final


class MailError(Exception):
    """Базовая ошибка почтового слоя."""


class MailConnectionNotFoundError(MailError):
    company_id: Final[str]

    def __init__(self, company_id: str) -> None:
        super().__init__(f"CompanyMailConnection not found for company_id={company_id}")
        self.company_id = company_id


class MailBindingNotFoundError(MailError):
    mailbox_binding_id: Final[str]

    def __init__(self, mailbox_binding_id: str) -> None:
        super().__init__(f"MailboxBinding not found: {mailbox_binding_id}")
        self.mailbox_binding_id = mailbox_binding_id


class MailMessageNotFoundError(MailError):
    mailbox_binding_id: Final[str]
    uid: Final[str]

    def __init__(self, mailbox_binding_id: str, uid: str) -> None:
        super().__init__(
            f"Mail message not found: mailbox_binding_id={mailbox_binding_id} uid={uid}"
        )
        self.mailbox_binding_id = mailbox_binding_id
        self.uid = uid


class MailUidNotFoundError(MailError):
    """UID отсутствует в выбранном IMAP mailbox (транспортный уровень)."""

    mailbox: Final[str]
    uid: Final[str]

    def __init__(self, mailbox: str, uid: str) -> None:
        super().__init__(f"IMAP message not found: mailbox={mailbox!r} uid={uid}")
        self.mailbox = mailbox
        self.uid = uid


class MailProvisionUnsupportedError(MailError):
    provider: Final[str]

    def __init__(self, provider: str) -> None:
        super().__init__(f"Mail provision unsupported for provider={provider}")
        self.provider = provider


class MailSystemConnectionReadOnlyError(MailError):
    def __init__(self) -> None:
        super().__init__(
            "CompanyMailConnection for company_id=system is read-only; use reconcile from conf"
        )


class MailDeleteDeniedError(MailError):
    email_address: Final[str]
    reason: Final[str]

    def __init__(self, email_address: str, reason: str) -> None:
        super().__init__(f"delete_mailbox denied for {email_address}: {reason}")
        self.email_address = email_address
        self.reason = reason


class MailSecretMissingError(MailError):
    email_address: Final[str]

    def __init__(self, email_address: str) -> None:
        super().__init__(f"Mailbox secret missing for {email_address}")
        self.email_address = email_address


class MailMailboxNotFoundError(MailError):
    folder_name: Final[str]

    def __init__(self, *, folder_name: str) -> None:
        super().__init__(f"IMAP mailbox not found: folder_name={folder_name!r}")
        self.folder_name = folder_name


class MailFolderCreateError(MailError):
    folder_name: Final[str]
    role: Final[str | None]

    def __init__(self, *, folder_name: str, role: str | None, detail: str) -> None:
        super().__init__(
            f"IMAP CREATE failed for folder_name={folder_name!r} role={role!r}: {detail}"
        )
        self.folder_name = folder_name
        self.role = role


class MailTransportError(MailError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class MailConfigError(MailError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class MailPermissionError(MailError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
