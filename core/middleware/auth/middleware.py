"""
Компактный AuthMiddleware с декларативной конфигурацией.
"""

import logging
import hashlib
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from core.context import set_context, clear_context
from core.config import get_settings
from core.models.identity_models import User, Company
from core.models.context_models import Context, Language
from core.utils.tokens import get_token_service, TokenData, TokenType

from .route_config import (
    RouteMatcher,
    RouteRule,
    browser_request_allows_spa_fallback,
    path_allows_spa_fallback,
)
from .company_resolver import CompanyResolver
from .context_factory import ContextFactory
from .platform_handlers import get_platform_handler

logger = logging.getLogger(__name__)

TRACE_ID_HEADER = "X-Trace-Id"
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
    
    def _get_or_create_trace_id(self, request: Request) -> str:
        """
        Извлекает trace_id из заголовка или генерирует новый.
        
        Формат: {service_name}:{uuid4}
        Если trace_id уже пришел из другого сервиса - используем его как есть.
        """
        trace_id = request.headers.get(TRACE_ID_HEADER)
        if trace_id:
            return trace_id
        
        settings = get_settings()
        service_name = settings.server.name
        return f"{service_name}:{uuid.uuid4()}"
    
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        trace_id = self._get_or_create_trace_id(request)
        
        # ТЕСТЫ ТОЖЕ ДОЛЖНЫ ПРОХОДИТЬ ЧЕРЕЗ НОРМАЛЬНУЮ АВТОРИЗАЦИЮ!
        # НЕТ НИКАКИХ ФОЛБЕКОВ НА "system" ЮЗЕРА!
        
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
                logger.info(
                    f"SPA fallback (anonymous): path={path}, trace_id={trace_id}"
                )
            else:
                logger.debug(
                    f"Маршрут не найден (не SPA): path={path}, method={request.method}, trace_id={trace_id}"
                )
                return JSONResponse(status_code=404, content={"detail": "Not Found"})
        
        # Не логировать для публичных путей
        if not path.startswith(("/openapi", "/docs", "/static")):
            logger.info(f"🎯 Matched rule for {path}: context_type={rule.context_type}, auth_required={rule.auth_required}")
        
        try:
            context = await self._create_context(
                request, rule, container, company_resolver, context_factory, trace_id
            )
            
            # Сохраняем token_data для эндпоинтов типа /auth/me
            token_data, _ = await self._extract_token(request, container)
            
            set_context(context)
            request.state.context = context
            request.state.user = context.user
            request.state.company = context.active_company
            request.state.language = context.language.value
            request.state.user_companies = context.user_companies
            request.state.token_data = token_data
            
            response = await call_next(request)
            return response
            
        except CompanyCreationRequired:
            return RedirectResponse(url="/select-company", status_code=307)
        except HTTPException as e:
            accept = request.headers.get("accept", "")
            if e.status_code == 401 and "text/html" in accept:
                return RedirectResponse(url="/", status_code=302)  # На главную для авторизации
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
        
        # Webhook обработка
        if rule.context_type == "webhook" and rule.channel:
            return await self._handle_webhook(request, rule, container, context_factory, trace_id)
        
        # Анонимный контекст (но пробуем загрузить пользователя если токен есть)
        if rule.context_type == "anonymous":
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
        
        logger.info(f"🔍 Путь: {request.url.path}, context_type={rule.context_type}, company={company.company_id if company else None}, host={request.headers.get('host')}")
        
        # Frontend без субдомена -> редирект на выбор компании
        if rule.context_type == "frontend" and not company:
            logger.info(f"🚨 Frontend без компании! Проверяем allows_no_subdomain для {request.url.path}")
            if not self.route_matcher.allows_no_subdomain(request.url.path):
                logger.info(f"🚫 Путь {request.url.path} требует субдомен! Бросаем CompanyCreationRequired")
                raise CompanyCreationRequired()
            else:
                logger.info(f"✅ Путь {request.url.path} разрешен без субдомена")
        
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
        
        # Синхронизация активной компании (для всех типов контекста)
        if user and company:
                await self._sync_active_company(container, user, company)
        
        return await context_factory.create(
            request, rule.context_type, company, user, token_data,
            platform=rule.channel,  # channel используется как platform для webhook
            auth_token=auth_token, 
            trace_id=trace_id
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
        handler = get_platform_handler(rule.channel, container)
        if not handler:
            raise HTTPException(status_code=400, detail=f"Unknown platform: {rule.channel}")
        
        company = await handler.extract_company_from_webhook_path(request.url.path, rule.channel)
        
        # GET для WhatsApp верификации - анонимный контекст
        if rule.channel == "whatsapp" and request.method == "GET":
            return await context_factory.create(request, "anonymous", company, trace_id=trace_id)
        
        user, metadata = await handler.create_user_from_request(request, company)
        
        context = await context_factory.create(
            request, "webhook", company, user, platform=rule.channel, trace_id=trace_id
        )
        context.metadata.update(metadata)
        
        logger.info(f"{rule.channel.title()} webhook: компания {company.company_id}, trace_id={trace_id}")
        return context
    
    async def _extract_token(
        self,
        request: Request,
        container,
    ) -> tuple[Optional[TokenData], Optional[str]]:
        """
        Извлекает и валидирует токен из запроса.
        
        Returns:
            tuple: (token_data, raw_token) - данные токена и сам токен для межсервисных запросов
        """
        token = request.cookies.get("auth_token")
        path = request.url.path
        is_public_path = path.startswith(("/openapi", "/docs", "/static"))
        
        # Логирование для отладки (не для публичных путей)
        if not token:
            if not is_public_path:
                logger.debug(f"Токен не найден в cookies для {path}")
        else:
            if not is_public_path:
                logger.debug(f"Токен найден в cookies для {path}")
        
        token_from_authorization = False
        if not token:
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
                token_from_authorization = True
                if not is_public_path:
                    logger.debug(f"Токен найден в Authorization header")
        
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
                logger.warning(f"API ключ невалиден или не имеет доступа к {path}")
                return None, None
            return api_key_token_data, token
        
        token_service = get_token_service()
        token_data = token_service.validate_token(token)
        
        if token_data:
            if not is_public_path:
                logger.debug(f"Токен валиден: user_id={token_data.user_id}, company_id={token_data.company_id}")
        else:
            logger.warning(f"Токен невалиден или истёк для {path}")
        
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
    ) -> Optional[TokenData]:
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
    
    async def _get_user(self, container, token_data: TokenData) -> Optional[User]:
        """Получает пользователя по данным токена"""
        user = await container.user_repository.get(token_data.user_id)
        if user:
            logger.debug(f"Пользователь найден: {token_data.user_id}")
        return user
    
    async def _sync_active_company(self, container, user: User, company):
        """Синхронизирует активную компанию пользователя"""
        if user.active_company_id != company.company_id:
            logger.info(f"Смена активной компании: {user.active_company_id} -> {company.company_id}")
            user.active_company_id = company.company_id
            await container.user_repository.set(user)

