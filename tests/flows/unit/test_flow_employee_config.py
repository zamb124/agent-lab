"""Валидация `FlowEmployeeConfig` и roundtrip `FlowConfig.employee` (чистый Pydantic)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.flows.src.models.flow_config import FlowConfig, FlowEmployeeConfig


def test_disabled_default_valid_without_roles_or_curators():
    cfg = FlowEmployeeConfig()
    assert cfg.enabled is False
    assert cfg.roles == []
    assert cfg.curator_user_ids == []


def test_enabled_requires_roles():
    with pytest.raises(ValidationError):
        FlowEmployeeConfig(enabled=True, roles=[], curator_user_ids=["c1"])


def test_enabled_requires_curators():
    with pytest.raises(ValidationError):
        FlowEmployeeConfig(enabled=True, roles=["member"], curator_user_ids=[])


def test_enabled_rejects_whitespace_only_roles_and_curators():
    with pytest.raises(ValidationError):
        FlowEmployeeConfig(enabled=True, roles=["   "], curator_user_ids=["c1"])
    with pytest.raises(ValidationError):
        FlowEmployeeConfig(enabled=True, roles=["member"], curator_user_ids=["  "])


def test_enabled_valid_full():
    cfg = FlowEmployeeConfig(
        enabled=True,
        roles=["member", "flow_operator"],
        curator_user_ids=["c1"],
        display_name="AI Worker",
        avatar_url="https://example.com/a.png",
    )
    assert cfg.enabled is True
    assert cfg.display_name == "AI Worker"
    assert cfg.avatar_url == "https://example.com/a.png"


def test_enabled_optional_display_avatar():
    cfg = FlowEmployeeConfig(enabled=True, roles=["member"], curator_user_ids=["c1"])
    assert cfg.display_name is None
    assert cfg.avatar_url is None


def test_flow_config_roundtrip_preserves_employee():
    cfg = FlowConfig(
        flow_id="rt_flow",
        name="RT",
        entry="main",
        nodes={"main": {"node_type": "llm_node"}},
        employee=FlowEmployeeConfig(
            enabled=True, roles=["member"], curator_user_ids=["c1"]
        ),
    )
    dumped = cfg.model_dump()
    restored = FlowConfig.model_validate(dumped)
    assert restored.employee.enabled is True
    assert restored.employee.roles == ["member"]
    assert restored.employee.curator_user_ids == ["c1"]


def test_flow_config_default_employee_disabled():
    cfg = FlowConfig(
        flow_id="no_emp",
        name="NoEmp",
        entry="main",
        nodes={"main": {"node_type": "llm_node"}},
    )
    assert cfg.employee.enabled is False
