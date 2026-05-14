"""
Wall-clock дедлайн для одного run flow (связка с ExecutionState.flow_deadline_monotonic).
"""

from __future__ import annotations

import time

from apps.flows.src.constants.execution_limits import get_flow_execution_wall_time_cap_seconds
from core.state import ExecutionState


def apply_flow_wall_clock_deadline(state: ExecutionState, timeout_seconds: int) -> None:
    """
    Устанавливает state.flow_deadline_monotonic = now + min(timeout, cap).
    """
    if timeout_seconds < 1:
        raise ValueError("timeout_seconds must be >= 1")
    cap = get_flow_execution_wall_time_cap_seconds()
    eff = min(int(timeout_seconds), cap)
    state.flow_timeout_effective_seconds = eff
    state.flow_deadline_monotonic = time.monotonic() + float(eff)
