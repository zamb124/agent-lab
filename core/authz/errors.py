"""Ошибки authorization слоя."""


class AuthzError(Exception):
    """Базовая ошибка AuthzService."""


class AuthzDenied(AuthzError):
    """Subject не имеет требуемой relation к object."""


class AuthzUnavailable(AuthzError):
    """OpenFGA недоступен или не сконфигурирован."""


class AuthzConfigError(AuthzError):
    """Некорректная конфигурация OpenFGA / object id."""
