"""
Определение компании из запроса.
"""


import time

from fastapi import HTTPException, Request

from core.config import settings
from core.logging import get_logger
from core.models.identity_models import Company, User
from core.utils.domain import extract_company_subdomain, extract_subdomain
from core.utils.tokens import TokenData

from .route_config import RouteContextType

logger = get_logger(__name__)
# POST принятия инвайта: пользователь намеренно ещё не в members этой компании
_INVITE_ACCEPT_PATHS = frozenset({
    "/api/invites/accept",
    "/frontend/api/invites/accept",
})

# GET идентичности вошедшего: ответ содержит только данные самого пользователя
# и его session company — данных host-компании в нём нет. Без этого исключения
# вошедший пользователь чужой компании не может даже открыть /join: проба
# auth/me падает 403 до рендера карточки приглашения.
_IDENTITY_READ_PATHS = frozenset({
    "/api/auth/me",
    "/frontend/api/auth/me",
})

# In-process TTL-кэш для горячих lookup auth middleware.
# Каждый HTTP-запрос ранее тащил 3 DB-запроса: subdomain->company_id, company,
# user (для membership). На production это десятки тысяч запросов в секунду,
# поэтому стоит небольшой process-local cache (30 секунд TTL).
#
# Межинстансная согласованность сейчас держится только на TTL: при изменении
# company/user.companies значение может быть устаревшим до 30 секунд. Для
# critical mutating endpoints это приемлемо: rebind session + правка members
# делаются редко, а каждая mutating операция перепроверяет access на бизнес-
# уровне (репозитории не используют этот cache).
_COMPANY_RESOLVER_CACHE_TTL_SECONDS = 30


class _TtlCache[K, V]:
    """
    Process-local TTL-кэш ``K -> V`` для горячих lookup CompanyResolver.

    Намеренно простой: без LRU eviction (auth-горячая память невелика — число
    активных subdomain'ов / company_id / (user, company) пар на одном узле
    ограничено). `time.monotonic` устойчив к перескокам wall clock.
    """

    def __init__(self, *, ttl_seconds: int) -> None:
        self._ttl_seconds: int = ttl_seconds
        self._items: dict[K, tuple[float, V]] = {}

    def get(self, key: K) -> V | None:
        record = self._items.get(key)
        if record is None:
            return None
        expires_at, value = record
        if expires_at <= time.monotonic():
            del self._items[key]
            return None
        return value

    def set(self, key: K, value: V) -> None:
        self._items[key] = (time.monotonic() + self._ttl_seconds, value)

    def invalidate(self, key: K) -> None:
        _ = self._items.pop(key, None)


class CompanyResolver:
    """Определяет компанию из запроса"""

    def __init__(self) -> None:
        self._subdomain_to_company_id_cache: _TtlCache[str, str | None] = _TtlCache(
            ttl_seconds=_COMPANY_RESOLVER_CACHE_TTL_SECONDS
        )
        self._company_cache: _TtlCache[str, Company | None] = _TtlCache(
            ttl_seconds=_COMPANY_RESOLVER_CACHE_TTL_SECONDS
        )
        self._user_membership_cache: _TtlCache[tuple[str, str], bool] = _TtlCache(
            ttl_seconds=_COMPANY_RESOLVER_CACHE_TTL_SECONDS
        )

    def invalidate_company(self, company_id: str) -> None:
        """Сброс кеша Company при mutating-операциях (rename, members update)."""
        self._company_cache.invalidate(company_id)

    def invalidate_subdomain(self, subdomain: str) -> None:
        """Сброс кеша subdomain→company_id при перепривязке домена."""
        self._subdomain_to_company_id_cache.invalidate(subdomain)

    def invalidate_user_membership(self, user_id: str, company_id: str) -> None:
        """Сброс кеша membership при изменении user.companies."""
        self._user_membership_cache.invalidate((user_id, company_id))

    async def _cached_subdomain_to_company_id(self, subdomain: str) -> str | None:
        cached = self._subdomain_to_company_id_cache.get(subdomain)
        if cached is not None:
            return cached or None
        company = await Company.by_subdomain(subdomain)
        company_id = None if company is None else company.company_id
        if company is not None:
            self._company_cache.set(company.company_id, company)
        self._subdomain_to_company_id_cache.set(subdomain, company_id or "")
        return company_id

    async def _cached_company(self, company_id: str) -> Company | None:
        cached = self._company_cache.get(company_id)
        if cached is not None:
            return cached
        company = await Company.get(company_id)
        self._company_cache.set(company_id, company)
        return company

    async def _cached_user_has_company(self, user_id: str, company_id: str) -> bool:
        cached = self._user_membership_cache.get((user_id, company_id))
        if cached is not None:
            return cached
        user = await User.get(user_id)
        has = bool(user and company_id in user.companies)
        self._user_membership_cache.set((user_id, company_id), has)
        return has

    async def resolve(
        self,
        request: Request,
        token_data: TokenData | None = None,
        context_type: RouteContextType = "frontend",
    ) -> Company | None:
        """
        Субдомен Host кодирует company context: для всех не-anonymous контекстов компания субдомена
        имеет приоритет над JWT / X-Company-Id, с проверкой membership.

        Публичные anonymous-роуты: компания с субдомена по возможности, без membership.
        """
        if context_type == "anonymous":
            return await self._resolve_anonymous(request)
        return await self._resolve_company_from_host(request, token_data, context_type)

    async def _resolve_anonymous(self, request: Request) -> Company | None:
        host = request.headers.get("host", "")

        override_company_id = request.headers.get("X-Company-Id")
        if override_company_id:
            if settings.server.env != "production":
                company = await self._cached_company(override_company_id)
                if company:
                    logger.debug("middleware.anonymous.x.company.id.dev")
                    return company
                logger.warning("middleware.anonymous.x.company.id")

        subdomain = self._extract_subdomain(host)
        if not subdomain:
            logger.debug("middleware.anonymous.host")
            return None

        company_id = await self._cached_subdomain_to_company_id(subdomain)
        if not company_id:
            logger.debug("middleware.anonymous.host.subdomain_repo")
            return None

        company = await self._cached_company(company_id)
        if company:
            logger.debug("auth.company.anonymous_subdomain", subdomain=subdomain)
            return company
        logger.debug("middleware.anonymous.company_id.company")
        return None

    async def _assert_subdomain_company_membership(
        self,
        request: Request,
        company_id: str,
        subdomain: str,
        token_data: TokenData | None,
    ) -> None:
        if not token_data or not token_data.user_id:
            return
        if await self._cached_user_has_company(token_data.user_id, company_id):
            return
        if request.method == "POST" and request.url.path in _INVITE_ACCEPT_PATHS:
            logger.info(
                "middleware.membership.path",
                user_id=token_data.user_id,
                company_id=company_id,
                path=request.url.path,
            )
            return
        if request.method == "GET" and request.url.path in _IDENTITY_READ_PATHS:
            return
        logger.warning(
            "auth.company.membership_denied",
            user_id=token_data.user_id,
            company_id=company_id,
            subdomain=subdomain,
        )
        raise HTTPException(
            status_code=403,
            detail=f"You do not have access to company {subdomain}",
        )

    def _x_company_id_must_match_company_subdomain(
        self, request: Request, subdomain_company_id: str
    ) -> None:
        override = request.headers.get("X-Company-Id")
        if not override:
            return
        if override != subdomain_company_id:
            logger.warning(
                "auth.company.x_company_id_mismatch",
                override_company_id=override,
                subdomain_company_id=subdomain_company_id,
            )
            raise HTTPException(
                status_code=403,
                detail='X-Company-Id does not match the subdomain host',
            )

    async def _resolve_company_from_host(
        self,
        request: Request,
        token_data: TokenData | None,
        context_type: RouteContextType,
    ) -> Company | None:
        host = request.headers.get("host", "")
        subdomain = extract_company_subdomain(host)

        if subdomain:
            company_id = await self._cached_subdomain_to_company_id(subdomain)
            if company_id:
                self._x_company_id_must_match_company_subdomain(request, company_id)
                await self._assert_subdomain_company_membership(
                    request, company_id, subdomain, token_data
                )
                company = await self._cached_company(company_id)
                if company:
                    logger.debug("auth.company.from_subdomain", subdomain=subdomain, company_id=company_id)
                    return company
                raise HTTPException(
                    status_code=404, detail=f"Company not found for subdomain: {subdomain}"
                )
            if settings.server.env == "production":
                raise HTTPException(
                    status_code=404,
                    detail=f"Company not found for subdomain: {subdomain}",
                )
            logger.warning(
                "company_resolver.subdomain_missing_registry_nonprod_fallback",
                subdomain=subdomain,
                host=host,
                path=request.url.path,
            )

        if context_type == "frontend":
            logger.info("auth.company.frontend_no_subdomain", host=host)
            return None

        override_company_id = request.headers.get("X-Company-Id")
        if override_company_id:
            if settings.server.env != "production":
                company = await self._cached_company(override_company_id)
                if company:
                    logger.debug("auth.company.from_header_dev", company_id=override_company_id)
                    return company
                logger.warning("auth.company.header_not_found", company_id=override_company_id)

            elif token_data and token_data.user_id:
                if not await self._cached_user_has_company(
                    token_data.user_id, override_company_id
                ):
                    user_exists = bool(
                        await User.get(token_data.user_id)
                    )
                    if not user_exists:
                        logger.warning("auth.company.user_not_found", user_id=token_data.user_id)
                        raise HTTPException(status_code=403, detail='User not found')
                    logger.warning(
                        "auth.company.header_membership_denied",
                        user_id=token_data.user_id,
                        company_id=override_company_id,
                    )
                    raise HTTPException(
                        status_code=403,
                        detail=f"You do not have access to company {override_company_id}",
                    )

                company = await self._cached_company(override_company_id)
                if company:
                    logger.debug("auth.company.from_header", company_id=override_company_id)
                    return company
                logger.warning("auth.company.header_not_found", company_id=override_company_id)

        if token_data and token_data.company_id:
            company = await self._cached_company(token_data.company_id)
            if company:
                logger.debug("auth.company.from_token", company_id=token_data.company_id)
                return company
            raise HTTPException(
                status_code=403, detail=f"Company {token_data.company_id} not found"
            )

        return None

    def _extract_subdomain(self, host: str) -> str | None:
        return extract_subdomain(host)

    def has_subdomain(self, request: Request) -> bool:
        host = request.headers.get("host", "")
        if request.headers.get("X-Company-Id"):
            return True
        return extract_subdomain(host) is not None


def build_service_base_url(request: Request, *, include_default_port: bool = False) -> str:
    """Каноничный base URL для request: `scheme://host[:port]`.

    Учитывает reverse-proxy:
    - `X-Forwarded-Proto` (`http`/`https`) перекрывает `request.url.scheme`.
    - `X-Forwarded-Host` перекрывает `Host`-header и `request.url.netloc`.

    Аргументы:
        request: FastAPI/Starlette Request.
        include_default_port: если True, для host без порта добавит
            `:80`/`:443` исходя из scheme.

    Исключения:
        ValueError: scheme не `http`/`https` или host пуст.
    """
    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").split(",", 1)[0].strip().lower()
    scheme = forwarded_proto if forwarded_proto in ("http", "https") else (request.url.scheme or "").strip().lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"build_service_base_url: expected http or https scheme, got {scheme!r}")

    forwarded_host = (request.headers.get("x-forwarded-host") or "").strip()
    host = forwarded_host or (request.headers.get("host") or "").strip() or (request.url.netloc or "").strip()
    if not host:
        raise ValueError('build_service_base_url: host is not defined (no X-Forwarded-Host, Host header, netloc)')

    if include_default_port and ":" not in host:
        if request.url.port:
            host = f"{host}:{request.url.port}"
        elif scheme == "https":
            host = f"{host}:443"
        elif scheme == "http":
            host = f"{host}:80"

    return f"{scheme}://{host}"
