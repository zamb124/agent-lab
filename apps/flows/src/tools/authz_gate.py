"""Tool authz gate: привязка на старте процесса flows, чтение при исполнении тула."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator, Sequence

from core.authz.errors import AuthzDenied
from core.authz.ids import PLATFORM_ADMIN_GROUP
from core.authz.models import AuthzObject, AuthzSubject
from core.authz.service import AuthzService
from core.authz.types import AuthzRelation
from core.context import require_active_company

ToolAuthzGate = Callable[
    [Sequence[str] | None, str, str],
    Awaitable[str | None],
]

_gate: ToolAuthzGate | None = None


def bound_tool_authz_gate(authz_service: AuthzService) -> Iterator[None]:
    """Lifecycle процесса flows: gate проверяет права тула через OpenFGA на время жизни DI."""
    global _gate
    _gate = _authz_gate(authz_service)
    yield
    _gate = None


def _authz_gate(authz: AuthzService) -> ToolAuthzGate:
    async def check(
        permission: Sequence[str] | None,
        user_id: str,
        tool_name: str,
    ) -> str | None:
        required = [item for item in list(permission or []) if item.strip()]
        try:
            company = require_active_company()
            if not required:
                await authz.require_can_view(
                    AuthzObject.company(company.company_id),
                    user_id=user_id,
                )
                return None
            subject = AuthzSubject.user(user_id)
            for group_name in required:
                group_obj = (
                    AuthzObject.group(PLATFORM_ADMIN_GROUP)
                    if group_name == PLATFORM_ADMIN_GROUP
                    else AuthzObject.group(group_name, company_id=company.company_id)
                )
                if await authz.check(subject, AuthzRelation.MEMBER, group_obj):
                    return None
            raise AuthzDenied(f"denied user:{user_id} group member for tool:{tool_name}")
        except AuthzDenied:
            if required:
                return (
                    f"У пользователя нет прав на использование инструмента '{tool_name}'. "
                    f"Требуется одна из групп: {', '.join(required)}"
                )
            return f"У пользователя нет прав на использование инструмента '{tool_name}'."

    return check


async def check_tool_permission(
    permission: Sequence[str] | None,
    user_id: str,
    tool_name: str,
) -> str | None:
    """None = allow; иначе сообщение об ошибке для агента."""
    if _gate is None:
        raise RuntimeError("tool authz gate is not bound")
    return await _gate(permission, user_id, tool_name)
