"""
Middleware для создания глобального контекста запроса
"""
import logging
import json
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from ..core.context import set_context, clear_context
from ..core.models import Context
from ..core.config import settings
from ..identity.models import User, AuthProvider
from ..identity.auth_service import auth_service

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware для создания RequestContext с пользователем"""
    
    async def dispatch(self, request: Request, call_next):
        # Пропускаем middleware для статики и служебных путей
        if (request.url.path.startswith("/static/") or 
            request.url.path.startswith("/.well-known/") or
            request.url.path.startswith("/favicon.ico")):
            return await call_next(request)
        
        try:
            # Создаем контекст на основе типа запроса
            context = await self._create_request_context(request)
            
            # Устанавливаем глобальный контекст
            set_context(context)
            
            # Также сохраняем в request.state для совместимости
            request.state.context = context
            request.state.user = context.user
            
            # Продолжаем обработку
            response = await call_next(request)
            return response
            
        except HTTPException as e:
            # Для HTML запросов редиректим на авторизацию
            accept_header = request.headers.get("accept", "")
            if e.status_code == 401 and "text/html" in accept_header:
                from fastapi.responses import RedirectResponse
                return RedirectResponse(url="/frontend/auth", status_code=302)
            
            # Для AJAX/JSON запросов возвращаем JSON
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=e.status_code,
                content={"detail": e.detail}
            )
        finally:
            # Очищаем контекст после обработки
            clear_context()
    
    async def _create_request_context(self, request: Request) -> Context:
        """Создает контекст на основе типа запроса"""
        
        path = request.url.path
        logger.info(f"🔍 Обрабатываем путь: {path}")
        
        # Определяем платформу по URL
        if "/webhook/telegram/" in path:
            logger.info("📱 Telegram контекст")
            return await self._create_telegram_context(request)
        elif "/api/v1/" in path:
            logger.info("🔌 API контекст")
            return await self._create_api_context(request)
        elif path == "/frontend/auth":
            logger.info("🔐 Страница авторизации - публичная")
            return await self._create_anonymous_context(request)
        elif path.startswith("/frontend/"):
            logger.info("🖥️ Frontend контекст - требует авторизации")
            return await self._create_frontend_context(request)
        elif path.startswith("/auth/"):
            logger.info("🔐 OAuth контекст")
            return await self._create_anonymous_context(request)
        else:
            logger.warning(f"❌ Неизвестный путь: {path}")
            raise HTTPException(status_code=404, detail="Not Found")
    
    async def _create_telegram_context(self, request: Request) -> Context:
        """Создает контекст для Telegram запросов"""
        try:
            body = await request.body()
            data = json.loads(body)
            
            # Извлекаем данные Telegram пользователя
            tg_user = data.get("message", {}).get("from", {})
            telegram_user_id = str(tg_user.get("id", "unknown"))
            username = tg_user.get("username", "")
            first_name = tg_user.get("first_name", "")
            last_name = tg_user.get("last_name", "")
            
            # Формируем полное имя
            full_name = f"{first_name} {last_name}".strip() or username or f"User_{telegram_user_id}"
            
            # Создаем реального Telegram пользователя
            from app.identity.models import UserStatus
            user = User(
                user_id=f"telegram_{telegram_user_id}",
                provider=AuthProvider.YANDEX,  # Placeholder
                provider_user_id=telegram_user_id,
                email="",  # У Telegram нет email
                name=full_name,
                status=UserStatus.ACTIVE,
                groups=["user"]
            )
            
            return Context(
                user=user,
                platform="telegram",
                metadata={
                    "telegram_user_id": telegram_user_id,
                    "username": username,
                    "first_name": first_name,
                    "last_name": last_name
                }
            )
            
        except Exception as e:
            logger.warning(f"Ошибка парсинга Telegram запроса: {e}")
            return await self._create_anonymous_context(request)
    
    async def _create_api_context(self, request: Request) -> Context:
        """Создает контекст для API запросов"""
        
        # Проверяем включена ли авторизация
        if not settings.auth.enabled:
            # Авторизация отключена - создаем анонимного пользователя
            return await self._create_anonymous_context(request)
        
        # TODO: Реализовать полную авторизацию через токены
        # Пока создаем анонимного пользователя
        return await self._create_anonymous_context(request)
    
    async def _create_anonymous_context(self, request: Request) -> Context:
        """Создает анонимный контекст"""
        from app.identity.models import UserStatus
        user = User(
            user_id="anonymous",
            provider=AuthProvider.YANDEX,  # Placeholder
            provider_user_id="anonymous",
            email="",
            name="Anonymous",
            status=UserStatus.ACTIVE,
            groups=["guest"]
        )
        
        return Context(
            user=user,
            platform="api",
            metadata={"anonymous": True}
        )
    
    
    async def _create_frontend_context(self, request: Request) -> Context:
        """Создает контекст для frontend запросов на основе куки"""
        # Получаем session_id из куки
        session_id = request.cookies.get("session_id")
        
        if not session_id:
            raise HTTPException(status_code=401, detail="Unauthorized")
        
        # Пытаемся найти пользователя по сессии
        from app.identity.auth_service import AuthService
        auth_service = AuthService()
        
        user = await auth_service.get_user_by_session(session_id)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid session")
        
        return Context(
            user=user,
            session_id=session_id,
            platform="frontend",
            metadata={"authenticated": True}
        )
