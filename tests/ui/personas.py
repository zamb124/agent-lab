"""Персоны E2E UI: те же компании и роли, что в tests/fixtures/auth.py — выбор юзера одной фикстурой."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from core.utils.tokens import TokenData, get_token_service


class UiPersona(StrEnum):
    """Кто открывает браузер в тесте."""

    SYSTEM_OWNER = "system_owner"
    SYSTEM_MEMBER = "system_member"
    COMPANY2_OWNER = "company2_owner"
    COMPANY2_MEMBER = "company2_member"
    ANONYMOUS = "anonymous"


@dataclass(frozen=True, slots=True)
class UiTestUser:
    """Идентичность для проверок в тесте; у anonymous нет токена и id."""

    persona: UiPersona
    user_id: str | None
    company_id: str | None
    roles: tuple[str, ...]
    token: str | None


ANONYMOUS_UI_USER = UiTestUser(
    persona=UiPersona.ANONYMOUS,
    user_id=None,
    company_id=None,
    roles=(),
    token=None,
)


def ui_test_user_from_token(persona: UiPersona, token: str) -> UiTestUser:
    token_service = get_token_service()
    data: TokenData | None = token_service.validate_token(token)
    if data is None:
        raise ValueError(f"Невалидный токен для персоны {persona.value}")
    return UiTestUser(
        persona=persona,
        user_id=data.user_id,
        company_id=data.company_id,
        roles=tuple(data.roles),
        token=token,
    )
