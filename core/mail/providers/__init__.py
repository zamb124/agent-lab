"""Адаптеры почтовых серверов."""

from core.mail.providers.generic_imap_smtp import GenericImapSmtpMailServerPort
from core.mail.providers.ispmanager import IspmanagerMailServerPort

__all__ = ["GenericImapSmtpMailServerPort", "IspmanagerMailServerPort"]
