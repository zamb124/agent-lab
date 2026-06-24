"""
Unit-тесты контракта Mock Control System.

Проверяют единое правило: значение mock для любой сущности (tool/node/flow/llm)
— список ответов. Скаляр и пустой список запрещены.
"""

import pytest
from pydantic import ValidationError

from core.clients.llm.mock_control import (
    MockControlConfig,
    assert_mock_permission,
    mock_item_to_node_result,
    mock_item_to_text,
    parse_mock_control_metadata,
)


def test_valid_config_with_lists() -> None:
    config = MockControlConfig.model_validate(
        {
            "enabled": True,
            "permission_groups": ["admin"],
            "tools": {"calculator": [{"type": "result", "content": "42"}]},
            "nodes": {
                "n1": [{"type": "text", "content": "one"}],
                "n2": [{"type": "text", "content": "two"}],
            },
            "flows": {"sub": ["готово"]},
            "llm": [{"type": "text", "content": "global"}],
        }
    )
    assert config.enabled is True
    assert config.nodes["n1"][0] == {"type": "text", "content": "one"}
    assert config.tools["calculator"][0] == {"type": "result", "content": "42"}


def test_scalar_tool_value_rejected() -> None:
    """Скаляр вместо списка ответов недопустим."""
    with pytest.raises(ValidationError):
        MockControlConfig.model_validate(
            {"enabled": True, "tools": {"calculator": "42"}}
        )


def test_scalar_node_value_rejected() -> None:
    with pytest.raises(ValidationError):
        MockControlConfig.model_validate(
            {"enabled": True, "nodes": {"n1": {"type": "text", "content": "x"}}}
        )


def test_empty_queue_rejected() -> None:
    """Сконфигурированная сущность с пустым списком — ошибка."""
    with pytest.raises(ValidationError):
        MockControlConfig.model_validate({"enabled": True, "nodes": {"n1": []}})


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError):
        MockControlConfig.model_validate({"enabled": True, "unexpected": 1})


def test_parse_metadata_returns_none_without_mock_key() -> None:
    assert parse_mock_control_metadata({"branch": "default"}) is None


def test_parse_metadata_parses_mock_key() -> None:
    config = parse_mock_control_metadata(
        {"__mock__": {"enabled": True, "permission_groups": ["admin"], "llm": ["hi"]}}
    )
    assert config is not None
    assert config.llm == ["hi"]


def test_permission_requires_membership() -> None:
    assert_mock_permission(["admin", "user"], ["admin", "developers"])
    with pytest.raises(Exception):
        assert_mock_permission(["user"], ["admin"])


def test_permission_requires_explicit_groups() -> None:
    """Пустой permission_groups запрещает mock (привилегированная фича)."""
    with pytest.raises(Exception):
        assert_mock_permission(["admin"], [])


def test_mock_item_to_text_variants() -> None:
    assert mock_item_to_text("plain") == "plain"
    assert mock_item_to_text({"type": "result", "content": "42"}) == "42"
    assert mock_item_to_text({"type": "text", "content": "hi"}) == "hi"


def test_mock_item_to_node_result_state_patch() -> None:
    result = mock_item_to_node_result({"type": "state", "patch": {"route": "order"}})
    assert result == {"route": "order"}


def test_mock_item_to_node_result_state_patch_requires_object() -> None:
    with pytest.raises(ValueError):
        mock_item_to_node_result({"type": "state", "patch": "not-an-object"})
