"""
Проверка permissions для agents, skills и tools.

Permissions основаны на группах пользователя из JWT (claim grps).
"""

from typing import List, Optional, Union

# Группа с полным доступом
ADMIN_GROUP = "admin"

# Fallback permission если не указан
DEFAULT_PERMISSION = [ADMIN_GROUP]


class PermissionChecker:
    """
    Проверка permissions для agents, skills и tools.
    
    Источник групп - claim grps из JWT токена.
    """

    def normalize(self, permission: Optional[Union[str, List[str]]]) -> List[str]:
        """Нормализует permission к списку строк."""
        if permission is None:
            return DEFAULT_PERMISSION
        if isinstance(permission, str):
            return [permission]
        if isinstance(permission, list):
            return permission if permission else DEFAULT_PERMISSION
        return DEFAULT_PERMISSION

    def check(self, user_groups: List[str], required: List[str]) -> bool:
        """Проверяет есть ли у пользователя доступ."""
        if not user_groups:
            return False
        if ADMIN_GROUP in user_groups:
            return True
        return bool(set(user_groups) & set(required))

    def check_flow_permission(
        self,
        user_groups: List[str],
        flow_permission: Optional[Union[str, List[str]]],
    ) -> bool:
        """Проверяет доступ к flow/agent."""
        required = self.normalize(flow_permission)
        return self.check(user_groups, required)

    def check_skill_permission(
        self,
        user_groups: List[str],
        skill_permission: Optional[Union[str, List[str]]],
        flow_permission: Optional[Union[str, List[str]]] = None,
    ) -> bool:
        """Проверяет доступ к skill. Fallback на permission flow."""
        if skill_permission:
            required = self.normalize(skill_permission)
        else:
            required = self.normalize(flow_permission)
        return self.check(user_groups, required)

    def check_tool_permission(
        self,
        user_groups: List[str],
        tool_permission: Optional[Union[str, List[str]]],
    ) -> bool:
        """Проверяет доступ к tool."""
        required = self.normalize(tool_permission)
        return self.check(user_groups, required)


# Singleton
permission_checker = PermissionChecker()

