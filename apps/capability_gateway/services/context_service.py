"""Восстановление доверенного Context для вызова capability."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from apps.capability_gateway.services.contracts import CapabilityGatewayContainerProtocol
from core.capabilities import CapabilityExecutionContext
from core.context import Context, clear_context, get_context, set_context
from core.context.job_context import build_job_context


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

        company_subdomain = company.subdomain
        if company_subdomain is None or company_subdomain.strip() == "":
            host = company.company_id
        else:
            host = company_subdomain.strip()

        trace_id = execution_context.trace_id
        if trace_id is None:
            request_id = execution_context.request_id
            if isinstance(request_id, str) and request_id.strip():
                trace_id = request_id.strip()
            else:
                trace_id = f"capability:{execution_context.session_id}"

        job_context = build_job_context(
            company=company,
            user=user,
            host=host,
            trace_id=trace_id,
            session_id=execution_context.session_id,
            channel=execution_context.channel,
        )
        updates: dict[str, object] = {"flow_id": execution_context.flow_id}
        if execution_context.namespace is not None:
            updates["active_namespace"] = execution_context.namespace
        return job_context.model_copy(update=updates)

    @contextmanager
    def activate(self, context: Context) -> Generator[None, None, None]:
        previous_context = get_context()
        _ = set_context(context)
        try:
            yield
        finally:
            if previous_context is None:
                clear_context()
            else:
                _ = set_context(previous_context)
