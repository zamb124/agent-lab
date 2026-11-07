"""Сборка CapabilityExecutionContext для code-runner и builtin tools через gateway."""

from __future__ import annotations

from apps.flows.config import get_settings as get_flows_settings
from apps.flows.src.runtime.tool_call_context import get_active_tool_call_context
from apps.flows.src.state import ExecutionState
from core.capabilities import CapabilityExecutionContext
from core.capabilities.tokens import (
    CapabilityExecutionTokenClaims,
    execution_token_exp,
    issue_execution_token,
)
from core.context import get_context
from core.logging import get_log_context


def capability_execution_context(
    state: ExecutionState,
    *,
    allowed_capabilities: list[str] | None = None,
) -> CapabilityExecutionContext:
    """Контекст и signed execution_token для POST /capabilities/call.

    ``allowed_capabilities`` — grant списка capability; пустой/None — без ограничения
    (как у RemoteCodeRunner для sandbox).
    """
    context = get_context()
    if context is None or context.active_company is None:
        raise ValueError("Capability call requires Context with active_company")
    company_id = context.active_company.company_id
    user_id = context.user.user_id
    settings = get_flows_settings()
    log_context = get_log_context()
    request_id = log_context.get("request_id")
    request_id_value = request_id if isinstance(request_id, str) and request_id.strip() else None
    tool_context = get_active_tool_call_context()
    source_node_id = tool_context.node_id if tool_context is not None else None
    source_tool_call_id = tool_context.tool_call_id if tool_context is not None else None
    namespace_raw = (context.active_namespace or "").strip()
    namespace = namespace_raw if namespace_raw and namespace_raw != "default" else None
    grant = list(allowed_capabilities) if allowed_capabilities is not None else []
    claims = CapabilityExecutionTokenClaims(
        company_id=company_id,
        user_id=user_id,
        flow_id=state.session_flow_id,
        branch_id=state.branch_id,
        session_id=state.session_id,
        task_id=state.task_id,
        context_id=state.context_id,
        channel=context.channel,
        request_id=request_id_value,
        durable_execution_branch_id=state.durable_execution_branch_id,
        durable_node_schedule_sequence=state.durable_node_schedule_sequence,
        durable_superstep_sequence=state.durable_superstep_sequence,
        source_node_id=source_node_id,
        source_tool_call_id=source_tool_call_id,
        namespace=namespace,
        allowed_capabilities=grant,
        exp=execution_token_exp(settings.capability_execution_token_ttl_seconds),
    )
    token = issue_execution_token(claims)
    return CapabilityExecutionContext(
        execution_token=token,
        company_id=company_id,
        user_id=user_id,
        flow_id=state.session_flow_id,
        branch_id=state.branch_id,
        session_id=state.session_id,
        task_id=state.task_id,
        context_id=state.context_id,
        channel=context.channel,
        request_id=request_id_value,
        trace_id=context.trace_id,
        durable_execution_branch_id=state.durable_execution_branch_id,
        durable_node_schedule_sequence=state.durable_node_schedule_sequence,
        durable_superstep_sequence=state.durable_superstep_sequence,
        source_node_id=source_node_id,
        source_tool_call_id=source_tool_call_id,
        namespace=namespace,
    )
