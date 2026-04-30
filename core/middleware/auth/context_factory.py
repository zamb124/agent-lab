"""
Фабрика для создания Context.
"""

from core.logging import get_logger
from typing import Optional, List

from fastapi import HTTPException, Request

from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.identity_models import User, Company, UserStatus, AuthProvider
from core.models.i18n_models import Language
from core.utils.tokens import TokenData

logger = get_logger(__name__)
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
        trace_id: Optional[str] = None,
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
            trace_id: ID трассировки для межсервисного взаимодействия
        """
        language = self._detect_language(request)
        host = request.headers.get("host", "")
        
        # Если анонимный контекст, но пользователь есть - используем его
        if context_type == "anonymous" and not user:
            return await self._create_anonymous_context(request, company, language, trace_id)

        if context_type == "api" and user is None and token_data is not None:
            active_cid = ""
            if company is not None:
                active_cid = company.company_id
            elif token_data.company_id:
                active_cid = token_data.company_id
            raw_name = token_data.user_id
            display_name = raw_name if len(raw_name) <= 200 else raw_name[:200]
            user = User(
                user_id=token_data.user_id,
                name=display_name,
                status=UserStatus.ACTIVE,
                groups=["guest"],
                companies={active_cid: ["guest"]} if active_cid else {},
                active_company_id=active_cid,
            )
        
        user_companies = await self._get_user_companies(user) if user else []
        
        metadata = {
            "context_type": context_type,
            "authenticated": user is not None,
        }
        
        if platform:
            metadata["platform"] = platform

        active_namespace = await self._resolve_active_namespace(
            request, company, user, user_companies, language, host, metadata, token_data,
            auth_token, trace_id, platform, context_type,
        )

        return Context(
            user=user,
            host=host,
            session_id=token_data.session_id if token_data else None,
            channel=platform or context_type,
            active_company=company,
            user_companies=user_companies,
            active_namespace=active_namespace,
            language=language,
            metadata=metadata,
            auth_token=auth_token,
            trace_id=trace_id,
            container=self.container,
        )
    
    async def _create_anonymous_context(
        self,
        request: Request,
        company: Optional[Company],
        language: Language,
        trace_id: Optional[str] = None,
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
        
        active_namespace = await self._resolve_active_namespace(
            request,
            company,
            anonymous_user,
            [company] if company else [],
            language,
            request.headers.get("host", ""),
            {"anonymous": True},
            None,
            None,
            trace_id,
            None,
            "anonymous",
        )

        return Context(
            user=anonymous_user,
            host=request.headers.get("host", ""),
            channel="anonymous",
            active_company=company,
            user_companies=[company] if company else [],
            active_namespace=active_namespace,
            language=language,
            metadata={"anonymous": True},
            trace_id=trace_id,
            container=self.container,
        )

    async def _resolve_active_namespace(
        self,
        request: Request,
        company: Optional[Company],
        user: Optional[User],
        user_companies: List[Company],
        language: Language,
        host: str,
        metadata: dict,
        token_data: Optional[TokenData],
        auth_token: Optional[str],
        trace_id: Optional[str],
        platform: Optional[str],
        context_type: str,
    ) -> str:
        if not company or not user:
            return "default"
        raw = (request.headers.get("X-Platform-Namespace") or "").strip()
        if not raw or raw == "default":
            return "default"

        preliminary = Context(
            user=user,
            host=host,
            session_id=token_data.session_id if token_data else None,
            channel=platform or context_type,
            active_company=company,
            user_companies=user_companies,
            active_namespace="default",
            language=language,
            metadata=metadata,
            auth_token=auth_token,
            trace_id=trace_id,
            container=self.container,
        )
        set_context(preliminary)
        try:
            ns = await self.container.namespace_repository.get(raw)
        finally:
            clear_context()

        if ns is None:
            raise HTTPException(
                status_code=400,
                detail=f"Namespace «{raw}» не найден",
            )
        if ns.company_id != company.company_id:
            raise HTTPException(
                status_code=403,
                detail="Namespace не принадлежит активной компании",
            )
        return ns.name

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
        
        return Language.EN

