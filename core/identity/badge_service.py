"""Вход по бейджу сотрудника — платформенный, для любых терминалов.

Бейдж — запись ``user_badges``: ``(company_id, code)`` → ``user_id``.
Логин идёт через ``POST /auth/login/badge`` на любом сервисе платформы
(куки сессии ставит HTTP-ответ). Компания определяется Host-ом запроса —
бейдж без тенантного контекста недействителен.
"""

from __future__ import annotations

from core.clients.redis_client import RedisClient
from core.errors.boundary import PlatformAccessDeniedError, PlatformNotFoundError
from core.identity.auth_service import AuthService
from core.models.identity_models import Company, UserBadge
from core.models.identity_models.auth_result import AuthResult
from core.utils.domain import extract_company_subdomain

_RL = "platform:rl:badge_login:"
_RL_IP_LIMIT = 30
_RL_IP_TTL = 300


class BadgeService:
    """Скан бейджа → SESSION JWT сотрудника через AuthService."""

    def __init__(self, auth: AuthService, redis: RedisClient) -> None:
        self._auth: AuthService = auth
        self._redis: RedisClient = redis

    async def login_badge(
        self, *, company_id: str, code: str, client_ip: str
    ) -> AuthResult:
        """Код бейджа → сессия или понятная ошибка.

        Rate-limit по IP защищает перебор кодов и считает каждую
        попытку — до проверки самого кода.
        """
        if client_ip != "":
            await self._rate_limit_ip(client_ip)
        normalized = code.strip()
        if normalized == "":
            raise PlatformNotFoundError(
                "Badge not found", error_code="badge_not_found"
            )
        badge = await UserBadge.resolve(company_id, normalized)
        if badge is None:
            raise PlatformNotFoundError(
                "Badge not found", error_code="badge_not_found"
            )
        user = await self._auth.get_user(badge.user_id)
        if user is None:
            raise PlatformNotFoundError(
                "Badge owner not found", error_code="badge_owner_not_found"
            )
        result = await self._auth.login_badge(user, company_id)
        if not result.success or result.session is None or result.token is None:
            raise PlatformAccessDeniedError(
                result.error_message or "Badge login denied",
                error_code="badge_login_denied",
            )
        return result

    async def resolve_login_company(self, host: str) -> Company:
        """Компания входа по Host запроса: subdomain → ``Company``.

        Терминал открыт на поддомене компании; без субдомена логин по
        бейджу невозможен — контекст tenant'а обязателен.
        """
        subdomain = extract_company_subdomain(host)
        if subdomain is None:
            raise PlatformAccessDeniedError(
                "Badge login requires company subdomain",
                error_code="badge_company_required",
            )
        company = await Company.by_subdomain(subdomain)
        if company is None:
            raise PlatformNotFoundError(
                "Company not found", error_code="badge_company_not_found"
            )
        return company

    async def _rate_limit_ip(self, client_ip: str) -> None:
        counter = f"{_RL}ip:{client_ip}"
        count = await self._redis.eval(
            "local n = redis.call('INCR', KEYS[1]) if n == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end return n",
            1,
            counter,
            _RL_IP_TTL,
        )
        if isinstance(count, int) and count > _RL_IP_LIMIT:
            raise PlatformAccessDeniedError(
                "Too many badge login attempts", error_code="badge_login_rate_limited"
            )
