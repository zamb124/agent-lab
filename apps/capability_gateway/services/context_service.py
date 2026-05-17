"""Восстановление доверенного Context для вызова capability."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from apps.capability_gateway.services.contracts import CapabilityGatewayContainerProtocol
from core.capabilities import CapabilityExecutionContext
from core.context import Context, clear_context, get_context, set_context


class CapabilityContextService:
    """Строит platform Context из capability execution context."""

    def __init__(self, container: CapabilityGatewayContainerProtocol):
        self._container: CapabilityGatewayContainerProtocol = container

    async def build_context(
        self,
        execution_context: CapabilityExecutionContext,
    ) -> Context:
        if execution_context.user_id is None:
            raise ValueError("Capability context requires user_id")

        user = await self._container.user_repository.get(execution_context.user_id)
        if user is None:
            raise ValueError(f"User not found: {execution_context.user_id}")

        company = await self._container.company_repository.get(execution_context.company_id)
        if company is None:
            raise ValueError(f"Company not found: {execution_context.company_id}")

        return Context(
            user=user,
            active_company=company,
            user_companies=[company],
            session_id=execution_context.session_id,
            channel="capability_gateway",
            flow_id=execution_context.flow_id,
            trace_id=execution_context.trace_id,
        )

    @contextmanager
    def activate(self, context: Context) -> Generator[None, None, None]:
        previous_context = get_context()
        set_context(context)
        try:
            yield
        finally:
            if previous_context is None:
                clear_context()
            else:
                set_context(previous_context)
