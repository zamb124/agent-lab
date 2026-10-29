"""
Оркестрация инициализации компаний через idle_worker.

Контракт
--------
- Новая компания: `apps/frontend/api/companies.py::create_company` создаёт
  `Company` в БД и сразу отвечает владельцу. Дальше — `company_init_new_company`
  (flows init + дефолтный sync-канал) с `Company.metadata.initialization_status`.
- System bootstrap: при старте `idle_worker` ставится `company_init_system` —
  только `POST /flows/api/v1/internal/company/init` для `company_id=system`
  (без sync-канала). Тяжёлый init в HTTP-процессе flows запрещён.

Статусы новой компании:
- `pending`     — задача зашедулена, ещё не отработала.
- `in_progress` — задача начала работу.
- `completed`   — оба под-шага успешны.
- `failed`      — после исчерпания retry; `initialization_error` для UI-баннера.
"""

from __future__ import annotations

from apps.idle.di import Di
from apps.idle.tasks.task_names import (
    TASK_INIT_NEW_COMPANY,
    TASK_INIT_SYSTEM_COMPANY,
)
from core.clients.service_client import ServiceClientError
from core.internal_context_headers import build_internal_context_headers
from core.logging import get_logger
from core.models.identity_models import Company
from core.tasks import platform_task
from core.types import JsonObject, require_json_object

logger = get_logger(__name__)

_DEFAULT_NAMESPACE_FOR_NEW_COMPANY = "default"
_SYSTEM_COMPANY_ID = "system"
_SYSTEM_COMPANY_NAME = "System"
_SYSTEM_COMPANY_SUBDOMAIN = "system"
_SYSTEM_USER_ID = "system"


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
    company = await Company.get(company_id)
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
    _ = await Company.set(company)


@platform_task(TASK_INIT_NEW_COMPANY)
async def initialize_new_company_task(
    company_id: str,
    company_name: str,
    subdomain: str,
    owner_user_id: str,
    *,
    di: Di,
) -> JsonObject:
    """
    Инициализирует только что созданную компанию.

    Шаги:
    1. flows: `/flows/api/v1/internal/company/init` — заводит дефолтных агентов / тулы.
    2. crm: `/crm/api/v1/internal/company/init` — системные типы, шаблоны, personal namespace.
    3. sync: `/sync/api/v1/channels/` — создаёт дефолтный topic-канал.
    4. stock: `/stock/api/v1/internal/company/init` — виртуальные локации и ЕИ.

    Каждая ошибка peer-сервиса пробрасывается → TaskIQ retry. После исчерпания
    retry — задача падает, `Company.metadata.initialization_status` = "failed".
    """
    service_client = di.service_client

    await _set_company_initialization_status(company_id=company_id, status="in_progress")

    try:
        flows_response = await service_client.post(
            "flows",
            "/flows/api/v1/internal/company/init",
            json={
                "company_id": company_id,
                "company_name": company_name,
                "subdomain": subdomain,
            },
            headers=build_internal_context_headers(
                company_id=company_id,
                user_id=owner_user_id,
            ),
        )
        flows_init_payload = require_json_object(
            flows_response, "flows /flows/api/v1/company/init response"
        )
        logger.info(
            "company_init.flows_init_done",
            company_id=company_id,
            flows_task_id=flows_init_payload.get("task_id"),
        )

        crm_response = await service_client.post(
            "crm",
            "/crm/api/v1/internal/company/init",
            json={"company_id": company_id},
            headers=build_internal_context_headers(
                company_id=company_id,
                user_id=owner_user_id,
            ),
        )
        crm_init_payload = require_json_object(
            crm_response, "crm /crm/api/v1/internal/company/init response"
        )
        logger.info(
            "company_init.crm_init_done",
            company_id=company_id,
            result=crm_init_payload.get("result"),
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
            headers=build_internal_context_headers(
                company_id=company_id,
                user_id=owner_user_id,
            ),
        )
        channel_payload = require_json_object(
            channel_response, "sync /sync/api/v1/channels/ response"
        )
        logger.info(
            "company_init.default_channel_created",
            company_id=company_id,
            channel_id=channel_payload.get("id"),
        )

        stock_response = await service_client.post(
            "stock",
            "/stock/api/v1/internal/company/init",
            json={"company_id": company_id},
            headers=build_internal_context_headers(
                company_id=company_id,
                user_id=owner_user_id,
            ),
        )
        stock_init_payload = require_json_object(
            stock_response, "stock /stock/api/v1/internal/company/init response"
        )
        logger.info(
            "company_init.stock_init_done",
            company_id=company_id,
            result=stock_init_payload.get("result"),
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

    await _set_company_initialization_status(company_id=company_id, status="completed")
    logger.info("company_init.completed", company_id=company_id)
    return {
        "company_id": company_id,
        "initialization_status": "completed",
    }


@platform_task(TASK_INIT_SYSTEM_COMPANY)
async def initialize_system_company_task(*, di: Di) -> JsonObject:
    """
    Bootstrap компании system: tools/flows/MCP через flows_worker.

    Вызывается из `idle_worker_startup` (enqueue only). Sync-канал не создаётся.
    """
    service_client = di.service_client

    try:
        flows_response = await service_client.post(
            "flows",
            "/flows/api/v1/internal/company/init",
            json={
                "company_id": _SYSTEM_COMPANY_ID,
                "company_name": _SYSTEM_COMPANY_NAME,
                "subdomain": _SYSTEM_COMPANY_SUBDOMAIN,
            },
            headers=build_internal_context_headers(
                company_id=_SYSTEM_COMPANY_ID,
                user_id=_SYSTEM_USER_ID,
            ),
        )
    except ServiceClientError as service_error:
        logger.error(
            "company_init.system_failed",
            company_id=_SYSTEM_COMPANY_ID,
            error_message=str(service_error),
            exc_info=True,
        )
        raise

    flows_init_payload = require_json_object(
        flows_response, "flows /flows/api/v1/internal/company/init response"
    )
    logger.info(
        "company_init.system_done",
        company_id=_SYSTEM_COMPANY_ID,
        flows_task_id=flows_init_payload.get("task_id"),
    )
    return {
        "company_id": _SYSTEM_COMPANY_ID,
        "flows_task_id": flows_init_payload.get("task_id"),
        "initialization_status": "enqueued",
    }
