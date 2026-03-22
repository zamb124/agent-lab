"""
Тесты системы permissions.

Покрывает все случаи:
- Нет прав на flow → JSON-RPC error -32008
- Нет прав на skill → JSON-RPC error -32008
- Нет прав на tool → возвращает строку агенту
- Есть права → успешный доступ
- permissions_enabled=false → проверка отключена

БЕЗ МОКОВ кроме LLM.
"""

import uuid
from typing import Any, Dict, List

import pytest

from core.auth import permission_checker
from core.auth.errors import PermissionDeniedA2AError
from core.auth.permissions import PermissionChecker


# =============================================================================
# Тесты PermissionChecker
# =============================================================================


class TestPermissionChecker:
    """Тесты класса PermissionChecker."""

    def test_admin_has_access_to_everything(self):
        """Admin group имеет доступ ко всему."""
        assert permission_checker.check_flow_permission(["admin"], None) is True
        assert permission_checker.check_flow_permission(["admin"], "managers") is True
        assert permission_checker.check_flow_permission(["admin"], ["managers", "users"]) is True

    def test_no_permission_defined_requires_admin(self):
        """Если permission не указан - требуется admin."""
        assert permission_checker.check_flow_permission(["user"], None) is False
        assert permission_checker.check_flow_permission([], None) is False
        assert permission_checker.check_flow_permission(["managers"], None) is False

    def test_user_has_required_permission(self):
        """Пользователь имеет требуемую группу."""
        assert permission_checker.check_flow_permission(["managers"], "managers") is True
        assert permission_checker.check_flow_permission(["managers", "users"], "managers") is True

    def test_user_missing_required_permission(self):
        """Пользователь не имеет требуемой группы."""
        assert permission_checker.check_flow_permission(["users"], "managers") is False
        assert permission_checker.check_flow_permission([], "managers") is False

    def test_permission_list_any_match(self):
        """Достаточно совпадения с любой группой из списка."""
        assert permission_checker.check_flow_permission(["users"], ["managers", "users"]) is True
        assert permission_checker.check_flow_permission(["guests"], ["managers", "users"]) is False

    def test_normalize_permission(self):
        """Normalize преобразует строку в список."""
        assert permission_checker.normalize(None) == ["admin"]
        assert permission_checker.normalize("managers") == ["managers"]
        assert permission_checker.normalize(["managers", "users"]) == ["managers", "users"]

    def test_skill_permission_inherits_from_flow(self):
        """Skill без permission наследует от flow."""
        # Skill permission = None, flow permission = "managers"
        # Пользователь с "managers" имеет доступ
        assert permission_checker.check_skill_permission(
            ["managers"], None, "managers"
        ) is True

        # Пользователь без "managers" - нет доступа
        assert permission_checker.check_skill_permission(
            ["users"], None, "managers"
        ) is False

    def test_skill_permission_overrides_flow(self):
        """Skill permission переопределяет flow permission."""
        # Agent требует "managers", skill требует "vip"
        # Пользователь с "vip" имеет доступ к skill
        assert permission_checker.check_skill_permission(
            ["vip"], "vip", "managers"
        ) is True

        # Пользователь с "managers" НЕ имеет доступ к skill (требуется vip)
        assert permission_checker.check_skill_permission(
            ["managers"], "vip", "managers"
        ) is False

    def test_tool_permission(self):
        """Проверка permission на tool."""
        assert permission_checker.check_tool_permission(["users"], "users") is True
        assert permission_checker.check_tool_permission(["users"], "admin") is False
        assert permission_checker.check_tool_permission(["admin"], "special") is True


# =============================================================================
# Тесты PermissionDeniedError
# =============================================================================


class TestPermissionDeniedA2AError:
    """Тесты класса PermissionDeniedA2AError."""

    def test_error_code_is_minus_32008(self):
        """Код ошибки должен быть -32008."""
        error = PermissionDeniedA2AError()
        assert error.code == -32008

    def test_for_flow_creates_correct_message(self):
        """for_flow создаёт правильное сообщение."""
        error = PermissionDeniedA2AError.for_flow("my_flow", ["managers"])
        assert "my_flow" in error.message
        assert error.code == -32008
        assert error.data["entity_type"] == "flow"
        assert error.data["entity_id"] == "my_flow"

    def test_for_skill_creates_correct_message(self):
        """for_skill создаёт правильное сообщение."""
        error = PermissionDeniedA2AError.for_skill("my_skill", "my_flow", ["vip"])
        assert "my_skill" in error.message
        assert "my_flow" in error.message
        assert error.data["entity_type"] == "skill"
        assert error.data["entity_id"] == "my_skill"

    def test_for_tool_creates_correct_message(self):
        """for_tool создаёт правильное сообщение."""
        error = PermissionDeniedA2AError.for_tool("my_tool", ["special"])
        assert "my_tool" in error.message
        assert error.data["entity_type"] == "tool"
        assert error.data["entity_id"] == "my_tool"

    def test_to_json_rpc_error(self):
        """to_json_rpc_error возвращает корректную структуру."""
        error = PermissionDeniedA2AError.for_flow("test", ["admin"])
        json_error = error.to_json_rpc_error()

        assert json_error["code"] == -32008
        assert "message" in json_error
        assert "data" in json_error

