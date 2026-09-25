"""Резолв identity исполнения flow: сотрудник-агент действует от собственного имени.

Единая точка подмены identity перед сериализацией ``context_data`` в worker.
Для flow-сотрудника (``employee.enabled``) собирается ``Context`` сотрудника с его
SESSION JWT — дальше вся платформа (ServiceClient, tools, capability gateway, billing)
видит обычного пользователя без единого адаптера. Для обычного flow — контекст
инициатора без изменений.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.flows.src.models.flow_config import FlowConfig
from core.context.job_context import build_job_context
from core.identity.flow_employee import flow_employee_user_id, is_flow_employee
from core.logging import get_logger
from core.models.context_models import Context
from core.models.flow_ui_share import FlowUIShareGrant
from core.models.identity_models import User
from core.types import JsonObject

logger = get_logger(__name__)


@dataclass(frozen=True)
class ResolvedExecutionIdentity:
    """Контекст исполнения + инициатор (собеседник/человек, запустивший run)."""

    context: Context
    initiator_user_id: str
    is_employee: bool


def _employee_permission_groups(company_id: str, groups: list[str], roles: list[str]) -> list[str]:
    merged: list[str] = []
    for group in [*groups, *roles]:
        if group and group not in merged:
            merged.append(group)
    _ = company_id
    return merged


async def _share_owner_context(
    *,
    share_grant: FlowUIShareGrant,
    visitor_context: Context,
) -> Context:
    """Ход editor-посетителя share исполняется от имени владельца сессии, выдавшего grant.

    Владелец остаётся и инициатором: A2A Task принадлежит ему, посетитель не является
    пользователем платформы и виден только в metadata контекста.
    """
    company = visitor_context.active_company
    if company is None or company.company_id != share_grant.company_id:
        raise ValueError("share visitor context must carry the grant company")
    owner = await User.get(share_grant.created_by_user_id)
    if owner is None:
        raise ValueError(
            f"share grant {share_grant.grant_id} owner {share_grant.created_by_user_id} not found"
        )
    owner_context = build_job_context(
        company=company,
        user=owner,
        host=visitor_context.host,
        trace_id=visitor_context.trace_id or "",
        session_id=visitor_context.session_id or "",
        channel=visitor_context.channel,
    )
    owner_context.active_namespace = visitor_context.active_namespace
    owner_context.language = visitor_context.language
    owner_context.metadata = {
        "context_type": "flow_ui_share_owner",
        "authenticated": True,
        "grps": list(owner.groups),
        "flow_ui_share_grant_id": share_grant.grant_id,
        "flow_ui_share_visitor_user_id": visitor_context.user.user_id,
    }
    return owner_context


async def resolve_execution_context(
    *,
    flow_config: FlowConfig,
    initiator_context: Context,
    share_grant: FlowUIShareGrant | None = None,
) -> ResolvedExecutionIdentity:
    """Возвращает контекст, от чьего имени исполняется flow, и инициатора запуска."""
    actor_context = initiator_context
    if share_grant is not None:
        actor_context = await _share_owner_context(
            share_grant=share_grant, visitor_context=initiator_context
        )
    initiator_user_id = actor_context.user.user_id
    if not flow_config.employee.enabled:
        return ResolvedExecutionIdentity(
            context=actor_context,
            initiator_user_id=initiator_user_id,
            is_employee=False,
        )

    company = actor_context.active_company
    if company is None:
        raise ValueError(
            f"resolve_execution_context: flow {flow_config.flow_id} employee requires active company"
        )

    employee_user_id = flow_employee_user_id(flow_config.flow_id)
    user = await User.get(employee_user_id)
    if user is None:
        raise ValueError(
            f"resolve_execution_context: flow employee user {employee_user_id} not provisioned"
        )
    if not is_flow_employee(user):
        raise ValueError(
            f"resolve_execution_context: user {employee_user_id} is not a flow employee"
        )

    roles = user.companies.get(company.company_id)
    if not roles:
        raise ValueError(
            f"resolve_execution_context: flow employee {employee_user_id} is not a member of {company.company_id}"
        )

    employee_context = build_job_context(
        company=company,
        user=user,
        host=actor_context.host,
        trace_id=actor_context.trace_id or "",
        session_id=actor_context.session_id or "",
        channel=actor_context.channel,
    )
    employee_context.active_namespace = actor_context.active_namespace
    employee_context.language = actor_context.language
    metadata: JsonObject = {
        "context_type": "flow_employee",
        "authenticated": True,
        "grps": _employee_permission_groups(company.company_id, user.groups, roles),
        "initiator_user_id": initiator_user_id,
    }
    employee_context.metadata = metadata

    logger.info(
        "flow_employee.execution_identity",
        flow_id=flow_config.flow_id,
        employee_user_id=employee_user_id,
        initiator_user_id=initiator_user_id,
    )
    return ResolvedExecutionIdentity(
        context=employee_context,
        initiator_user_id=initiator_user_id,
        is_employee=True,
    )
