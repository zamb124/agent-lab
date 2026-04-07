"""
Узкие точки входа к сервисам платформы для inline-кода и платформенных тулов.

Контейнер целиком в namespace не передаётся: только явно перечисленные сервисы.
Каждая функция возвращает минимально необходимый объект, не контейнер.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.flows.src.services.operator_handoff_service import OperatorHandoffService
    from apps.flows.src.services.schedule_service import ScheduleService
    from core.integrations.oauth_service import OAuthService


def get_operator_handoff_service() -> "OperatorHandoffService":
    from apps.flows.src.container import get_container

    return get_container().operator_handoff_service


def get_schedule_service() -> "ScheduleService":
    from apps.flows.src.container import get_container

    return get_container().schedule_service


def get_oauth_service() -> "OAuthService":
    from apps.flows.src.container import get_container

    return get_container().oauth_service


async def get_file_bytes(file_id: str) -> bytes:
    """Скачивает содержимое файла по ID из хранилища платформы (FileRepository + S3)."""
    from apps.flows.src.container import get_container
    from core.files import S3ClientFactory

    container = get_container()
    record = await container.file_repository.get(file_id)
    if record is None:
        raise ValueError(f"Файл {file_id} не найден в хранилище")
    s3 = S3ClientFactory.create_client_for_bucket(record.s3_bucket)
    return await s3.download_bytes(record.s3_key)
