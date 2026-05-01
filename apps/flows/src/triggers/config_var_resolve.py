"""
Резолв @var: в конфигах триггеров. Словарь — ``FlowFactory.get_resolved_variables_map``
(как ``state.variables`` при старте flow), без дублирования логики merge.
"""

from __future__ import annotations

from typing import Any, Optional

from core.variables.resolver import VarResolver, VariableResolutionError


async def resolve_at_var_for_flow(
    container: Any,
    flow_id: str,
    raw: str,
    *,
    branch_id: str = "default",
    config_version: Optional[str] = None,
) -> str:
    if not raw:
        return ""
    s = str(raw).strip()
    if not s.startswith("@var:"):
        return s
    try:
        var_map = await container.flow_factory.get_resolved_variables_map(
            flow_id,
            branch_id,
            config_version=config_version,
        )
    except ValueError as e:
        raise VariableResolutionError(str(e)) from e
    out = VarResolver.resolve_ref(s, var_map)
    return str(out) if out is not None else ""
