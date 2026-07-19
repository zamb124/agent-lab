"""Offline: fail-closed delete policy до HTTP."""

from __future__ import annotations

import pytest

from core.mail.delete_policy import assert_mailbox_delete_allowed
from core.mail.exceptions import MailDeleteDeniedError


def test_delete_allowed_with_prefix() -> None:
    assert_mailbox_delete_allowed(
        "plt-abc123@linnex.io",
        protected_local_parts=frozenset({"support", "hr"}),
        allow_delete=True,
        delete_prefix_required="plt-",
    )


def test_delete_denied_protected() -> None:
    with pytest.raises(MailDeleteDeniedError) as exc_info:
        assert_mailbox_delete_allowed(
            "support@linnex.io",
            protected_local_parts=frozenset({"support", "hr"}),
            allow_delete=True,
            delete_prefix_required="plt-",
        )
    assert exc_info.value.reason == "protected role local_part"


def test_delete_denied_without_prefix() -> None:
    with pytest.raises(MailDeleteDeniedError) as exc_info:
        assert_mailbox_delete_allowed(
            "alice@linnex.io",
            protected_local_parts=frozenset({"support"}),
            allow_delete=True,
            delete_prefix_required="plt-",
        )
    assert "plt-" in exc_info.value.reason


def test_delete_denied_allow_false() -> None:
    with pytest.raises(MailDeleteDeniedError) as exc_info:
        assert_mailbox_delete_allowed(
            "plt-x@linnex.io",
            protected_local_parts=frozenset(),
            allow_delete=False,
            delete_prefix_required="plt-",
        )
    assert exc_info.value.reason == "allow_delete=false"
