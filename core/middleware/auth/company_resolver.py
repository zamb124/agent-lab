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

    def __init__(self, container) -> None:
        self.container = container

    async def resolve(
        self,
        request: Request,
        token_data: Optional[TokenData] = None,
        context_type: str = "frontend",
    ) -> Optional[Company]:
        """
        Субдомен Host кодирует тенант: для всех не-anonymous контекстов компания субдомена
        имеет приоритет над JWT / X-Company-Id, с проверкой membership.

        Публичные anonymous-роуты: компания с субдомена по возможности, без membership.
        """
        if context_type == "anonymous":
            return await self._resolve_anonymous(request)
        return await self._resolve_tenant(request, token_data, context_type)

    async def _resolve_anonymous(self, request: Request) -> Optional[Company]:
        company_repo = self.container.company_repository
        subdomain_repo = self.container.subdomain_repository
        host = request.headers.get("host", "")

        override_company_id = request.headers.get("X-Company-Id")
        if override_company_id:
            if settings.server.env != "production":
                company = await company_repo.get(override_company_id)
                if company:
                    logger.debug("Anonymous: компания из X-Company-Id (dev)")
                    return company
                logger.warning("Anonymous: X-Company-Id указывает на несуществующую компанию")

        subdomain = self._extract_subdomain(host)
        if not subdomain:
            logger.debug("Anonymous: нет субдомена в Host")
            return None

        company_id = await subdomain_repo.get_company_id(subdomain)
        if not company_id:
            logger.debug(
                "Anonymous: субдомен в Host без записи в subdomain_repo — контекст без компании"
            )
            return None

        company = await company_repo.get(company_id)
        if company:
            logger.debug(f"Anonymous: компания из субдомена {subdomain}")
            return company
        logger.debug("Anonymous: company_id в реестре, запись company не найдена")
        return None

    async def _assert_subdomain_tenant(
        self,
        request: Request,
        company_id: str,
        subdomain: str,
        token_data: Optional[TokenData],
    ) -> None:
        if not token_data or not token_data.user_id:
            return
        user = await self.container.user_repository.get(token_data.user_id)
        if not user:
            return
        if company_id in user.companies:
            return
        if request.method == "POST" and request.url.path in _INVITE_ACCEPT_PATHS:
            logger.info(
                f"Принятие инвайта: {token_data.user_id} ещё не участник {company_id}, "
                f"проверку membership пропускаем (path={request.url.path})"
            )
            return
        logger.warning(
            f"Пользователь {token_data.user_id} не имеет доступа к компании {company_id} (субдомен: {subdomain})"
        )
        raise HTTPException(
            status_code=403,
            detail=f"У вас нет доступа к компании {subdomain}",
        )

    def _x_company_id_must_match_tenant(
        self, request: Request, tenant_company_id: str
    ) -> None:
        override = request.headers.get("X-Company-Id")
        if not override:
            return
        if override != tenant_company_id:
            logger.warning(
                f"X-Company-Id ({override}) не совпадает с компанией субдомена ({tenant_company_id})"
            )
            raise HTTPException(
                status_code=403,
                detail="X-Company-Id не соответствует хосту субдомена",
            )

    async def _resolve_tenant(
        self,
        request: Request,
        token_data: Optional[TokenData],
        context_type: str,
    ) -> Optional[Company]:
        company_repo = self.container.company_repository
        subdomain_repo = self.container.subdomain_repository
        host = request.headers.get("host", "")
        subdomain = self._extract_subdomain(host)

        if subdomain:
            company_id = await subdomain_repo.get_company_id(subdomain)
            if not company_id:
                raise HTTPException(
                    status_code=404,
                    detail=f"Company not found for subdomain: {subdomain}",
                )
            self._x_company_id_must_match_tenant(request, company_id)
            await self._assert_subdomain_tenant(
                request, company_id, subdomain, token_data
            )
            company = await company_repo.get(company_id)
            if company:
                logger.debug(f"Компания из субдомена {subdomain}: {company_id}")
                return company
            raise HTTPException(
                status_code=404, detail=f"Company not found for subdomain: {subdomain}"
            )

        if context_type == "frontend":
            logger.info(f"Тенант frontend без субдомена (host={host}) -> None")
            return None

        override_company_id = request.headers.get("X-Company-Id")
        if override_company_id:
            if settings.server.env != "production":
                company = await company_repo.get(override_company_id)
                if company:
                    logger.debug(f"Компания из X-Company-Id (dev): {override_company_id}")
                    return company
                logger.warning(f"Компания {override_company_id} из X-Company-Id не найдена")

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
                        detail=f"У вас нет доступа к компании {override_company_id}",
                    )

                company = await company_repo.get(override_company_id)
                if company:
                    logger.debug(f"Компания из X-Company-Id: {override_company_id}")
                    return company
                logger.warning(f"Компания {override_company_id} из X-Company-Id не найдена")

        if token_data and token_data.company_id:
            company = await company_repo.get(token_data.company_id)
            if company:
                logger.debug(f"Компания из токена: {token_data.company_id}")
                return company
            raise HTTPException(
                status_code=403, detail=f"Company {token_data.company_id} not found"
            )

        return None

    def _extract_subdomain(self, host: str) -> Optional[str]:
        return extract_subdomain(host)

    def has_subdomain(self, request: Request) -> bool:
        host = request.headers.get("host", "")
        if request.headers.get("X-Company-Id"):
            return True
        return extract_subdomain(host) is not None
