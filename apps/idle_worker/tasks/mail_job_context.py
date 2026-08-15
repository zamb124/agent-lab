"""Context+JWT для mail idle-задач (sync / mutations)."""

from __future__ import annotations

from apps.idle_worker.container import IdleWorkerContainer
from apps.idle_worker.tasks.mail_recipients import mailbox_recipient_user_ids
from core.context import clear_context, get_context, set_context
from core.context.job_context import build_job_context
from core.mail.models import MailboxBinding, MailboxBindingKind
from core.models.context_models import Context


async def enter_mail_binding_context(
    container: IdleWorkerContainer,
    binding: MailboxBinding,
    *,
    channel: str = "mail_sync",
) -> Context | None:
    """JWT Context: RAG/files/office и MailService._active_user_id требуют Bearer/user."""
    previous = get_context()
    company = await container.company_repository.get(binding.company_id)
    if company is None:
        raise ValueError(f"company not found for mail job: {binding.company_id}")
    if binding.kind == MailboxBindingKind.USER:
        if binding.user_id is None or not binding.user_id.strip():
            raise ValueError(
                "mail job requires user_id for kind=user "
                + f"mailbox_binding_id={binding.mailbox_binding_id}"
            )
        user = await container.user_repository.get(binding.user_id)
        if user is None:
            raise ValueError(f"user not found for mail job: {binding.user_id}")
    else:
        user = None
        binding_member_ids = await mailbox_recipient_user_ids(container, binding)
        for member_user_id in binding_member_ids:
            if member_user_id == binding.user_id:
                continue
            candidate = await container.user_repository.get(member_user_id)
            if candidate is not None:
                user = candidate
                break
        if user is None:
            raise ValueError(
                "no FGA mailbox member for role mail job: "
                + f"mailbox_binding_id={binding.mailbox_binding_id} "
                + f"company_id={binding.company_id}"
            )
    _ = set_context(
        build_job_context(
            company=company,
            user=user,
            host="mail-job.local",
            trace_id=f"{channel}:{binding.mailbox_binding_id}",
            session_id=f"{channel}:{binding.mailbox_binding_id}",
            channel=channel,
        )
    )
    return previous


def leave_mail_binding_context(previous: Context | None) -> None:
    if previous is not None:
        _ = set_context(previous)
    else:
        clear_context()
