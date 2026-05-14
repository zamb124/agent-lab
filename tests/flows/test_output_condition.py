"""Условия output_actions: канон `evaluate_output_action_condition`."""


from apps.flows.src.triggers.output_condition import (
    evaluate_output_action_condition,
    parse_output_condition_literal,
)


def test_parse_bool_null():
    assert parse_output_condition_literal("true") is True
    assert parse_output_condition_literal("false") is False
    assert parse_output_condition_literal("null") is None
    assert parse_output_condition_literal('"x"') == "x"


def test_equality_state():
    state = {"variables": {"k": 1}, "a": 2}
    assert evaluate_output_action_condition("@state:variables.k == 1", state) is True
    assert evaluate_output_action_condition("@state:variables.k == 2", state) is False
    assert evaluate_output_action_condition('@state:variables.k != "1"', state) is True


def test_truthy_path():
    state = {"x": 0, "y": 1}
    assert evaluate_output_action_condition("@state:y", state) is True
    assert evaluate_output_action_condition("@state:x", state) is False


def test_empty_means_true():
    assert evaluate_output_action_condition("", {"a": 1}) is True
