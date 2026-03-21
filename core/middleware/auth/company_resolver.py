"""
Определение компании из запроса.
"""

import logging
from typing import Optional
from fastapi import Request, HTTPException

from core.config import settings
from core.models.identity_models import Company
from core.utils.domain import extract_subdomain
from core.utils.tokens import TokenData

logger = logging.getLogger(__name__)

# POST принятия инвайта: пользователь намеренно ещё не в members этой компании
_INVITE_ACCEPT_PATHS = frozenset({
    "/api/invites/accept",
    "/frontend/api/invites/accept",
})


class CompanyResolver:
    """Определяет компанию из запроса"""
    
    def __init__(self, container):
        self.container = container
    
    async def resolve(
        self,
        request: Request,
        token_data: Optional[TokenData] = None,
        context_type: str = "frontend",
    ) -> Optional[Company]:
        """
        Определяет компанию для запроса.
        
        Приоритет для FRONTEND (ggg.humanitec.ru):
        1. Субдомен (пользователь явно зашел на этот домен)
        
        Приоритет для API (service-to-service):
        1. X-Company-Id header (сервис указывает компанию)
        2. Токен
        3. Субдомен
        
        X-Company-Id позволяет переключить активную компанию:
        - В local env - без проверок (для разработки)
        - На проде - только если у пользователя есть доступ к компании
        """
        company_repo = self.container.company_repository
        subdomain_repo = self.container.subdomain_repository
        host = request.headers.get("host", "")
        
        # Для FRONTEND - ТОЛЬКО субдомен! Токен игнорируется.
        if context_type == "frontend":
            subdomain = self._extract_subdomain(host)
            logger.info(f"🔍 CompanyResolver: context_type=frontend, host={host}, subdomain={subdomain}")
            if not subdomain:
                # Нет субдомена -> middleware сделает редирект на select-company
                logger.info(f"🚨 Frontend без субдомена (host={host}) -> возвращаю None")
                return None
            
            company_id = await subdomain_repo.get_company_id(subdomain)
            if not company_id:
                raise HTTPException(status_code=404, detail=f"Company not found for subdomain: {subdomain}")
            
            # Проверяем что у пользователя есть доступ к этой компании
            if token_data and token_data.user_id:
                user = await self.container.user_repository.get(token_data.user_id)
                if user and company_id not in user.companies:
                    path = request.url.path
                    if (
                        request.method == "POST"
                        and path in _INVITE_ACCEPT_PATHS
                    ):
                        logger.info(
                            f"Принятие инвайта: {token_data.user_id} ещё не участник {company_id}, "
                            f"проверку membership пропускаем (path={path})"
                        )
                    else:
                        logger.warning(
                            f"Пользователь {token_data.user_id} не имеет доступа к компании {company_id} (субдомен: {subdomain})"
                        )
                        raise HTTPException(
                            status_code=403,
                            detail=f"У вас нет доступа к компании {subdomain}"
                        )
            
            company = await company_repo.get(company_id)
            if company:
                logger.debug(f"Компания из субдомена {subdomain}: {company_id}")
                return company
            raise HTTPException(status_code=404, detail=f"Company not found for subdomain: {subdomain}")
        
        # === Ниже - только для НЕ-frontend контекстов (API, webhooks, anonymous) ===
        
        # X-Company-Id header - переключение активной компании
        override_company_id = request.headers.get("X-Company-Id")
        if override_company_id:
            # В dev/local разрешаем без проверок (для удобства разработки)
            # В production проверяем права доступа
            if settings.server.env != "production":
                company = await company_repo.get(override_company_id)
                if company:
                    logger.debug(f"Компания из X-Company-Id (dev): {override_company_id}")
                    return company
                logger.warning(f"Компания {override_company_id} из X-Company-Id не найдена")
            
            # Production: проверяем доступ пользователя
            elif token_data and token_data.user_id:
                user = await self.container.user_repository.get(token_data.user_id)
                if not user:
                    logger.warning(f"Пользователь {token_data.user_id} не найден")
                    raise HTTPException(status_code=403, detail="Пользователь не найден")
                
                if override_company_id not in user.companies:
                    logger.warning(
                        f"Пользователь {token_data.user_id} не имеет доступа к компании {override_company_id}"
                    )
                    raise HTTPException(
                        status_code=403, 
                        detail=f"У вас нет доступа к компании {override_company_id}"
                    )
                
                company = await company_repo.get(override_company_id)
                if company:
                    logger.debug(f"Компания из X-Company-Id: {override_company_id}")
                    return company
                logger.warning(f"Компания {override_company_id} из X-Company-Id не найдена")
        
        # Токен - fallback если X-Company-Id не указан
        if token_data and token_data.company_id:
            company = await company_repo.get(token_data.company_id)
            if company:
                logger.debug(f"Компания из токена: {token_data.company_id}")
                return company
            raise HTTPException(status_code=403, detail=f"Company {token_data.company_id} not found")
        
        # Субдомен для НЕ-frontend контекста
        subdomain = self._extract_subdomain(host)
        if subdomain:
            company_id = await subdomain_repo.get_company_id(subdomain)
            if company_id:
                company = await company_repo.get(company_id)
                if company:
                    logger.debug(f"Компания из субдомена {subdomain}: {company_id}")
                    return company
            raise HTTPException(status_code=404, detail=f"Company not found for subdomain: {subdomain}")
        
        # Для anonymous (публичные страницы) - компания не требуется
        if context_type == "anonymous":
            logger.debug("Anonymous контекст - компания не требуется, возвращаем None")
            return None
        
        # Нет субдомена для frontend - редирект на выбор компании
        return None
    
    def _extract_subdomain(self, host: str) -> Optional[str]:
        """Извлекает субдомен из Host header"""
        return extract_subdomain(host)
    
    def has_subdomain(self, request: Request) -> bool:
        """Проверяет наличие субдомена в запросе"""
        host = request.headers.get("host", "")
        
        # X-Company-Id считается как субдомен (для API и dev)
        if request.headers.get("X-Company-Id"):
            return True
        
        return extract_subdomain(host) is not None
