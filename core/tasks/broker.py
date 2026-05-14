"""
Фабрика для создания TaskIQ brokers с общими настройками.

Конкретные brokers создаются в:
- apps/flows_worker/broker.py - для задач сервиса flows
- apps/idle_worker/broker.py - для общеплатформенных idle-задач
- apps/rag_worker/broker.py - для RAG задач
- apps/sync/realtime/broker.py - для sync realtime задач
- apps/crm_worker/broker.py - для CRM задач
"""

from typing import Optional

from taskiq import TaskiqScheduler, TaskiqState
from taskiq.events import TaskiqEvents
from taskiq.middlewares.simple_retry_middleware import SimpleRetryMiddleware
from taskiq_redis import ListRedisScheduleSource, RedisAsyncResultBackend, RedisStreamBroker

try:
    import redis.asyncio as redis
    from redis.exceptions import ResponseError as RedisResponseError

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None
    RedisResponseError = None  # type: ignore[misc, assignment]

from core.config import get_settings
from core.logging import get_logger, setup_logging
from core.tasks.logging_middleware import build_logging_middleware
from core.tasks.session_lock import session_lock_middleware

logger = get_logger(__name__)


def create_broker(
    queue_name: Optional[str] = None,
    *,
    service_name: Optional[str] = None,
) -> RedisStreamBroker:
    """
    Создает TaskIQ broker с общими настройками.

    Args:
        queue_name: Имя очереди (Redis Stream). Если None, использует "taskiq" (default).
        service_name: Имя сервиса-инициатора (для service.name в логах задач).
            Если None — берётся из settings.server.name. Используется
            только в качестве дефолта; kiq() обязан передавать
            service_name явно через core.tasks.kicker.with_log_labels().

    Returns:
        Настроенный RedisStreamBroker с result_backend и middlewares
    """
    settings = get_settings()
    broker_url = settings.tasks.broker_url
    effective_queue = queue_name or "taskiq"
    effective_service = service_name or settings.server.name

    logger.info(
        "task.broker_created",
        queue=effective_queue,
        broker_url=broker_url,
        service=effective_service,
    )

    result_backend = RedisAsyncResultBackend(redis_url=broker_url, result_ex_time=3600)

    broker_kwargs = {"url": broker_url}
    if queue_name:
        broker_kwargs["queue_name"] = queue_name

    # Порядок middleware (TaskIQ receiver):
    # - pre_execute: по порядку регистрации — Logging → SessionLock → SimpleRetry (без pre_execute).
    # - on_error: в обратном порядке — SimpleRetry первым (решение о повторной kiq), затем SessionLock
    #   (снятие lock при ошибке), затем Logging.
    retry_middleware = SimpleRetryMiddleware(
        default_retry_count=settings.tasks.default_retry_count,
        default_retry_label=False,
        no_result_on_retry=True,
    )

    broker = (
        RedisStreamBroker(**broker_kwargs)
        .with_result_backend(result_backend)
        .with_middlewares(
            build_logging_middleware(
                queue_name=effective_queue,
                service_name=effective_service,
            ),
            session_lock_middleware,
            retry_middleware,
        )
    )

    return broker


def create_scheduler(broker: RedisStreamBroker) -> TaskiqScheduler:
    """
    Создает scheduler для broker.

    Args:
        broker: TaskIQ broker

    Returns:
        TaskiqScheduler с Redis source
    """
    settings = get_settings()
    broker_url = settings.tasks.broker_url

    schedule_source = ListRedisScheduleSource(url=broker_url, prefix="platform_schedules")
    scheduler = TaskiqScheduler(broker, sources=[schedule_source])

    return scheduler


def create_stale_tasks_recovery(queue_name: str = "taskiq"):
    """
    Возвращает функцию для восстановления зависших задач.

    Args:
        queue_name: Имя очереди (Redis Stream) для recovery

    Returns:
        Async функция для использования в @broker.on_event("startup")
    """
    async def recover_stale_pending_tasks() -> None:
        """
        При старте worker забираем зависшие pending задачи от мёртвых consumers.
        Задача в pending дольше 2 минут считается осиротевшей: XAUTOCLAIM
        переназначает её текущему consumer.
        """
        if not REDIS_AVAILABLE:
            logger.warning("task.stale_recover_skipped", reason="redis_unavailable", queue=queue_name)
            return

        settings = get_settings()
        broker_url = settings.tasks.broker_url

        logger.info("task.stale_recover_started", queue=queue_name)

        r = redis.from_url(broker_url)
        try:
            try:
                consumers = await r.xinfo_consumers(queue_name, queue_name)
            except Exception as exc:
                if (
                    RedisResponseError is not None
                    and isinstance(exc, RedisResponseError)
                    and "NOGROUP" in str(exc).upper()
                ):
                    logger.info(
                        "task.stale_recover_skipped",
                        queue=queue_name,
                        reason="no_consumer_group",
                    )
                    return
                raise

            if not consumers:
                return

            active = sorted(consumers, key=lambda c: c["idle"])
            if not active:
                return

            current_consumer = active[0]["name"]

            result = await r.xautoclaim(
                queue_name,
                queue_name,
                current_consumer,
                min_idle_time=120000,
                start_id="0-0",
                count=100,
            )

            claimed_count = len(result[1]) if result and len(result) > 1 else 0
            if claimed_count > 0:
                logger.warning(
                    "task.stale_recovered",
                    queue=queue_name,
                    claimed=claimed_count,
                )
            else:
                logger.info("task.stale_recover_empty", queue=queue_name)

        except Exception as exc:
            logger.exception(
                "task.stale_recover_failed",
                queue=queue_name,
                **{"exception.type": type(exc).__name__},
            )
        finally:
            await r.aclose()
            logger.info("task.stale_recover_finished", queue=queue_name)

    return recover_stale_pending_tasks


def register_worker_events(
    broker: RedisStreamBroker,
    startup_handler,
    shutdown_handler,
    *,
    service_name: str,
) -> None:
    """
    Регистрирует startup/shutdown события для worker и инициализирует
    единое логирование с этим service_name. Вызов setup_logging происходит
    в pre-startup хуке — до пользовательского startup_handler, чтобы
    первая же запись несла service.name.

    Args:
        broker: TaskIQ broker
        startup_handler: Async функция (state: TaskiqState) -> None
        shutdown_handler: Async функция (state: TaskiqState) -> None
        service_name: имя сервиса для service.name в логах (ОБЯЗАТЕЛЬНО)
    """
    if not service_name:
        raise ValueError("register_worker_events: service_name пустой")

    async def _logging_pre_startup(state: TaskiqState) -> None:
        setup_logging(service_name=service_name)

    broker.on_event(TaskiqEvents.WORKER_STARTUP)(_logging_pre_startup)
    broker.on_event(TaskiqEvents.WORKER_STARTUP)(startup_handler)
    broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)(shutdown_handler)

    logger.info("task.worker_events_registered", service=service_name)


