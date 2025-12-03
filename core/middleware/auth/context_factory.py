"""
Фабрика для создания Context.
"""

import logging
from typing import Optional, List
from fastapi import Request

from core.models.context_models import Context
from core.models.identity_models import User, Company, UserStatus, AuthProvider
from core.models.i18n_models import Language
from core.utils.tokens import TokenData

logger = logging.getLogger(__name__)


class ContextFactory:
    """Единая фабрика для создания Context"""
    
    def __init__(self, container):
        self.container = container
    
    async def create(
        self,
        request: Request,
        context_type: str,
        company: Optional[Company],
        user: Optional[User] = None,
        token_data: Optional[TokenData] = None,
        platform: Optional[str] = None,
        auth_token: Optional[str] = None,
    ) -> Context:
        """
        Создает Context для запроса.
        
        Args:
            request: FastAPI Request
            context_type: Тип контекста (frontend, api, webhook, anonymous)
            company: Компания (может быть None для select-company)
            user: Пользователь (None для anonymous)
            token_data: Данные токена
            platform: Платформа (telegram, whatsapp)
            auth_token: JWT токен для межсервисной авторизации
        """
        language = self._detect_language(request)
        host = request.headers.get("host", "")
        
        # Если анонимный контекст, но пользователь есть - используем его
        if context_type == "anonymous" and not user:
            return self._create_anonymous_context(request, company, language)
        
        user_companies = await self._get_user_companies(user) if user else []
        
        metadata = {
            "context_type": context_type,
            "authenticated": user is not None,
        }
        
        if platform:
            metadata["platform"] = platform
        
        return Context(
            user=user,
            host=host,
            session_id=token_data.session_id if token_data else None,
            platform=platform or context_type,
            active_company=company,
            user_companies=user_companies,
            language=language,
            metadata=metadata,
            auth_token=auth_token,
        )
    
    def _create_anonymous_context(
        self,
        request: Request,
        company: Optional[Company],
        language: Language,
    ) -> Context:
        """Создает анонимный контекст"""
        company_id = company.company_id if company else "system"
        
        anonymous_user = User(
            user_id="anonymous",
            provider=AuthProvider.YANDEX,
            provider_user_id="anonymous",
            email="",
            name="Anonymous",
            status=UserStatus.ACTIVE,
            groups=["guest"],
            companies={company_id: ["guest"]},
            active_company_id=company_id,
        )
        
        return Context(
            user=anonymous_user,
            host=request.headers.get("host", ""),
            platform="anonymous",
            active_company=company,
            user_companies=[company] if company else [],
            language=language,
            metadata={"anonymous": True},
        )
    
    async def _get_user_companies(self, user: User) -> List[Company]:
        """Получает все компании пользователя"""
        company_repo = self.container.company_repository
        companies = []
        for company_id in user.companies.keys():
            company = await company_repo.get(company_id)
            if company:
                companies.append(company)
        return companies
    
    def _detect_language(self, request: Request) -> Language:
        """Определяет язык пользователя"""
        # 1. HTMX Accept-Language header (highest priority)
        htmx_lang = (request.headers.get('Accept-Language') or '').lower()
        if htmx_lang:
            for lang in Language:
                if lang.value == htmx_lang:
                    return lang
        
        # 2. Cookie language
        language_cookie = (request.cookies.get('language') or '').lower()
        if language_cookie:
            for lang in Language:
                if lang.value == language_cookie:
                    return lang
        
        # 3. Browser Accept-Language header
        accept_lang = (request.headers.get('accept-language') or '').lower()
        if accept_lang:
            languages = [l.split(';')[0].split('-')[0].strip() for l in accept_lang.split(',')]
            for browser_lang in languages:
                for lang in Language:
                    if lang.value == browser_lang:
                        return lang
        
        return Language.RU

