"""Shared helper: recipient user ids for a mailbox binding via OpenFGA."""

from __future__ import annotations

from core.authz.models import AuthzObject
from core.authz.types import AuthzObjectType, AuthzRelation, AuthzSubjectKind
from core.container.base import BaseContainer
from core.mail.models import MailboxBinding
from core.models.identity_models import Company, User


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


def _user_in_company(user: User, company: Company) -> bool:
    return company.company_id in user.companies or user.user_id in company.members


async def _first_existing_company_member(
    container: BaseContainer,
    company: Company,
    user_ids: list[str],
) -> User | None:
    for user_id in user_ids:
        user = await container.user_repository.get(user_id)
        if user is None:
            continue
        if _user_in_company(user, company):
            return user
    return None


async def mailbox_role_job_actor_user(
    container: BaseContainer, binding: MailboxBinding
) -> User:
    company = await container.company_repository.get(binding.company_id)
    if company is None:
        raise ValueError(f"company not found for mail job: {binding.company_id}")
    recipient_ids = await mailbox_recipient_user_ids(container, binding)
    actor = await _first_existing_company_member(container, company, recipient_ids)
    if actor is not None:
        return actor
    obj = AuthzObject.mailbox_binding(binding.mailbox_binding_id)
    subjects = await container.authz_service.list_users(
        obj,
        AuthzRelation.CAN_ADMIN,
        user_filters=[AuthzObjectType.USER],
    )
    admin_ids = sorted(
        subject.value
        for subject in subjects
        if subject.kind is AuthzSubjectKind.USER
    )
    actor = await _first_existing_company_member(container, company, admin_ids)
    if actor is None:
        raise ValueError(
            "no FGA mailbox member for role mail job: "
            + f"mailbox_binding_id={binding.mailbox_binding_id} "
            + f"company_id={binding.company_id}"
        )
    return actor
