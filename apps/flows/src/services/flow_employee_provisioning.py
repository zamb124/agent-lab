"""Provisioning сотрудника-агента при сохранении/удалении FlowConfig.

Запись версии — ``FlowConfig.create_version``. Синхронизация runtime-identity сотрудника
(двустороннее членство в компании) живёт здесь и вызывается из API create/update/delete.
"""

from __future__ import annotations

from apps.flows.src.models.flow_config import FlowConfig
from core.authz.service import AuthzService
from core.context import get_context
from core.identity.flow_employee import (
    deactivate_flow_employee,
    ensure_flow_employee,
    flow_employee_user_id,
)
from core.logging import get_logger
from core.mail.service import MailService
from core.models.identity_models import SYSTEM_COMPANY_ID

logger = get_logger(__name__)


def _require_company_id() -> str:
    ctx = get_context()
    if ctx is None or ctx.active_company is None:
        raise ValueError("flow employee provisioning requires active company context")
    company_id = ctx.active_company.company_id.strip()
    if not company_id:
        raise ValueError("flow employee provisioning: active company_id is empty")
    return company_id


async def sync_flow_employee(
    authz_service: AuthzService,
    mail_service: MailService,
    flow_config: FlowConfig,
) -> None:
    """Синхронизирует runtime-identity сотрудника с конфигом flow.

    ``employee.enabled=True`` создаёт/обновляет ``User`` сотрудника и членство в
    компании; ``False`` — деактивирует (идемпотентно).
    """
    company_id = _require_company_id()
    employee = flow_config.employee
    if employee.enabled:
        display_name = (employee.display_name or "").strip() or flow_config.name
        employee_user = await ensure_flow_employee(
            authz_service,
            flow_id=flow_config.flow_id,
            company_id=company_id,
            name=display_name,
            roles=employee.roles,
            curator_user_ids=employee.curator_user_ids,
            avatar_url=employee.avatar_url,
        )
        await _ensure_employee_company_mailbox(
            mail_service,
            user_id=employee_user.user_id,
            company_id=company_id,
        )
        logger.info(
            "flow_employee.synced",
            flow_id=flow_config.flow_id,
            company_id=company_id,
            roles=list(employee.roles),
        )
        return
    await _deactivate_employee_and_unbind_mailbox(
        authz_service,
        mail_service,
        flow_id=flow_config.flow_id,
        company_id=company_id,
    )


async def remove_flow_employee(
    authz_service: AuthzService,
    mail_service: MailService,
    flow_id: str,
) -> None:
    """Деактивирует сотрудника-агента при удалении flow (идемпотентно)."""
    company_id = _require_company_id()
    await _deactivate_employee_and_unbind_mailbox(
        authz_service,
        mail_service,
        flow_id=flow_id,
        company_id=company_id,
    )
    logger.info("flow_employee.removed", flow_id=flow_id, company_id=company_id)


async def _ensure_employee_company_mailbox(
    mail_service: MailService,
    *,
    user_id: str,
    company_id: str,
) -> None:
    if company_id == SYSTEM_COMPANY_ID:
        return
    connection = await mail_service.get_connection(company_id=company_id)
    if connection is None:
        return
    _ = await mail_service.get_or_create_user_binding(
        user_id,
        company_id=company_id,
    )


async def _deactivate_employee_and_unbind_mailbox(
    authz_service: AuthzService,
    mail_service: MailService,
    *,
    flow_id: str,
    company_id: str,
) -> None:
    employee_user_id = flow_employee_user_id(flow_id)
    await deactivate_flow_employee(
        authz_service,
        flow_id=flow_id,
        company_id=company_id,
    )
    await mail_service.unbind_company_user_mailboxes(
        employee_user_id,
        company_id=company_id,
    )
