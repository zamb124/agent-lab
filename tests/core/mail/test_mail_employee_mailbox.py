"""Company mailbox for flow-сотрудника: provision и unbind при deactivate."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest

from apps.flows.src.models.flow_config import FlowConfig, FlowEmployeeConfig
from apps.flows.src.services.flow_employee_provisioning import sync_flow_employee
from core.identity.flow_employee import flow_employee_user_id
from core.mail.models import MailboxBindingKind
from core.mail.repositories import MailboxBindingRepository
from core.mail.service import MailService
from core.models.identity_models import Company, User
from tests.core.mail.complete_client_helpers import seed_connected_user_binding
from tests.core.mail.fakes import RecordingMailServerPort

MailMemberSeed = Callable[..., Awaitable[tuple[Company, User]]]

_MAIL_SERVICE_CACHE = "_cached_mail_service"


@pytest.mark.asyncio
async def test_sync_flow_employee_binds_and_unbinds_company_mailbox(
    mail_service: MailService,
    recording_mail_port: RecordingMailServerPort,
    mailbox_binding_repository: MailboxBindingRepository,
    mail_member_context: MailMemberSeed,
    container,
    unique_id: str,
) -> None:
    company_id, curator_user_id, _user_binding = await seed_connected_user_binding(
        mail_service,
        mail_member_context,
        recording_mail_port,
        unique_id=unique_id,
        prefix="empbox",
    )
    flow_id = f"empbox_{unique_id}"
    employee_user_id = flow_employee_user_id(flow_id)
    enabled = FlowConfig(
        flow_id=flow_id,
        name="Mail Employee",
        entry="main",
        nodes={"main": {"node_type": "llm_node"}},
        employee=FlowEmployeeConfig(
            enabled=True,
            roles=["member"],
            curator_user_ids=[curator_user_id],
        ),
    )
    had_cached = _MAIL_SERVICE_CACHE in container.__dict__
    previous_mail = container.__dict__.get(_MAIL_SERVICE_CACHE)
    container._cached_mail_service = mail_service
    try:
        await sync_flow_employee(container, enabled)
        binding = await mailbox_binding_repository.get_by_user(company_id, employee_user_id)
        assert binding is not None
        assert binding.kind == MailboxBindingKind.USER
        assert binding.user_id == employee_user_id

        disabled = enabled.model_copy(update={"employee": FlowEmployeeConfig()})
        await sync_flow_employee(container, disabled)
        unbound = await mailbox_binding_repository.get_by_user(company_id, employee_user_id)
        assert unbound is None
    finally:
        leftover = await mailbox_binding_repository.get_by_user(company_id, employee_user_id)
        if leftover is not None:
            await mail_service.unbind_mailbox(
                leftover.mailbox_binding_id,
                company_id=company_id,
                acting_as_admin=True,
            )
        if had_cached:
            container._cached_mail_service = previous_mail
        elif _MAIL_SERVICE_CACHE in container.__dict__:
            del container._cached_mail_service
        await container.user_repository.delete(employee_user_id)
