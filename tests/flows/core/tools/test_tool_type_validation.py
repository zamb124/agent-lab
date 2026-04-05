"""
Тесты ReactToolRole и уникальности reason/exit в llm_node.
"""

import pytest

from apps.flows.src.models.enums import ReactToolRole
from apps.flows.src.services.flow_validator import FlowValidator, FlowValidationResult
from apps.flows.src.services.flows_loader import FlowsLoader
from apps.flows.tools import calculator, final_answer, finish, reason


class TestReactToolRoleEnum:
    def test_react_role_values(self):
        assert ReactToolRole.STANDARD == "standard"
        assert ReactToolRole.REASON == "reason"
        assert ReactToolRole.EXIT == "exit"

    def test_builtin_tools_roles(self):
        assert reason.react_role == ReactToolRole.REASON
        assert finish.react_role == ReactToolRole.EXIT
        assert final_answer.react_role == ReactToolRole.EXIT
        assert calculator.react_role == ReactToolRole.STANDARD


class TestFlowValidatorReactRole:
    @pytest.fixture
    def validator(self):
        return FlowValidator()

    def test_single_reason_and_exit_ok(self, validator):
        result = FlowValidationResult(valid=True)
        tools = [
            {"tool_id": "reason", "react_role": "reason", "code": "..."},
            {"tool_id": "calc", "react_role": "standard", "code": "..."},
        ]
        validator._validate_react_role_uniqueness("test_node", tools, result)
        assert result.valid

    def test_single_exit_ok(self, validator):
        result = FlowValidationResult(valid=True)
        tools = [
            {"tool_id": "finish", "react_role": "exit", "code": "..."},
            {"tool_id": "calc", "react_role": "standard", "code": "..."},
        ]
        validator._validate_react_role_uniqueness("test_node", tools, result)
        assert result.valid

    def test_duplicate_reason_fails(self, validator):
        result = FlowValidationResult(valid=True)
        tools = [
            {"tool_id": "reason", "react_role": "reason", "code": "..."},
            {"tool_id": "custom_reason", "react_role": "reason", "code": "..."},
        ]
        validator._validate_react_role_uniqueness("test_node", tools, result)
        assert not result.valid
        assert any(e.code == "duplicate_reason_tool" for e in result.errors)

    def test_duplicate_exit_fails(self, validator):
        result = FlowValidationResult(valid=True)
        tools = [
            {"tool_id": "finish", "react_role": "exit", "code": "..."},
            {"tool_id": "final_answer", "react_role": "exit", "code": "..."},
        ]
        validator._validate_react_role_uniqueness("test_node", tools, result)
        assert not result.valid
        assert any(e.code == "duplicate_exit_tool" for e in result.errors)

    def test_reason_and_exit_together_ok(self, validator):
        result = FlowValidationResult(valid=True)
        tools = [
            {"tool_id": "reason", "react_role": "reason", "code": "..."},
            {"tool_id": "finish", "react_role": "exit", "code": "..."},
        ]
        validator._validate_react_role_uniqueness("test_node", tools, result)
        assert result.valid

    def test_multiple_standard_ok(self, validator):
        result = FlowValidationResult(valid=True)
        tools = [
            {"tool_id": "calc", "react_role": "standard", "code": "..."},
            {"tool_id": "search", "react_role": "standard", "code": "..."},
        ]
        validator._validate_react_role_uniqueness("test_node", tools, result)
        assert result.valid

    def test_missing_react_role_ok(self, validator):
        result = FlowValidationResult(valid=True)
        tools = [
            {"tool_id": "calc", "code": "..."},
        ]
        validator._validate_react_role_uniqueness("test_node", tools, result)
        assert result.valid


class TestFlowsLoaderReactRoleValidation:
    def test_loader_duplicate_reason_raises(self, tmp_path):
        loader = FlowsLoader(
            bundles_dir=tmp_path,
            flow_repository=None,
            node_repository=None,
            tool_repository=None,
        )
        tools = [
            {"tool_id": "reason", "react_role": "reason"},
            {"tool_id": "calc", "react_role": "standard"},
            {"tool_id": "my_reason", "react_role": "reason"},
        ]
        with pytest.raises(ValueError, match="только 1 reasoning"):
            loader._validate_llm_node_tools("n", tools)

    def test_loader_duplicate_exit_raises(self, tmp_path):
        loader = FlowsLoader(
            bundles_dir=tmp_path,
            flow_repository=None,
            node_repository=None,
            tool_repository=None,
        )
        tools = [
            {"tool_id": "finish", "react_role": "exit"},
            {"tool_id": "final_answer", "react_role": "exit"},
        ]
        with pytest.raises(ValueError, match="только 1 exit"):
            loader._validate_llm_node_tools("n", tools)
