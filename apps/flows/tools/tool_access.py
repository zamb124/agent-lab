"""Доступ к общим демо- и пользовательским тулам: company member (OpenFGA)."""

# Пустой список → BaseTool/_check_permission требует company#can_view (см. authz_gate).
STANDARD_USER_TOOL_GROUPS: tuple[str, ...] = ()
