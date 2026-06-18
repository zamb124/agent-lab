"""Persistence and scheduling service for the canonical AI model catalog."""

import asyncio
from datetime import datetime, timezone

from apps.flows.config import get_settings
from core.ai.adapters import AIProviderAdapterError, create_model_catalog_adapter_registry
from core.ai.free_pool import read_humanitec_llms_model_options
from core.ai.model_catalog_repository import AIModelCatalogRepository
from core.ai.models import AIModelRecord
from core.ai.providers import (
    HUMANITEC_LLM_PROVIDER,
    OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER,
    PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER,
    PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_SLUGS,
    PROVIDER_LITSERVE,
    AICapability,
    platform_provider_specs_for_capability,
)
from core.clients.redis_client import RedisClient
from core.clients.scheduler_client import SchedulerClient
from core.logging import get_logger
from core.scheduler.models import (
    PlatformScheduleCreateRequest,
    PlatformScheduledTask,
    PlatformScheduleFilter,
    PlatformScheduleType,
    ScheduledTaskStatus,
)
from core.types import JsonObject

logger = get_logger(__name__)

_LLM_SYNC_TASK_NAME = "sync_llm_models_task"
_LLM_SYNC_TARGET_SERVICE = "flows"
_LLM_SYNC_QUEUE_NAME = "idle"
_LLM_SYNC_PAYLOAD_MARKER = "llm_models_background_sync"
_PLATFORM_FREE_MODELS_TASK_NAME = "refresh_platform_free_models_task"
_PLATFORM_FREE_MODELS_PAYLOAD_MARKER = "platform_free_models_background_sync"


class LLMModelsService:
    """Scheduler-facing orchestration for the shared ``core.ai`` model catalog."""

    def __init__(
        self,
        repository: AIModelCatalogRepository,
        scheduler_client: SchedulerClient,
        redis_client: RedisClient,
    ):
        self._repository: AIModelCatalogRepository = repository
        self._scheduler_client: SchedulerClient = scheduler_client
        self._redis_client: RedisClient = redis_client
        self._sync_schedule_task_id: str | None = None
        self._platform_free_schedule_task_id: str | None = None
        self._sync_interval_seconds: int = 60

    @staticmethod
    def _registry():
        return create_model_catalog_adapter_registry(get_settings())

    @staticmethod
    def _provider_is_configured(provider: str) -> bool:
        registry = LLMModelsService._registry()
        if not registry.has(provider):
            return False
        return registry.get(provider).is_configured()

    async def fetch_models_by_provider(self, provider: str) -> list[str]:
        """Fetch provider model ids from canonical ``core.ai`` model discovery."""
        normalized_provider = provider.strip()
        registry = self._registry()
        if not registry.has(normalized_provider):
            logger.warning("Неизвестный провайдер: %s", provider)
            return []
        records = await registry.get(normalized_provider).list_models(probe_embeddings=False)
        return [record.model_id for record in records]

    async def fetch_model_records_by_provider(self, provider: str) -> list[AIModelRecord]:
        """Fetch full provider model records from dynamic discovery and probes."""
        normalized_provider = provider.strip()
        registry = self._registry()
        if not registry.has(normalized_provider):
            logger.warning("Неизвестный провайдер: %s", provider)
            return []
        return await registry.get(normalized_provider).list_models(probe_embeddings=True)

    async def discover_model_records_by_provider(self, provider: str) -> list[AIModelRecord]:
        """Fetch provider catalog without inference endpoint probes."""
        normalized_provider = provider.strip()
        registry = self._registry()
        if not registry.has(normalized_provider):
            logger.warning("Неизвестный провайдер: %s", provider)
            return []
        return await registry.get(normalized_provider).list_models(probe_embeddings=False)

    async def probe_embedding_dimension(self, provider: str, model_id: str) -> int | None:
        """Public live probe for verified embedding model metadata."""
        normalized_provider = provider.strip()
        registry = self._registry()
        if not registry.has(normalized_provider):
            raise ValueError(f"Неизвестный провайдер: {provider}")
        return await registry.get(normalized_provider).probe_embedding_dimension(model_id)

    @staticmethod
    def storage_dimension_for_embedding(native_dimension: int | None) -> int | None:
        """Project native embedding dimension to the current pgvector storage dimension."""
        if native_dimension is None:
            return None
        storage_dimension = get_settings().rag.embedding.api.dimension
        if native_dimension == storage_dimension:
            return storage_dimension
        return None

    async def fetch_models(self) -> list[str]:
        """Fetch models from the configured default provider."""
        settings = get_settings()
        return await self.fetch_models_by_provider(settings.llm.provider)

    async def sync_models_by_provider(self, provider: str) -> int:
        """Sync model records from one provider into the single catalog storage."""
        try:
            records = await self.fetch_model_records_by_provider(provider)
            if not records:
                logger.warning("Не получено моделей от провайдера %s", provider)
                return 0

            for model in records:
                _ = await self._repository.set(model)

            logger.info("Синхронизировано %d моделей от %s", len(records), provider)
            return len(records)
        except AIProviderAdapterError as exc:
            logger.error("Ошибка при синхронизации моделей от %s: %s", provider, exc)
            return 0
        except Exception as exc:
            logger.error("Ошибка при синхронизации моделей от %s: %s", provider, exc)
            return 0

    async def sync_models(self) -> int:
        """Sync models from the configured default provider."""
        settings = get_settings()
        return await self.sync_models_by_provider(settings.llm.provider)

    async def sync_all_providers(self) -> dict[str, int]:
        """Sync models from every configured provider adapter."""
        providers = [
            adapter.provider
            for adapter in self._registry().all()
            if adapter.is_configured()
        ]
        counts = await asyncio.gather(
            *(self.sync_models_by_provider(provider) for provider in providers)
        )
        results = dict(zip(providers, counts, strict=True))

        total = sum(results.values())
        logger.info("Синхронизировано %d моделей от всех провайдеров: %s", total, results)
        return results

    async def get_default_model_ids_by_capability(
        self,
        capability: AICapability,
    ) -> list[str | JsonObject]:
        """Read model ids for the configured default provider and capability."""
        settings = get_settings()
        return await self.get_model_ids_by_provider_capability(settings.llm.provider, capability)

    async def get_model_ids_by_provider_capability(
        self,
        provider: str,
        capability: AICapability,
    ) -> list[str | JsonObject]:
        """Read model ids for one provider and one AI capability from storage."""
        if provider == HUMANITEC_LLM_PROVIDER:
            if capability not in {
                AICapability.LLM_CHAT,
                AICapability.LLM_SUMMARIZE,
                AICapability.LLM_FORMAT_MARKDOWN,
                AICapability.LLM_CODEGEN,
                AICapability.LLM_VISION,
            }:
                return []
            options = await read_humanitec_llms_model_options(self._redis_client)
            humanitec_models: list[str | JsonObject] = []
            humanitec_models.extend(options)
            return humanitec_models
        models = await self._repository.list_by_provider_capability(provider, capability)
        provider_models: list[str | JsonObject] = []
        provider_models.extend(m.model_id for m in models)
        return provider_models

    @staticmethod
    def get_configured_providers() -> list[str]:
        """Configured providers from the canonical adapter registry.

        Humanitec LLMs is shown when the free-pool feature is enabled and at
        least one configured free-candidate provider is active.
        """
        settings = get_settings()
        registry = LLMModelsService._registry()
        configured_providers = [
            provider
            for provider in OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER
            if registry.has(provider) and registry.get(provider).is_configured()
        ]
        providers: list[str] = []
        if (
            settings.llm.platform_free_pool.enabled
            and any(
                provider in configured_providers
                and provider in PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_SLUGS
                for provider in PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER
            )
        ):
            providers.append(HUMANITEC_LLM_PROVIDER)
        providers.extend(configured_providers)
        if registry.has(PROVIDER_LITSERVE) and registry.get(PROVIDER_LITSERVE).is_configured():
            providers.append(PROVIDER_LITSERVE)
        return providers

    @staticmethod
    def get_configured_providers_by_capability(capability: AICapability) -> list[str]:
        """Configured providers that support exactly one AI capability."""
        settings = get_settings()
        registry = LLMModelsService._registry()
        configured_free_candidates = {
            provider
            for provider in PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER
            if registry.has(provider) and registry.get(provider).is_configured()
        }
        providers: list[str] = []
        for spec in platform_provider_specs_for_capability(capability):
            provider = spec.provider
            if provider == HUMANITEC_LLM_PROVIDER:
                if (
                    capability in {
                        AICapability.LLM_CHAT,
                        AICapability.LLM_SUMMARIZE,
                        AICapability.LLM_FORMAT_MARKDOWN,
                        AICapability.LLM_CODEGEN,
                        AICapability.LLM_VISION,
                    }
                    and settings.llm.platform_free_pool.enabled
                    and configured_free_candidates
                ):
                    providers.append(provider)
                continue
            if registry.has(provider) and registry.get(provider).is_configured():
                providers.append(provider)
        return providers

    @staticmethod
    def _is_compatible_background_schedule(task: PlatformScheduledTask, interval: int) -> bool:
        if task.target_service != _LLM_SYNC_TARGET_SERVICE:
            return False
        if task.task_name != _LLM_SYNC_TASK_NAME:
            return False
        if task.schedule_type != PlatformScheduleType.INTERVAL:
            return False
        if task.interval_seconds != interval:
            return False
        return True

    @staticmethod
    def _is_compatible_platform_free_schedule(task: PlatformScheduledTask, interval: int) -> bool:
        if task.target_service != _LLM_SYNC_TARGET_SERVICE:
            return False
        if task.task_name != _PLATFORM_FREE_MODELS_TASK_NAME:
            return False
        if task.schedule_type != PlatformScheduleType.INTERVAL:
            return False
        if task.interval_seconds != interval:
            return False
        return True

    async def _list_background_schedules(self, interval: int) -> list[PlatformScheduledTask]:
        schedules = await self._scheduler_client.list_schedules(
            PlatformScheduleFilter(
                target_service=_LLM_SYNC_TARGET_SERVICE,
                task_name=_LLM_SYNC_TASK_NAME,
                limit=500,
                offset=0,
            )
        )
        schedule_items = list(schedules.items)
        return [task for task in schedule_items if self._is_compatible_background_schedule(task, interval)]

    async def _list_platform_free_schedules(self, interval: int) -> list[PlatformScheduledTask]:
        schedules = await self._scheduler_client.list_schedules(
            PlatformScheduleFilter(
                target_service=_LLM_SYNC_TARGET_SERVICE,
                task_name=_PLATFORM_FREE_MODELS_TASK_NAME,
                limit=500,
                offset=0,
            )
        )
        schedule_items = list(schedules.items)
        return [
            task
            for task in schedule_items
            if self._is_compatible_platform_free_schedule(task, interval)
        ]

    @staticmethod
    def _pick_single_or_raise(tasks: list[PlatformScheduledTask], status: ScheduledTaskStatus) -> PlatformScheduledTask | None:
        matched = [task for task in tasks if task.status == status]
        if not matched:
            return None
        if len(matched) > 1:
            schedule_task_ids = ", ".join(task.schedule_task_id for task in matched)
            raise ValueError(
                f"multiple LLM sync schedules with status={status}: {schedule_task_ids}"
            )
        return matched[0]

    async def start_background_sync(self, interval: int = 60) -> None:
        """Create recurring scheduler task for provider model catalog sync."""
        if interval <= 0:
            raise ValueError("interval must be positive")
        self._sync_interval_seconds = interval
        schedules = await self._list_background_schedules(interval=interval)
        pending = self._pick_single_or_raise(schedules, ScheduledTaskStatus.PENDING)
        if pending is not None:
            self._sync_schedule_task_id = pending.schedule_task_id
            logger.info(
                "Фоновая синхронизация уже запланирована (schedule_task_id=%s)",
                pending.schedule_task_id,
            )
            return
        paused = self._pick_single_or_raise(schedules, ScheduledTaskStatus.PAUSED)
        if paused is not None:
            resumed = await self._scheduler_client.resume_schedule(paused.schedule_task_id)
            self._sync_schedule_task_id = resumed.schedule_task_id
            logger.info(
                "Фоновая синхронизация возобновлена (schedule_task_id=%s)",
                resumed.schedule_task_id,
            )
            return
        request = PlatformScheduleCreateRequest(
            target_service=_LLM_SYNC_TARGET_SERVICE,
            task_name=_LLM_SYNC_TASK_NAME,
            queue_name=_LLM_SYNC_QUEUE_NAME,
            schedule_type=PlatformScheduleType.INTERVAL,
            interval_seconds=interval,
            payload={"system_task": _LLM_SYNC_PAYLOAD_MARKER},
            timezone="UTC",
            run_at=datetime.now(timezone.utc),
        )
        schedule = await self._scheduler_client.create_schedule(request)
        self._sync_schedule_task_id = schedule.schedule_task_id
        logger.info(
            "Фоновая синхронизация моделей запланирована в scheduler (schedule_task_id=%s)",
            schedule.schedule_task_id,
        )

    async def start_platform_free_models_sync(self, interval: int) -> None:
        """Create recurring scheduler task for Redis platform free-pool refresh."""
        if interval <= 0:
            raise ValueError("interval must be positive")
        schedules = await self._list_platform_free_schedules(interval=interval)
        pending = self._pick_single_or_raise(schedules, ScheduledTaskStatus.PENDING)
        if pending is not None:
            self._platform_free_schedule_task_id = pending.schedule_task_id
            logger.info(
                "Platform free-pool sync уже запланирован (schedule_task_id=%s)",
                pending.schedule_task_id,
            )
            return
        paused = self._pick_single_or_raise(schedules, ScheduledTaskStatus.PAUSED)
        if paused is not None:
            resumed = await self._scheduler_client.resume_schedule(paused.schedule_task_id)
            self._platform_free_schedule_task_id = resumed.schedule_task_id
            logger.info(
                "Platform free-pool sync возобновлен (schedule_task_id=%s)",
                resumed.schedule_task_id,
            )
            return
        request = PlatformScheduleCreateRequest(
            target_service=_LLM_SYNC_TARGET_SERVICE,
            task_name=_PLATFORM_FREE_MODELS_TASK_NAME,
            queue_name=_LLM_SYNC_QUEUE_NAME,
            schedule_type=PlatformScheduleType.INTERVAL,
            interval_seconds=interval,
            payload={"system_task": _PLATFORM_FREE_MODELS_PAYLOAD_MARKER},
            timezone="UTC",
            run_at=datetime.now(timezone.utc),
        )
        schedule = await self._scheduler_client.create_schedule(request)
        self._platform_free_schedule_task_id = schedule.schedule_task_id
        logger.info(
            "Platform free-pool sync запланирован (schedule_task_id=%s)",
            schedule.schedule_task_id,
        )

    async def stop_background_sync(self) -> None:
        """Cancel recurring provider model catalog sync."""
        if not self._sync_schedule_task_id:
            return
        _ = await self._scheduler_client.cancel_schedule(self._sync_schedule_task_id)
        logger.info(
            "Фоновая синхронизация моделей остановлена (schedule_task_id=%s)",
            self._sync_schedule_task_id,
        )
        self._sync_schedule_task_id = None

    async def stop_platform_free_models_sync(self) -> None:
        """Cancel recurring Redis platform free-pool refresh."""
        if not self._platform_free_schedule_task_id:
            return
        _ = await self._scheduler_client.cancel_schedule(self._platform_free_schedule_task_id)
        logger.info(
            "Platform free-pool sync остановлен (schedule_task_id=%s)",
            self._platform_free_schedule_task_id,
        )
        self._platform_free_schedule_task_id = None
