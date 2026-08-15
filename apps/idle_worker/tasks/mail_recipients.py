"""Shared helper: recipient user ids for a mailbox binding via OpenFGA."""

from __future__ import annotations

from core.authz.models import AuthzObject
from core.authz.types import AuthzRelation, AuthzSubjectKind
from core.container.base import BaseContainer
from core.mail.models import MailboxBinding


async def mailbox_recipient_user_ids(
    container: BaseContainer, binding: MailboxBinding
) -> list[str]:
    user_ids: list[str] = []
    if binding.user_id is not None and binding.user_id.strip():
        user_ids.append(binding.user_id)
    obj = AuthzObject.mailbox_binding(binding.mailbox_binding_id)
    for relation in (
        AuthzRelation.OWNER,
        AuthzRelation.MEMBER,
        AuthzRelation.MANAGER,
    ):
        tuples = await container.authz_service.list_tuples(obj, relation=relation)
        for item in tuples:
            if item.subject.kind is not AuthzSubjectKind.USER:
                continue
            if item.subject.value not in user_ids:
                user_ids.append(item.subject.value)
    return user_ids
