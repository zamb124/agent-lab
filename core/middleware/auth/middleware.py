"""
Компактный AuthMiddleware с декларативной конфигурацией.
"""

import logging
from typing import Optional
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from core.context import set_context, clear_context
from core.models.identity_models import User
from core.utils.tokens import get_token_service, TokenData

from .route_config import RouteMatcher, RouteRule
from .company_resolver import CompanyResolver
from .context_factory import ContextFactory
from .platform_handlers import get_platform_handler

logger = logging.getLogger(__name__)


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
    
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        if self.route_matcher.should_skip(path):
            return await call_next(request)
        
        container = self._get_container(request)
        company_resolver = CompanyResolver(container)
        context_factory = ContextFactory(container)
        
        rule = self.route_matcher.match(path)
        if not rule:
            logger.warning(f"Неизвестный путь: {path}")
            raise HTTPException(status_code=404, detail="Not Found")
        
        try:
            context = await self._create_context(
                request, rule, container, company_resolver, context_factory
            )
            
            set_context(context)
            request.state.context = context
            request.state.user = context.user
            request.state.language = context.language.value
            request.state.user_companies = context.user_companies
            
            response = await call_next(request)
            return response
            
        except CompanyCreationRequired:
            return RedirectResponse(url="/frontend/select-company", status_code=307)
        except HTTPException as e:
            accept = request.headers.get("accept", "")
            if e.status_code == 401 and "text/html" in accept:
                return RedirectResponse(url="/frontend/auth", status_code=302)
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
    ):
        """Создает контекст на основе правила маршрутизации"""
        
        # Webhook обработка
        if rule.context_type == "webhook" and rule.platform:
            return await self._handle_webhook(request, rule, container, context_factory)
        
        # Анонимный контекст (но пробуем загрузить пользователя если токен есть)
        if rule.context_type == "anonymous":
            company = await company_resolver.resolve(request, context_type="anonymous")
            token_data, auth_token = self._extract_token(request)
            user = await self._get_user(container, token_data) if token_data else None
            return await context_factory.create(
                request, "anonymous", company, user, token_data, auth_token=auth_token
            )
        
        # Авторизованный контекст
        token_data, auth_token = self._extract_token(request)
        
        if rule.auth_required and not token_data:
            raise HTTPException(status_code=401, detail="Unauthorized")
        
        user = await self._get_user(container, token_data) if token_data else None
        
        if rule.auth_required and not user:
            raise HTTPException(status_code=401, detail="User not found")
        
        company = await company_resolver.resolve(request, token_data, rule.context_type)
        
        # Frontend без субдомена -> редирект на выбор компании
        if rule.context_type == "frontend" and not company:
            if not self.route_matcher.allows_no_subdomain(request.url.path):
                raise CompanyCreationRequired()
        
        # Проверка доступа к удаляемой компании
        if company and company.status == "deleting":
            if not self.route_matcher.allows_deleting_company(request.url.path):
                raise HTTPException(
                    status_code=403,
                    detail="Компания удаляется. Пожалуйста, выберите другую компанию."
                )
        
        # Проверка доступа пользователя к компании
        if user and company and rule.context_type == "frontend":
            if company.company_id not in user.companies:
                if not self.route_matcher.allows_no_subdomain(request.url.path):
                    raise CompanyCreationRequired()
            else:
                await self._sync_active_company(container, user, company)
        
        return await context_factory.create(
            request, rule.context_type, company, user, token_data, rule.platform, auth_token
        )
    
    async def _handle_webhook(
        self,
        request: Request,
        rule: RouteRule,
        container,
        context_factory: ContextFactory,
    ):
        """Обрабатывает webhook запросы"""
        handler = get_platform_handler(rule.platform, container)
        if not handler:
            raise HTTPException(status_code=400, detail=f"Unknown platform: {rule.platform}")
        
        company = await handler.extract_company_from_webhook_path(request.url.path, rule.platform)
        
        # GET для WhatsApp верификации - анонимный контекст
        if rule.platform == "whatsapp" and request.method == "GET":
            return await context_factory.create(request, "anonymous", company)
        
        user, metadata = await handler.create_user_from_request(request, company)
        
        context = await context_factory.create(
            request, "webhook", company, user, platform=rule.platform
        )
        context.metadata.update(metadata)
        
        logger.info(f"{rule.platform.title()} webhook: компания {company.company_id}")
        return context
    
    def _extract_token(self, request: Request) -> tuple[Optional[TokenData], Optional[str]]:
        """
        Извлекает и валидирует токен из запроса.
        
        Returns:
            tuple: (token_data, raw_token) - данные токена и сам токен для межсервисных запросов
        """
        token = request.cookies.get("auth_token")
        
        if not token:
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
        
        if not token:
            return None, None
        
        token_service = get_token_service()
        token_data = token_service.validate_token(token)
        return token_data, token if token_data else None
    
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

