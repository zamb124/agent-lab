"""Валидация subdomain компании."""
import re

# Зарезервированные slug'и: субдомены платформы, OnlyOffice Document Server,
# observability-стек, LiveKit и CDN статики/embed.
_RESERVED_SUBDOMAINS: frozenset[str] = frozenset(
    {
        "www",
        "api",
        "admin",
        "static",
        "cdn",
        "system",
        "test",
        "staging",
        "production",
        "localhost",
        "onlyoffice",
        "grafana",
        "loki",
        "tempo",
        "alloy",
        "livekit",
    }
)


def validate_slug(slug: str) -> tuple[bool, str | None]:
    """
    Валидирует slug для использования в субдомене

    Примеры:
        >>> validate_slug("mycompany")
        (True, None)
        >>> validate_slug("ab")
        (False, "Минимальная длина - 3 символа")
    """
    if not slug:
        return False, "Slug не может быть пустым"

    if len(slug) < 3:
        return False, "Минимальная длина - 3 символа"

    if len(slug) > 63:
        return False, "Максимальная длина - 63 символа"

    if not re.match(r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?$', slug):
        return False, "Только латинские буквы, цифры и дефис. Должен начинаться и заканчиваться буквой или цифрой"

    if slug in _RESERVED_SUBDOMAINS:
        return False, f"'{slug}' - зарезервированное имя"

    return True, None
