"""
Проверка permissions для agents, branches и tools.

Permissions основаны на группах пользователя из JWT (claim grps).
"""


# Группа с полным доступом
ADMIN_GROUP = "admin"

# Secure default permission если permission не указан.
DEFAULT_PERMISSION: tuple[str, ...] = (ADMIN_GROUP,)


class PermissionChecker:
    """
    Проверка permissions для agents, branches и tools.

    Источник групп - claim grps из JWT токена.
    """

    def normalize(self, permission: str | list[str] | None) -> list[str]:
        """Нормализует permission к списку строк."""
        if permission is None:
            return list(DEFAULT_PERMISSION)
        if isinstance(permission, str):
            return [permission]
        return permission if permission else list(DEFAULT_PERMISSION)

    def check(self, user_groups: list[str], required: list[str]) -> bool:
        """Проверяет есть ли у пользователя доступ."""
        if not user_groups:
            return False
        if ADMIN_GROUP in user_groups:
            return True
        return bool(set(user_groups) & set(required))

    def check_flow_permission(
        self,
        user_groups: list[str],
        flow_permission: str | list[str] | None,
    ) -> bool:
        """Проверяет доступ к flow/agent."""
        required = self.normalize(flow_permission)
        return self.check(user_groups, required)

    def check_branch_permission(
        self,
        user_groups: list[str],
        branch_permission: str | list[str] | None,
        flow_permission: str | list[str] | None = None,
    ) -> bool:
        """Проверяет доступ к ветке графа. При отсутствии branch policy наследует flow policy."""
        if branch_permission:
            required = self.normalize(branch_permission)
        else:
            required = self.normalize(flow_permission)
        return self.check(user_groups, required)

    def check_tool_permission(
        self,
        user_groups: list[str],
        tool_permission: str | list[str] | None,
    ) -> bool:
        """Проверяет доступ к tool."""
        required = self.normalize(tool_permission)
        return self.check(user_groups, required)


# Singleton-экземпляр
permission_checker = PermissionChecker()
