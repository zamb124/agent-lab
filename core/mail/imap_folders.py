"""IMAP LIST / NAMESPACE / SPECIAL-USE: парсинг и роли (без alias-угадывания имён)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from core.mail.models import MailFolder, MailFolderListResult, MailFolderRole

ImapResponseLine = bytes | bytearray | str

_LIST_LINE_RE = re.compile(
    r'^(?:\* LIST\s+)?\((?P<attrs>[^)]*)\) (?P<delim>"[^"]*"|NIL|\S+) (?P<name>.+)$',
    re.IGNORECASE,
)

_SPECIAL_USE_TO_ROLE: Final[dict[str, MailFolderRole]] = {
    "\\SENT": MailFolderRole.SENT,
    "\\DRAFTS": MailFolderRole.DRAFTS,
    "\\TRASH": MailFolderRole.TRASH,
    "\\JUNK": MailFolderRole.JUNK,
    "\\ARCHIVE": MailFolderRole.ARCHIVE,
}

STANDARD_ENSURE_ROLES: Final[tuple[MailFolderRole, ...]] = (
    MailFolderRole.SENT,
    MailFolderRole.DRAFTS,
    MailFolderRole.TRASH,
)

ROLE_DEFAULT_LOCAL_NAME: Final[dict[MailFolderRole, str]] = {
    MailFolderRole.SENT: "Sent",
    MailFolderRole.DRAFTS: "Drafts",
    MailFolderRole.TRASH: "Trash",
}

_FOLDER_ROLE_SORT_ORDER: Final[dict[MailFolderRole, int]] = {
    MailFolderRole.INBOX: 0,
    MailFolderRole.SENT: 1,
    MailFolderRole.DRAFTS: 2,
    MailFolderRole.TRASH: 3,
    MailFolderRole.JUNK: 4,
    MailFolderRole.ARCHIVE: 5,
    MailFolderRole.OTHER: 6,
}


@dataclass(frozen=True, slots=True)
class ParsedImapListEntry:
    name: str
    attributes: frozenset[str]
    delimiter: str | None


def parse_imap_list_lines(lines: Sequence[ImapResponseLine]) -> list[ParsedImapListEntry]:
    entries: list[ParsedImapListEntry] = []
    for raw in lines:
        if isinstance(raw, str):
            text = raw
        else:
            text = raw.decode("utf-8", errors="replace")
        text = text.strip()
        # aioimaplib часто отдаёт untagged без "* LIST " — только "(attrs) delim name".
        if text.upper().startswith("LIST COMPLETED") or text.upper().startswith("OK "):
            continue
        if not (text.upper().startswith("* LIST ") or text.startswith("(")):
            continue
        match = _LIST_LINE_RE.match(text)
        if match is None:
            continue
        attrs_raw = match.group("attrs").strip()
        attrs = frozenset(
            part.strip().upper() for part in attrs_raw.split() if part.strip()
        )
        delim_raw = match.group("delim")
        delimiter: str | None
        if delim_raw.upper() == "NIL":
            delimiter = None
        elif delim_raw.startswith('"') and delim_raw.endswith('"'):
            delimiter = delim_raw[1:-1]
        else:
            delimiter = delim_raw
        name_raw = match.group("name").strip()
        if name_raw.startswith('"') and name_raw.endswith('"') and len(name_raw) >= 2:
            name = name_raw[1:-1]
        else:
            name = name_raw
        if not name:
            continue
        entries.append(
            ParsedImapListEntry(name=name, attributes=attrs, delimiter=delimiter)
        )
    return entries


def parse_namespace_personal_prefix(lines: Sequence[ImapResponseLine]) -> tuple[str, str | None]:
    """
    Вернуть (prefix, delimiter) персонального NAMESPACE.
    Пустой prefix и delimiter=None — если NAMESPACE недоступен/пуст.
    """
    for raw in lines:
        if isinstance(raw, str):
            text = raw
        else:
            text = raw.decode("utf-8", errors="replace")
        text = text.strip()
        # aioimaplib: "* NAMESPACE ..." или только '(("" ".")) NIL NIL'
        if text.upper().startswith("* NAMESPACE "):
            body = text
        elif text.startswith("((") or text.startswith("(NIL"):
            body = text
        else:
            continue
        personal_match = re.search(
            r'\(\(\s*"([^"]*)"\s+"([^"]*)"\s*\)\)',
            body,
            flags=re.IGNORECASE,
        )
        if personal_match is None:
            personal_nil = re.search(
                r'\(\(\s*NIL\s*NIL\s*\)\)',
                body,
                flags=re.IGNORECASE,
            )
            if personal_nil is not None:
                return "", None
            continue
        return personal_match.group(1), personal_match.group(2)
    return "", None


def role_from_flags(
    *,
    name: str,
    flags: frozenset[str],
    namespace_prefix: str = "",
) -> MailFolderRole:
    if name.casefold() == "inbox":
        return MailFolderRole.INBOX
    for flag, role in _SPECIAL_USE_TO_ROLE.items():
        if flag in flags:
            return role
    # Канонические ensure-имена (Sent/Drafts/Trash под prefix) — не алиасы/локализации.
    for role, local_name in ROLE_DEFAULT_LOCAL_NAME.items():
        if name == f"{namespace_prefix}{local_name}":
            return role
    return MailFolderRole.OTHER


def build_mail_folder_list_result_by_role_and_name_asc(
    *,
    list_entries: list[ParsedImapListEntry],
    namespace_prefix: str,
    namespace_delimiter: str | None,
    capabilities: list[str],
) -> MailFolderListResult:
    delimiter = namespace_delimiter
    folders: list[MailFolder] = []
    for entry in list_entries:
        if delimiter is None and entry.delimiter is not None:
            delimiter = entry.delimiter
        flags = sorted(entry.attributes)
        role = role_from_flags(
            name=entry.name,
            flags=entry.attributes,
            namespace_prefix=namespace_prefix,
        )
        selectable = "\\NOSELECT" not in entry.attributes
        folders.append(
            MailFolder(
                name=entry.name,
                delimiter=entry.delimiter if entry.delimiter is not None else delimiter,
                flags=flags,
                role=role,
                selectable=selectable,
            )
        )
    present_roles = {folder.role for folder in folders}
    existing_names = {folder.name for folder in folders}
    missing: list[MailFolderRole] = []
    for role in STANDARD_ENSURE_ROLES:
        if role in present_roles:
            continue
        canonical = standard_folder_name(role=role, namespace_prefix=namespace_prefix)
        if canonical in existing_names:
            continue
        missing.append(role)
    folders.sort(
        key=lambda folder: (
            _FOLDER_ROLE_SORT_ORDER.get(folder.role, 99),
            folder.name.casefold(),
        )
    )
    return MailFolderListResult(
        folders=folders,
        namespace_prefix=namespace_prefix,
        delimiter=delimiter,
        capabilities=list(capabilities),
        missing_standard_roles=missing,
    )


def standard_folder_name(*, role: MailFolderRole, namespace_prefix: str) -> str:
    local = ROLE_DEFAULT_LOCAL_NAME.get(role)
    if local is None:
        raise ValueError(f"role {role.value} has no standard local name")
    return f"{namespace_prefix}{local}"


def is_imap_already_exists_response(response_text: str) -> bool:
    return "ALREADYEXISTS" in response_text.upper()


def special_use_flag_for_role(role: MailFolderRole) -> str | None:
    for flag, mapped in _SPECIAL_USE_TO_ROLE.items():
        if mapped == role:
            return flag
    return None
