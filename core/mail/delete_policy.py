"""Правила разрешения delete_mailbox (fail-closed до HTTP к панели)."""

from __future__ import annotations

from core.mail.exceptions import MailDeleteDeniedError


def assert_mailbox_delete_allowed(
    email_address: str,
    *,
    protected_local_parts: frozenset[str],
    allow_delete: bool,
    delete_prefix_required: str | None,
) -> None:
    normalized = email_address.strip().lower()
    if "@" not in normalized:
        raise ValueError(f"delete_mailbox: invalid email_address={email_address!r}")
    local_part, _domain = normalized.split("@", 1)
    if local_part in protected_local_parts:
        raise MailDeleteDeniedError(normalized, "protected role local_part")
    if not allow_delete:
        raise MailDeleteDeniedError(normalized, "allow_delete=false")
    if delete_prefix_required is not None:
        if not local_part.startswith(delete_prefix_required):
            raise MailDeleteDeniedError(
                normalized,
                f"local_part must start with {delete_prefix_required!r}",
            )
