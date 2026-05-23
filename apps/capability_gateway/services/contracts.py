"""Protocol-типы сервисов capability-gateway."""

from __future__ import annotations

from typing import Protocol

from core.clients.redis_client import RedisClient
from core.clients.service_client import ServiceClient
from core.db.repositories.company_repository import CompanyRepository
from core.db.repositories.user_repository import UserRepository
from core.files.file_repository import FileRepository
from core.files.processors import FileProcessor


class CapabilityGatewayContainerProtocol(Protocol):
    """Минимальный контейнерный контракт для services слоя."""

    @property
    def file_repository(self) -> FileRepository: ...

    @property
    def file_processor(self) -> FileProcessor: ...

    @property
    def user_repository(self) -> UserRepository: ...

    @property
    def company_repository(self) -> CompanyRepository: ...

    @property
    def service_client(self) -> ServiceClient: ...

    @property
    def redis_client(self) -> RedisClient: ...
