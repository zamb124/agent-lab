"""Сервис синхронизации LLM моделей от провайдеров."""

from datetime import datetime, timezone

import httpx

from apps.flows.config import get_settings
from apps.flows.src.db import LLMModelRepository
from apps.flows.src.models import LLMModel
from core.clients.llm.model_routing import HUMANITEC_LLM_AUTO_MODEL, HUMANITEC_LLM_PROVIDER
from core.clients.scheduler_client import SchedulerClient
from core.config.llm_openai_compat import (
    yandex_llm_openai_root_from_provider_cfg,
    yandex_provider_http_headers,
)
from core.http import ProxyStrategy, get_httpx_client
from core.http.client import request_with_strategy
from core.logging import get_logger
from core.scheduler.models import (
    PlatformScheduleCreateRequest,
    PlatformScheduledTask,
    PlatformScheduleFilter,
    PlatformScheduleType,
    ScheduledTaskStatus,
)

logger = get_logger(__name__)

_LLM_SYNC_TASK_NAME = "sync_llm_models_task"
_LLM_SYNC_TARGET_SERVICE = "flows"
_LLM_SYNC_QUEUE_NAME = "idle"
_LLM_SYNC_PAYLOAD_MARKER = "llm_models_background_sync"
_OPENROUTER_FREE_MODELS_TASK_NAME = "refresh_openrouter_free_models_task"
_OPENROUTER_FREE_MODELS_PAYLOAD_MARKER = "openrouter_free_models_background_sync"


class LLMModelsService:
    """Сервис для синхронизации и получения списка LLM моделей."""

    def __init__(self, repository: LLMModelRepository, scheduler_client: SchedulerClient):
        self._repository = repository
        self._scheduler_client = scheduler_client
        self._sync_schedule_task_id: str | None = None
        self._openrouter_free_schedule_task_id: str | None = None
        self._sync_interval_seconds: int = 60

    async def _fetch_bothub_models(self) -> list[str]:
        """
        Запрос моделей от BotHub API.
        API: https://bothub.chat/api/v2/model/list?children=1
        """
        settings = get_settings()
        cfg = settings.llm.bothub
        if not cfg or not cfg.api_key:
            logger.warning("BotHub API key не настроен")
            return []

        # BotHub использует отдельный endpoint для списка моделей
        url = "https://bothub.chat/api/v2/model/list?children=1"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg.api_key}",
        }

        response = await request_with_strategy(
            "GET",
            url,
            headers=headers,
            timeout=30.0,
            strategy=ProxyStrategy.DIRECT_FIRST,
            direct_attempts=3,
            proxy_attempts=3,
        )
        response.raise_for_status()
        data = response.json()
        # BotHub возвращает список моделей с полем "name" или "id"
        models = []
        for item in data if isinstance(data, list) else data.get("data", []):
            model_id = item.get("name") or item.get("id")
            if model_id:
                models.append(model_id)
        logger.info(f"BotHub: получено {len(models)} моделей")
        return models

    async def _fetch_openrouter_models(self) -> list[str]:
        """Запрос моделей от OpenRouter API."""
        settings = get_settings()
        cfg = settings.llm.openrouter
        if not cfg or not cfg.api_key:
            logger.warning("OpenRouter API key не настроен")
            return []

        url = f"{cfg.base_url}/models"
        headers = {
            "Authorization": f"Bearer {cfg.api_key}",
            "HTTP-Referer": cfg.site_url,
            "X-Title": cfg.site_name,
        }

        response = await request_with_strategy(
            "GET",
            url,
            headers=headers,
            timeout=30.0,
            strategy=ProxyStrategy.DIRECT_FIRST,
            direct_attempts=3,
            proxy_attempts=3,
        )
        response.raise_for_status()
        data = response.json()
        models = [item["id"] for item in data.get("data", [])]
        logger.info(f"OpenRouter: получено {len(models)} моделей")
        return models

    async def _fetch_openai_models(self) -> list[str]:
        """Запрос моделей от OpenAI API."""
        settings = get_settings()
        cfg = settings.llm.openai
        if not cfg or not cfg.api_key:
            logger.warning("OpenAI API key не настроен")
            return []

        base_url = cfg.base_url or "https://api.openai.com/v1"
        url = f"{base_url}/models"
        headers = {"Authorization": f"Bearer {cfg.api_key}"}

        response = await request_with_strategy(
            "GET",
            url,
            headers=headers,
            timeout=30.0,
            strategy=ProxyStrategy.DIRECT_FIRST,
            direct_attempts=3,
            proxy_attempts=3,
        )
        response.raise_for_status()
        data = response.json()
        models = [item["id"] for item in data.get("data", [])]
        logger.info(f"OpenAI: получено {len(models)} моделей")
        return models

    async def _fetch_yandex_models(self) -> list[str]:
        """Запрос моделей от Yandex OpenAI-совместимого API."""
        settings = get_settings()
        cfg = settings.llm.yandex
        if not cfg or not cfg.api_key:
            logger.warning("Yandex LLM API key не настроен")
            return []
        if not cfg.folder_id or not str(cfg.folder_id).strip():
            logger.warning("Yandex LLM folder_id не настроен")
            return []

        base = yandex_llm_openai_root_from_provider_cfg(cfg)
        url = f"{base}/models"
        headers = {
            **yandex_provider_http_headers(cfg),
            "Content-Type": "application/json",
        }

        response = await request_with_strategy(
            "GET",
            url,
            headers=headers,
            timeout=30.0,
            strategy=ProxyStrategy.DIRECT_FIRST,
            direct_attempts=3,
            proxy_attempts=3,
        )
        response.raise_for_status()
        data = response.json()
        models = [item["id"] for item in data.get("data", [])]
        logger.info(f"Yandex LLM: получено {len(models)} моделей")
        return models

    async def _fetch_provider_litserve_models(self) -> list[str]:
        """Запрос моделей от provider_litserve OpenAI-совместимого API."""
        settings = get_settings()
        provider_cfg = settings.provider_litserve
        base_url = provider_cfg.resolve_openai_v1_base_url()
        url = f"{base_url}/models"

        async with get_httpx_client(timeout=30.0, strategy=ProxyStrategy.DIRECT_ONLY) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            models = [item["id"] for item in data.get("data", [])]
            logger.info(f"provider_litserve: получено {len(models)} моделей")
            return models

    async def fetch_models_by_provider(self, provider: str) -> list[str]:
        """Запрос моделей от указанного провайдера."""
        if provider == "bothub":
            return await self._fetch_bothub_models()
        elif provider == "openrouter":
            return await self._fetch_openrouter_models()
        elif provider == "openai":
            return await self._fetch_openai_models()
        elif provider == "yandex":
            return await self._fetch_yandex_models()
        elif provider == "provider_litserve":
            return await self._fetch_provider_litserve_models()
        else:
            logger.warning(f"Неизвестный провайдер: {provider}")
            return []

    async def fetch_models(self) -> list[str]:
        """Запрос моделей от текущего провайдера из конфига."""
        settings = get_settings()
        return await self.fetch_models_by_provider(settings.llm.provider)

    async def sync_models_by_provider(self, provider: str) -> int:
        """Синхронизация моделей от указанного провайдера."""
        try:
            model_ids = await self.fetch_models_by_provider(provider)
            if not model_ids:
                logger.warning(f"Не получено моделей от провайдера {provider}")
                return 0

            for model_id in model_ids:
                model = LLMModel(model_id=model_id, provider=provider)
                await self._repository.set(model)

            logger.info(f"Синхронизировано {len(model_ids)} моделей от {provider}")
            return len(model_ids)

        except httpx.HTTPError as e:
            logger.error(f"Ошибка HTTP при синхронизации моделей от {provider}: {e}")
            return 0
        except Exception as e:
            logger.error(f"Ошибка при синхронизации моделей от {provider}: {e}")
            return 0

    async def sync_models(self) -> int:
        """Синхронизация моделей от текущего провайдера из конфига."""
        settings = get_settings()
        return await self.sync_models_by_provider(settings.llm.provider)

    async def sync_all_providers(self) -> dict[str, int]:
        """Синхронизация моделей от ВСЕХ настроенных провайдеров."""
        settings = get_settings()
        results = {}

        # BotHub
        if settings.llm.bothub and settings.llm.bothub.api_key:
            results["bothub"] = await self.sync_models_by_provider("bothub")

        # OpenRouter
        if settings.llm.openrouter and settings.llm.openrouter.api_key:
            results["openrouter"] = await self.sync_models_by_provider("openrouter")

        # OpenAI
        if settings.llm.openai and settings.llm.openai.api_key:
            results["openai"] = await self.sync_models_by_provider("openai")

        if settings.llm.yandex and settings.llm.yandex.api_key and settings.llm.yandex.folder_id:
            results["yandex"] = await self.sync_models_by_provider("yandex")

        # provider_litserve
        provider_cfg = settings.provider_litserve
        if provider_cfg.api.base_url:
            results["provider_litserve"] = await self.sync_models_by_provider("provider_litserve")

        total = sum(results.values())
        logger.info(f"Синхронизировано {total} моделей от всех провайдеров: {results}")
        return results

    async def get_models(self) -> list[str]:
        """Возвращает список id моделей текущего провайдера из БД."""
        settings = get_settings()
        return await self.get_models_by_provider(settings.llm.provider)

    async def get_models_by_provider(self, provider: str) -> list[str]:
        """Возвращает список id моделей указанного провайдера из БД."""
        if provider == HUMANITEC_LLM_PROVIDER:
            return [HUMANITEC_LLM_AUTO_MODEL]
        models = await self._repository.list_by_provider(provider)
        return [m.model_id for m in models]

    @staticmethod
    def get_configured_providers() -> list[str]:
        """Список реально настроенных LLM-провайдеров из conf.json.

        Провайдер считается настроенным, если в `settings.llm.<provider>` присутствует
        api_key (для openai/openrouter/bothub), для yandex — ещё и непустой folder_id,
        либо если для provider_litserve задан base_url. humanitec_llm доступен, когда
        включён платформенный OpenRouter dynamic pool.
        """
        settings = get_settings()
        providers: list[str] = []
        if settings.llm.openai and settings.llm.openai.api_key:
            providers.append("openai")
        if settings.llm.openrouter and settings.llm.openrouter.api_key:
            providers.append("openrouter")
        if (
            settings.llm.openrouter_free_pool.enabled
            and settings.llm.openrouter
            and settings.llm.openrouter.api_key
        ):
            providers.append(HUMANITEC_LLM_PROVIDER)
        if settings.llm.bothub and settings.llm.bothub.api_key:
            providers.append("bothub")
        if (
            settings.llm.yandex
            and settings.llm.yandex.api_key
            and settings.llm.yandex.folder_id
            and str(settings.llm.yandex.folder_id).strip()
        ):
            providers.append("yandex")
        if settings.provider_litserve.api.base_url:
            providers.append("provider_litserve")
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
    def _is_compatible_openrouter_free_schedule(task: PlatformScheduledTask, interval: int) -> bool:
        if task.target_service != _LLM_SYNC_TARGET_SERVICE:
            return False
        if task.task_name != _OPENROUTER_FREE_MODELS_TASK_NAME:
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

    async def _list_openrouter_free_schedules(self, interval: int) -> list[PlatformScheduledTask]:
        schedules = await self._scheduler_client.list_schedules(
            PlatformScheduleFilter(
                target_service=_LLM_SYNC_TARGET_SERVICE,
                task_name=_OPENROUTER_FREE_MODELS_TASK_NAME,
                limit=500,
                offset=0,
            )
        )
        schedule_items = list(schedules.items)
        return [
            task
            for task in schedule_items
            if self._is_compatible_openrouter_free_schedule(task, interval)
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
        """Создает recurring schedule для синхронизации ВСЕХ провайдеров."""
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

    async def start_openrouter_free_models_sync(self, interval: int) -> None:
        """Создает recurring schedule обновления Redis free-pool OpenRouter."""
        if interval <= 0:
            raise ValueError("interval must be positive")
        schedules = await self._list_openrouter_free_schedules(interval=interval)
        pending = self._pick_single_or_raise(schedules, ScheduledTaskStatus.PENDING)
        if pending is not None:
            self._openrouter_free_schedule_task_id = pending.schedule_task_id
            logger.info(
                "OpenRouter free-pool sync уже запланирован (schedule_task_id=%s)",
                pending.schedule_task_id,
            )
            return
        paused = self._pick_single_or_raise(schedules, ScheduledTaskStatus.PAUSED)
        if paused is not None:
            resumed = await self._scheduler_client.resume_schedule(paused.schedule_task_id)
            self._openrouter_free_schedule_task_id = resumed.schedule_task_id
            logger.info(
                "OpenRouter free-pool sync возобновлен (schedule_task_id=%s)",
                resumed.schedule_task_id,
            )
            return
        request = PlatformScheduleCreateRequest(
            target_service=_LLM_SYNC_TARGET_SERVICE,
            task_name=_OPENROUTER_FREE_MODELS_TASK_NAME,
            queue_name=_LLM_SYNC_QUEUE_NAME,
            schedule_type=PlatformScheduleType.INTERVAL,
            interval_seconds=interval,
            payload={"system_task": _OPENROUTER_FREE_MODELS_PAYLOAD_MARKER},
            timezone="UTC",
            run_at=datetime.now(timezone.utc),
        )
        schedule = await self._scheduler_client.create_schedule(request)
        self._openrouter_free_schedule_task_id = schedule.schedule_task_id
        logger.info(
            "OpenRouter free-pool sync запланирован (schedule_task_id=%s)",
            schedule.schedule_task_id,
        )

    async def stop_background_sync(self) -> None:
        """Отменяет recurring schedule синхронизации моделей."""
        if not self._sync_schedule_task_id:
            return
        await self._scheduler_client.cancel_schedule(self._sync_schedule_task_id)
        logger.info(
            "Фоновая синхронизация моделей остановлена (schedule_task_id=%s)",
            self._sync_schedule_task_id,
        )
        self._sync_schedule_task_id = None

    async def stop_openrouter_free_models_sync(self) -> None:
        """Отменяет recurring schedule обновления Redis free-pool OpenRouter."""
        if not self._openrouter_free_schedule_task_id:
            return
        await self._scheduler_client.cancel_schedule(self._openrouter_free_schedule_task_id)
        logger.info(
            "OpenRouter free-pool sync остановлен (schedule_task_id=%s)",
            self._openrouter_free_schedule_task_id,
        )
        self._openrouter_free_schedule_task_id = None
