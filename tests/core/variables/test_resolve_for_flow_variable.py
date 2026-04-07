"""Контракт VarResolver.resolve_for_flow_variable (flow variables + company map)."""

from core.variables import VarResolver


def test_plain_string_unchanged() -> None:
    assert VarResolver.resolve_for_flow_variable("hello", {}) == "hello"


def test_full_ref_missing_root_is_none() -> None:
    assert VarResolver.resolve_for_flow_variable("@var:missing_root", {}) is None


def test_full_ref_resolves() -> None:
    assert VarResolver.resolve_for_flow_variable("@var:key", {"key": "v"}) == "v"


def test_composite_any_missing_root_entire_string_none() -> None:
    assert VarResolver.resolve_for_flow_variable("Bearer @var:t", {}) is None


def test_composite_resolves() -> None:
    assert VarResolver.resolve_for_flow_variable("Bearer @var:t", {"t": "x"}) == "Bearer x"


def test_invalid_nested_path_returns_none() -> None:
    assert VarResolver.resolve_for_flow_variable("@var:a.b", {"a": {}}) is None
