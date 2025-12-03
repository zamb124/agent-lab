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
        
        Приоритет:
        1. X-Company-Id header (для service API в local env)
        2. Токен (для API запросов)
        3. Субдомен (для frontend)
        4. Системная компания (для anonymous)
        """
        company_repo = self.container.company_repository
        subdomain_repo = self.container.subdomain_repository
        host = request.headers.get("host", "")
        
        # 1. X-Company-Id header (только для local env)
        if settings.server.env == "local":
            override_company_id = request.headers.get("X-Company-Id")
            if override_company_id:
                company = await company_repo.get(override_company_id)
                if company:
                    logger.debug(f"Компания из X-Company-Id: {override_company_id}")
                    return company
                logger.warning(f"Компания {override_company_id} из X-Company-Id не найдена")
        
        # 2. Токен (для API запросов)
        if context_type == "api" and token_data and token_data.company_id:
            company = await company_repo.get(token_data.company_id)
            if company:
                logger.debug(f"Компания из токена: {token_data.company_id}")
                return company
            raise HTTPException(status_code=403, detail=f"Company {token_data.company_id} not found")
        
        # 3. Субдомен
        subdomain = self._extract_subdomain(host)
        if subdomain:
            company_id = await subdomain_repo.get_company_id(subdomain)
            if company_id:
                company = await company_repo.get(company_id)
                if company:
                    logger.debug(f"Компания из субдомена {subdomain}: {company_id}")
                    return company
            raise HTTPException(status_code=404, detail=f"Company not found for subdomain: {subdomain}")
        
        # 4. Системная компания (для anonymous)
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


