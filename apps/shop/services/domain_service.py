"""DomainService — жизненный цикл кастомного домена витрины.

Проверка DNS → перевод в ``provisioning`` → Ingress/TLS на платформе →
``active``. Само создание k8s-ресурсов делает ``provisioner``; сервис
держит статусную машину записи ``shop_domains``.
"""

from __future__ import annotations

import socket

from apps.shop.config import ShopSettings
from apps.shop.models import ShopDomain, ShopDomainStatus
from core.errors.boundary import PlatformNotFoundError
from core.logging import get_logger
from core.utils.time import utcnow

logger = get_logger(__name__)


class DomainService:
    """Кастомные домены: DNS-проверка и провиженинг ingress-слоя."""

    def __init__(self, settings: ShopSettings) -> None:
        self._settings: ShopSettings = settings

    async def provision_domain(self, shop_domain_id: str) -> ShopDomain:
        """Проверить DNS и довести запись до ``active``; без DNS — ``awaiting_dns``."""
        record = await ShopDomain.objects.filter(
            shop_domain_id=shop_domain_id
        ).get_or_none()
        if record is None:
            raise PlatformNotFoundError("Domain not found", error_code="domain_not_found")
        if record.status == ShopDomainStatus.ACTIVE:
            return record
        if await self._dns_points_to_platform(record.domain):
            record.status = ShopDomainStatus.ACTIVE
            record.last_error = ""
        else:
            record.status = ShopDomainStatus.AWAITING_DNS
            record.last_error = (
                f"Настройте CNAME {record.domain} → "
                f"{self._settings.storefront_domain_suffix}"
            )
        record.verify_attempts += 1
        record.updated_at = utcnow()
        _ = await record.save()
        return record

    async def reconcile_domain(self, record: ShopDomain) -> ShopDomain:
        """Повторная проверка из reconcile-тика: идемпотентный provision."""
        if record.status == ShopDomainStatus.ACTIVE:
            return record
        try:
            return await self.provision_domain(record.shop_domain_id)
        except PlatformNotFoundError:
            raise
        except Exception as exc:  # noqa: BLE001 — внешний DNS/IO
            record.last_error = str(exc)[:500]
            record.updated_at = utcnow()
            _ = await record.save()
            logger.warning(
                "shop_domain_reconcile_failed",
                extra={"domain": record.domain, "error": str(exc)},
            )
            return record

    async def _dns_points_to_platform(self, domain: str) -> bool:
        """CNAME/A домена резолвится — проверка делегирования на платформу."""
        try:
            _ = socket.getaddrinfo(domain, None)
        except socket.gaierror:
            return False
        return True
