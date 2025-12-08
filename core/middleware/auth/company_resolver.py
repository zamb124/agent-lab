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
        2. X-Company-Id header
        3. Токен
        
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
        
        # Для FRONTEND - субдомен имеет приоритет, но проверяем доступ
        if context_type == "frontend":
            subdomain = self._extract_subdomain(host)
            if subdomain:
                company_id = await subdomain_repo.get_company_id(subdomain)
                if not company_id:
                    raise HTTPException(status_code=404, detail=f"Company not found for subdomain: {subdomain}")
                
                # Проверяем что у пользователя есть доступ к этой компании
                if token_data and token_data.user_id:
                    user = await self.container.user_repository.get(token_data.user_id)
                    if user and company_id not in user.companies:
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
        
        # X-Company-Id header - переключение активной компании
        override_company_id = request.headers.get("X-Company-Id")
        if override_company_id:
            # В local env разрешаем без проверок
            if settings.server.env == "local":
                company = await company_repo.get(override_company_id)
                if company:
                    logger.debug(f"Компания из X-Company-Id (local): {override_company_id}")
                    return company
                logger.warning(f"Компания {override_company_id} из X-Company-Id не найдена")
            
            # На проде проверяем что у пользователя есть доступ
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
        
        # Системная компания (для anonymous)
        if context_type == "anonymous":
            return await self._get_system_company()
        
        # Нет субдомена для frontend - редирект на выбор компании
        return None
    
    def _extract_subdomain(self, host: str) -> Optional[str]:
        """Извлекает субдомен из Host header"""
        if settings.server.env == "local":
            if ".localhost" in host:
                return host.split(".")[0]
            return None
        return extract_subdomain(host)
    
    def has_subdomain(self, request: Request) -> bool:
        """Проверяет наличие субдомена в запросе"""
        host = request.headers.get("host", "")
        
        if settings.server.env == "local":
            has_override = request.headers.get("X-Company-Id") is not None
            has_subdomain = ".localhost" in host
            return has_subdomain or has_override
        
        return extract_subdomain(host) is not None
    
    async def _get_system_company(self) -> Company:
        """Возвращает системную компанию"""
        company = await self.container.company_repository.get("system")
        if not company:
            raise RuntimeError("Системная компания не найдена - запустите миграцию")
        return company


