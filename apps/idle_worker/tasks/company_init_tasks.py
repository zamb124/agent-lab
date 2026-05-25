"""
Инициализация новой компании после её создания.

Контракт
--------
- `apps/frontend/api/companies.py::create_company` создаёт `Company` в БД и
  публикует HTTP-ответ владельцу немедленно (UX: не блокировать создание
  компании на доступности `flows`/`sync`).
- Дальнейшая инициализация (агенты, дефолтный канал sync) запускается через
  эту TaskIQ-задачу с retry и явным `Company.metadata.initialization_status`.

Раньше прямо в HTTP-хендлере стояли `try: ... except Exception: logger.error(...)
# НЕ падаем` — каскадные сбои в `flows`/`sync` оставляли компанию без агентов
и без канала, без какого-либо следа в данных. UI считал компанию готовой,
владелец видел пустой dashboard. Теперь:

- `initialization_status` = "pending"     — задача зашедулена, ещё не отработала.
- `initialization_status` = "in_progress" — задача начала выполнение.
- `initialization_status` = "completed"   — оба под-шага успешны.
- `initialization_status` = "failed"      — после исчерпания retry хотя бы
  один под-шаг не прошёл; `initialization_error` содержит структурированный
  details, UI обязан показать баннер.

Сам ответ HTTP-хендлера остаётся быстрым, но костыля «тихо ничего не
сделать» больше нет.
"""

from __future__ import annotations

from apps.idle_worker.broker import broker as idle_broker
from apps.idle_worker.container import get_container
from core.clients.service_client import ServiceClientError
from core.logging import get_logger
from core.types import JsonObject, require_json_object

logger = get_logger(__name__)

TASK_INIT_NEW_COMPANY = "company_init_new_company"

_DEFAULT_NAMESPACE_FOR_NEW_COMPANY = "default"


async def _set_company_initialization_status(
    *,
    company_id: str,
    status: str,
    error_details: JsonObject | None = None,
) -> None:
    """
    Атомарно обновляет `Company.metadata.initialization_status` (+ `_error`).

    Если компания исчезла к моменту записи — это нормально (удалена владельцем
    параллельно), просто логируем warning без raise: цель статуса —
    диагностика, не data correctness.
    """
    container = get_container()
    company = await container.company_repository.get(company_id)
    if company is None:
        logger.warning(
            "company_init.status_write_skipped",
            company_id=company_id,
            requested_status=status,
            reason="company_not_found",
        )
        return
    metadata = dict(company.metadata)
    metadata["initialization_status"] = status
    if error_details is None:
        _ = metadata.pop("initialization_error", None)
    else:
        metadata["initialization_error"] = error_details
    company.metadata = metadata
    _ = await container.company_repository.set(company)


@idle_broker.task(
    task_name=TASK_INIT_NEW_COMPANY,
    queue_name="idle",
    retry_on_error=True,
    max_retries=3,
)
async def initialize_new_company_task(
    company_id: str,
    company_name: str,
    subdomain: str,
    owner_user_id: str,
) -> JsonObject:
    """
    Инициализирует только что созданную компанию.

    Шаги:
    1. flows: `/flows/api/v1/company/init` — заводит дефолтных агентов / тулы.
    2. sync: `/sync/api/v1/channels/` — создаёт дефолтный topic-канал.

    Каждая ошибка peer-сервиса пробрасывается → TaskIQ retry. После исчерпания
    retry — задача падает, `Company.metadata.initialization_status` = "failed".
    """
    container = get_container()
    service_client = container.service_client

    await _set_company_initialization_status(
        company_id=company_id, status="in_progress"
    )

    try:
        flows_response = await service_client.post(
            "flows",
            "/flows/api/v1/company/init",
            json={
                "company_id": company_id,
                "company_name": company_name,
                "subdomain": subdomain,
            },
        )
        flows_init_payload = require_json_object(
            flows_response, "flows /flows/api/v1/company/init response"
        )
        logger.info(
            "company_init.flows_init_done",
            company_id=company_id,
            flows_task_id=flows_init_payload.get("task_id"),
        )

        channel_response = await service_client.post(
            "sync",
            "/sync/api/v1/channels/",
            json={
                "namespace": _DEFAULT_NAMESPACE_FOR_NEW_COMPANY,
                "type": "topic",
                "name": company_name,
                "is_private": False,
            },
            headers={"X-Company-Id": company_id, "X-User-Id": owner_user_id},
        )
        channel_payload = require_json_object(
            channel_response, "sync /sync/api/v1/channels/ response"
        )
        logger.info(
            "company_init.default_channel_created",
            company_id=company_id,
            channel_id=channel_payload.get("id"),
        )
    except ServiceClientError as service_error:
        await _set_company_initialization_status(
            company_id=company_id,
            status="failed",
            error_details={
                "error_type": type(service_error).__name__,
                "error_message": str(service_error),
            },
        )
        logger.error(
            "company_init.failed",
            company_id=company_id,
            error_message=str(service_error),
            exc_info=True,
        )
        raise

    await _set_company_initialization_status(
        company_id=company_id, status="completed"
    )
    logger.info("company_init.completed", company_id=company_id)
    return {
        "company_id": company_id,
        "initialization_status": "completed",
    }
