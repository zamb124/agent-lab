"""Сборка и применение доменных delta для ExecutionState."""

from __future__ import annotations

from apps.flows.src.durable_execution.models import (
    apply_state_delta,
    build_state_delta,
)

__all__ = ["apply_state_delta", "build_state_delta"]
