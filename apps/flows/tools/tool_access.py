"""Группы JWT (`grps`), которым разрешены общие демо- и пользовательские тулы."""

STANDARD_USER_TOOL_GROUPS: tuple[str, ...] = (
    "guest",
    "viewer",
    "developer",
    "admin",
    "owner",
)
