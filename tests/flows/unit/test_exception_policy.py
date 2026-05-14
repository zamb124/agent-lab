"""Тесты политики exception_as_response."""

import asyncio

import pytest

from apps.flows.src.runtime.exception_policy import (
    node_exception_policy,
    normalize_allow_types,
    should_absorb_exception,
)
from apps.flows.src.runtime.exceptions import BreakpointInterrupt, FlowInterrupt


def test_should_absorb_disabled() -> None:
    assert should_absorb_exception(ValueError("x"), enabled=False, allow_types=[]) is False


def test_should_absorb_flow_interrupt_never() -> None:
    assert (
        should_absorb_exception(
            FlowInterrupt(question="q"),
            enabled=True,
            allow_types=[],
        )
        is False
    )


def test_should_absorb_breakpoint_never() -> None:
    exc = BreakpointInterrupt("n", "code", {}, flow_id="f")
    assert should_absorb_exception(exc, enabled=True, allow_types=[]) is False


def test_should_absorb_cancelled_never() -> None:
    assert (
        should_absorb_exception(asyncio.CancelledError(), enabled=True, allow_types=[])
        is False
    )


def test_should_absorb_system_exit_never() -> None:
    assert should_absorb_exception(SystemExit(1), enabled=True, allow_types=[]) is False


def test_should_absorb_empty_allow_list_means_any() -> None:
    assert should_absorb_exception(ValueError("a"), enabled=True, allow_types=[]) is True


def test_should_absorb_whitelist() -> None:
    assert (
        should_absorb_exception(
            ValueError("a"), enabled=True, allow_types=["ValueError"]
        )
        is True
    )
    assert (
        should_absorb_exception(
            TypeError("a"), enabled=True, allow_types=["ValueError"]
        )
        is False
    )


def test_normalize_allow_types_strips() -> None:
    assert normalize_allow_types(["  ValueError  ", ""]) == ["ValueError"]


def test_node_exception_policy_from_dict() -> None:
    enabled, types = node_exception_policy(
        {"exception_as_response": True, "exception_allow_types": ["RuntimeError"]}
    )
    assert enabled is True
    assert types == ["RuntimeError"]


def test_normalize_allow_types_rejects_non_list() -> None:
    with pytest.raises(TypeError):
        normalize_allow_types("x")
