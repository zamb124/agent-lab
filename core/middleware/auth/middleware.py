"""
Компактный AuthMiddleware с декларативной конфигурацией.

Внутренний слой по отношению к AccessLogMiddleware: request_id и trace_id
уже забиндены в лог-контекст и доступны через `request.state.request_id`
и `request.state.trace_id`. AuthMiddleware дополняет лог-контекст полями
user/company/session/namespace при успешной авторизации; снятие скоупа
делает AccessLogMiddleware.
"""

import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from core.context import clear_context, set_context
from core.identity.runtime_users import ensure_persisted_runtime_user
from core.logging import bind_log_context, get_logger
from core.logging.attributes import (
    LOG_COMPANY_ID,
    LOG_COMPANY_SUBDOMAIN,
    LOG_NAMESPACE,
    LOG_SESSION_ID,
    LOG_USER_ID,
)
from core.models.identity_models import Company, User, UserStatus
from core.utils.auth_session_rebind import attach_session_auth_cookie, rebind_session_to_company
from core.utils.domain import extract_subdomain
from core.utils.tokens import TokenData, TokenType, get_token_service

from .company_access_error_page import (
    build_company_access_error_response,
    http_exception_detail_to_str,
)
from .company_resolver import CompanyResolver
from .context_factory import ContextFactory
from .platform_handlers import get_platform_handler
from .route_config import (
    RouteMatcher,
    RouteRule,
    browser_request_accepts_company_access_error_html,
    browser_request_allows_spa_fallback,
    path_allows_spa_fallback,
)

logger = get_logger(__name__)

EMBED_SESSION_TOKEN_REQUIRED_SCOPES = {"agents:read", "agents:write"}


class CompanyCreationRequired(Exception):
    """Пользователю нужно создать или выбрать компанию"""
    pass


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware для создания контекста запроса"""

    def __init__(self, app):
        super().__init__(app)
        self.route_matcher = RouteMatcher()

    def _get_container(self, request: Request):
        return request.app.state.container

    def _trace_id_from_state(self, request: Request) -> str:
        trace_id = getattr(request.state, "trace_id", None)
        if not isinstance(trace_id, str) or not trace_id.strip():
            raise RuntimeError(
                "AuthMiddleware: request.state.trace_id отсутствует. "
                "Проверьте, что AccessLogMiddleware подключён внешним слоем."
            )
        return trace_id

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        trace_id = self._trace_id_from_state(request)

        if self.route_matcher.should_skip(path):
            return await call_next(request)

        container = self._get_container(request)
        company_resolver = CompanyResolver(container)
        context_factory = ContextFactory(container)

        rule = self.route_matcher.match(path)
        if rule and rule.skip:
            return await call_next(request)

        if not rule:
            if path_allows_spa_fallback(path) and browser_request_allows_spa_fallback(request):
                rule = RouteRule(
                    pattern="/*",
                    auth_required=False,
                    context_type="anonymous",
                )
                logger.info("auth.spa_fallback", path=path)
            else:
                logger.debug(
                    "auth.route_not_found",
                    path=path,
                    http_method=request.method,
                )
                return JSONResponse(status_code=404, content={"detail": "Not Found"})

        if not path.startswith(("/openapi", "/docs", "/static")):
            logger.info(
                "auth.route_matched",
                path=path,
                context_type=rule.context_type,
                auth_required=rule.auth_required,
            )

        try:
            context = await self._create_context(
                request, rule, container, company_resolver, context_factory, trace_id
            )

            # Сохраняем token_data для эндпоинтов типа /auth/me
            token_data, _ = await self._extract_token(request, container)
            session_td = getattr(request.state, "session_token_data", None)
            if session_td is not None:
                token_data = session_td

            set_context(context)
            request.state.context = context
            request.state.user = context.user
            request.state.company = context.active_company
            request.state.language = context.language.value
            request.state.user_companies = context.user_companies
            request.state.token_data = token_data

            log_fields: dict[str, str | None] = {}
            if context.user is not None:
                log_fields[LOG_USER_ID] = context.user.user_id
            if context.active_company is not None:
                log_fields[LOG_COMPANY_ID] = context.active_company.company_id
                if context.active_company.subdomain:
                    log_fields[LOG_COMPANY_SUBDOMAIN] = context.active_company.subdomain
            if context.session_id:
                log_fields[LOG_SESSION_ID] = context.session_id
            if context.active_namespace and context.active_namespace != "default":
                log_fields[LOG_NAMESPACE] = context.active_namespace
            if log_fields:
                bind_log_context(**log_fields)

            if (
                rule.context_type == "frontend"
                and path.startswith("/litserve")
                and not path.startswith("/litserve/ui/static")
            ):
                ac = context.active_company
                if ac is None or ac.company_id != "system":
                    raise HTTPException(
                        status_code=403,
                        detail="Интерфейс LitServe доступен только при активной компании system.",
                    )

            response = await call_next(request)
            reissue = getattr(request.state, "reissue_auth_token", None)
            if reissue is not None:
                attach_session_auth_cookie(response, request, reissue)
            return response

        except CompanyCreationRequired:
            return RedirectResponse(url="/select-company", status_code=307)
        except HTTPException as e:
            accept = request.headers.get("accept", "")
            if e.status_code == 401 and "text/html" in accept:
                return RedirectResponse(url="/", status_code=302)  # На главную для авторизации
            if e.status_code in (403, 404) and browser_request_accepts_company_access_error_html(
                request
            ):
                return build_company_access_error_response(
                    e.status_code, http_exception_detail_to_str(e.detail)
                )
            return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
        finally:
            clear_context()

    async def _create_context(
        self,
        request: Request,
        rule: RouteRule,
        container,
        company_resolver: CompanyResolver,
        context_factory: ContextFactory,
        trace_id: str,
    ):
        """Создает контекст на основе правила маршрутизации"""

        if self._auth_disabled_auto_context_allowed(request, rule):
            return await self._create_auth_disabled_auto_context(
                request,
                container,
                context_factory,
                trace_id,
                rule.context_type,
            )

        # Webhook обработка
        if rule.context_type == "webhook" and rule.channel:
            return await self._handle_webhook(request, rule, container, context_factory, trace_id)

        # Анонимный контекст (но пробуем загрузить пользователя если токен есть)
        if rule.context_type == "anonymous":
            # Для anonymous контекста компания НЕ требуется (публичные страницы)
            # Извлекаем компанию только если есть субдомен (для публичных страниц компании)
            company = None
            host = request.headers.get("host", "")
            if extract_subdomain(host):
                company = await company_resolver.resolve(request, context_type="anonymous")
            token_data, auth_token = await self._extract_token(request, container)
            user = await self._get_user(container, token_data) if token_data else None
            return await context_factory.create(
                request, "anonymous", company, user, token_data,
                auth_token=auth_token, trace_id=trace_id
            )

        # Авторизованный контекст
        token_data, auth_token = await self._extract_token(request, container)

        if rule.auth_required and not token_data:
            raise HTTPException(status_code=401, detail="Unauthorized")

        user = await self._get_user(container, token_data) if token_data else None

        token_type = token_data.token_type if token_data else None
        is_embed_session = token_type == TokenType.EMBED_SESSION
        if rule.auth_required and not user and not is_embed_session:
            raise HTTPException(status_code=401, detail="User not found")

        company = await company_resolver.resolve(request, token_data, rule.context_type)

        logger.info(
            "auth.context_resolved",
            path=request.url.path,
            context_type=rule.context_type,
            company_id=company.company_id if company else None,
            host=request.headers.get("host"),
        )

        if rule.context_type == "frontend" and not company:
            if not self.route_matcher.allows_no_subdomain(request.url.path):
                logger.info(
                    "auth.subdomain_required",
                    path=request.url.path,
                )
                raise CompanyCreationRequired()
            logger.info("auth.frontend_no_subdomain_allowed", path=request.url.path)

        # Проверка доступа к удаляемой компании
        if company and company.status == "deleting":
            if not self.route_matcher.allows_deleting_company(request.url.path):
                raise HTTPException(
                    status_code=403,
                    detail="Компания удаляется. Пожалуйста, выберите другую компанию."
                )

        # Проверка доступа пользователя к компании (для frontend)
        if user and company and rule.context_type == "frontend":
            if company.company_id not in user.companies:
                if not self.route_matcher.allows_no_subdomain(request.url.path):
                    raise CompanyCreationRequired()

        if (
            user
            and company
            and rule.context_type in ("frontend", "api")
            and token_data
            and token_data.token_type == TokenType.SESSION
            and token_data.company_id
            and token_data.company_id != company.company_id
            and extract_subdomain(request.headers.get("host", "")) is not None
        ):
            if company.company_id not in user.companies:
                raise HTTPException(
                    status_code=403,
                    detail="У вас нет доступа к компании с этим адресом (субдомен).",
                )
            jwt_str, session_td = await rebind_session_to_company(
                container=container,
                user=user,
                company=company,
            )
            request.state.reissue_auth_token = jwt_str
            request.state.session_token_data = session_td
            token_data = session_td
            auth_token = jwt_str

        # Синхронизация активной компании (для всех типов контекста)
        if user and company:
            await self._sync_active_company(container, user, company)

        return await context_factory.create(
            request, rule.context_type, company, user, token_data,
            platform=rule.channel,  # channel используется как platform для webhook
            auth_token=auth_token,
            trace_id=trace_id
        )

    def _auth_disabled_auto_context_allowed(self, request: Request, rule: RouteRule) -> bool:
        settings = getattr(request.app.state, "settings", None)
        auth = getattr(settings, "auth", None)
        server = getattr(settings, "server", None)
        if not auth or getattr(auth, "enabled", True):
            return False
        if not getattr(auth, "dev_auto_context_enabled", False):
            return False
        if getattr(settings, "testing", False):
            return False
        if getattr(server, "env", "production") == "production":
            return False
        return rule.auth_required

    async def _create_auth_disabled_auto_context(
        self,
        request: Request,
        container,
        context_factory: ContextFactory,
        trace_id: str,
        context_type: str,
    ):
        settings = request.app.state.settings
        auth = settings.auth
        company_id = auth.dev_auto_company_id or "system"
        company = await container.company_repository.get(company_id)
        if company is None:
            company = Company(
                company_id=company_id,
                name=auth.dev_auto_company_name or company_id,
                subdomain=None,
                owner_user_id=auth.dev_auto_user_id,
                members={auth.dev_auto_user_id: ["admin"]},
            )
            await container.company_repository.set(company)

        groups = list(dict.fromkeys(auth.dev_auto_groups or ["admin", "developers"]))
        user = User(
            user_id=auth.dev_auto_user_id,
            name="Dev Auto User",
            status=UserStatus.ACTIVE,
            groups=groups,
            companies={company.company_id: groups},
            active_company_id=company.company_id,
            emails=[f"{auth.dev_auto_user_id}@dev.local"],
        )
        user = await ensure_persisted_runtime_user(
            container,
            user_id=user.user_id,
            company_id=company.company_id,
            name=user.name,
            roles=groups,
            attrs={"kind": "dev_auto_user"},
            email=user.emails[0] if user.emails else None,
        )
        logger.warning(
            "auth.disabled_auto_context",
            path=request.url.path,
            user_id=user.user_id,
            company_id=company.company_id,
            context_type=context_type,
        )
        return await context_factory.create(
            request,
            context_type,
            company,
            user,
            token_data=None,
            auth_token=None,
            trace_id=trace_id,
        )

    async def _handle_webhook(
        self,
        request: Request,
        rule: RouteRule,
        container,
        context_factory: ContextFactory,
        trace_id: str,
    ):
        """Обрабатывает webhook запросы"""
        platform = rule.channel
        if platform is None:
            raise HTTPException(status_code=400, detail="Webhook platform is not configured")
        handler = get_platform_handler(platform, container)
        if not handler:
            raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")

        company = await handler.extract_company_from_webhook_path(request.url.path, platform)

        # GET для WhatsApp верификации - анонимный контекст
        if platform == "whatsapp" and request.method == "GET":
            return await context_factory.create(request, "anonymous", company, trace_id=trace_id)

        user, metadata = await handler.create_user_from_request(request, company)

        context = await context_factory.create(
            request, "webhook", company, user, platform=platform, trace_id=trace_id
        )
        context.metadata.update(metadata)

        logger.info(
            "auth.webhook_context_resolved",
            platform=platform,
            company_id=company.company_id if company else None,
        )
        return context

    async def _extract_token(
        self,
        request: Request,
        container,
    ) -> tuple[TokenData | None, str | None]:
        """
        Извлекает и валидирует токен из запроса.

        Returns:
            tuple: (token_data, raw_token) - данные токена и сам токен для межсервисных запросов
        """
        token = request.cookies.get("auth_token")
        path = request.url.path
        is_public_path = path.startswith(("/openapi", "/docs", "/static"))

        if not is_public_path:
            logger.debug(
                "auth.cookie_lookup",
                path=path,
                cookie_present=bool(token),
            )

        token_from_authorization = False
        if not token:
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
                token_from_authorization = True
                if not is_public_path:
                    logger.debug("auth.bearer_token_used", path=path)

        if not token:
            return None, None

        if token_from_authorization and token.count(".") != 2:
            if path.startswith("/v1/"):
                return None, None
            api_key_token_data = await self._build_api_key_token_data(
                container=container,
                raw_token=token,
                path=path,
            )
            if api_key_token_data is None:
                logger.warning("auth.api_key_invalid", path=path)
                return None, None
            return api_key_token_data, token

        token_service = get_token_service()
        token_data = token_service.validate_token(token)

        if token_data:
            if not is_public_path:
                logger.debug(
                    "auth.token_valid",
                    user_id=token_data.user_id,
                    company_id=token_data.company_id,
                )
        else:
            logger.warning("auth.token_invalid", path=path)

        return token_data, token if token_data else None

    @staticmethod
    def _required_api_key_scopes_for_path(path: str) -> set[str]:
        if path.startswith("/frontend/api/embed/configs/") and path.endswith("/session-token"):
            return EMBED_SESSION_TOKEN_REQUIRED_SCOPES
        return set()

    async def _build_api_key_token_data(
        self,
        *,
        container,
        raw_token: str,
        path: str,
    ) -> TokenData | None:
        if not raw_token.startswith("hum_"):
            return None
        key_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        api_key_record = await container.api_key_repository.get_by_hash(key_hash)
        if api_key_record is None:
            return None

        required_scopes = self._required_api_key_scopes_for_path(path)
        if required_scopes and not (set(api_key_record.scopes) & required_scopes):
            return None

        await container.api_key_repository.touch_last_used(
            key_id=api_key_record.key_id,
            company_id=api_key_record.company_id,
        )
        now = datetime.now(timezone.utc)
        return TokenData(
            user_id=api_key_record.created_by,
            company_id=api_key_record.company_id,
            roles=[],
            token_type=TokenType.API,
            iat=now,
            exp=now + timedelta(days=365),
            metadata={
                "auth_kind": "api_key",
                "api_key_id": api_key_record.key_id,
                "api_key_scopes": api_key_record.scopes,
            },
        )

    async def _get_user(self, container, token_data: TokenData) -> User | None:
        """Получает пользователя по данным токена"""
        user = await container.user_repository.get(token_data.user_id)
        if user is None and token_data.token_type == TokenType.EMBED_SESSION:
            user = await ensure_persisted_runtime_user(
                container,
                user_id=token_data.user_id,
                company_id=token_data.company_id,
                name="Embed Guest",
                roles=["guest"],
                attrs={
                    "kind": "embed_session_guest",
                    "token_expires_at": token_data.exp.isoformat(),
                    "embed_id": token_data.metadata.get("embed_id"),
                    "embed_flow_id": token_data.metadata.get("embed_flow_id"),
                    "embed_branch_id": token_data.metadata.get("embed_branch_id"),
                    "issued_by": token_data.metadata.get("issued_by"),
                },
            )
        if user:
            logger.debug("auth.user_loaded", user_id=token_data.user_id)
        return user

    async def _sync_active_company(self, container, user: User, company):
        """Синхронизирует активную компанию пользователя"""
        if user.active_company_id != company.company_id:
            logger.info(
                "auth.active_company_switched",
                previous_company_id=user.active_company_id,
                company_id=company.company_id,
            )
            user.active_company_id = company.company_id
            await container.user_repository.set(user)
