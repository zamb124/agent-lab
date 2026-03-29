"""Сервис синхронизации LLM моделей от провайдеров."""

from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx

from apps.flows.config import get_settings
from core.http import get_httpx_client
from apps.flows.src.db import LLMModelRepository
from core.clients import SchedulerClient
from core.logging import get_logger
from core.scheduler.models import (
    PlatformScheduleCreateRequest,
    PlatformScheduleFilter,
    PlatformScheduledTask,
    PlatformScheduleType,
    ScheduledTaskStatus,
)
from apps.flows.src.models import LLMModel

logger = get_logger(__name__)

_LLM_SYNC_TASK_NAME = "sync_llm_models_task"
_LLM_SYNC_TARGET_SERVICE = "flows"
_LLM_SYNC_QUEUE_NAME = "default"
_LLM_SYNC_PAYLOAD_MARKER = "llm_models_background_sync"


class LLMModelsService:
    """Сервис для синхронизации и получения списка LLM моделей."""

    def __init__(self, repository: LLMModelRepository, scheduler_client: SchedulerClient):
        self._repository = repository
        self._scheduler_client = scheduler_client
        self._sync_schedule_id: Optional[str] = None
        self._sync_interval_seconds: int = 60

    async def _fetch_bothub_models(self) -> List[str]:
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

        async with get_httpx_client(timeout=30.0, proxy=True) as client:
            response = await client.get(url, headers=headers)
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

    async def _fetch_openrouter_models(self) -> List[str]:
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

        async with get_httpx_client(timeout=30.0, proxy=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            models = [item["id"] for item in data.get("data", [])]
            logger.info(f"OpenRouter: получено {len(models)} моделей")
            return models

    async def _fetch_openai_models(self) -> List[str]:
        """Запрос моделей от OpenAI API."""
        settings = get_settings()
        cfg = settings.llm.openai
        if not cfg or not cfg.api_key:
            logger.warning("OpenAI API key не настроен")
            return []

        base_url = cfg.base_url or "https://api.openai.com/v1"
        url = f"{base_url}/models"
        headers = {"Authorization": f"Bearer {cfg.api_key}"}

        async with get_httpx_client(timeout=30.0, proxy=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            models = [item["id"] for item in data.get("data", [])]
            logger.info(f"OpenAI: получено {len(models)} моделей")
            return models

    async def fetch_models_by_provider(self, provider: str) -> List[str]:
        """Запрос моделей от указанного провайдера."""
        if provider == "bothub":
            return await self._fetch_bothub_models()
        elif provider == "openrouter":
            return await self._fetch_openrouter_models()
        elif provider == "openai":
            return await self._fetch_openai_models()
        else:
            logger.warning(f"Неизвестный провайдер: {provider}")
            return []

    async def fetch_models(self) -> List[str]:
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

    async def sync_all_providers(self) -> Dict[str, int]:
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
        
        total = sum(results.values())
        logger.info(f"Синхронизировано {total} моделей от всех провайдеров: {results}")
        return results

    async def get_models(self) -> List[str]:
        """Возвращает список id моделей текущего провайдера из БД."""
        settings = get_settings()
        return await self.get_models_by_provider(settings.llm.provider)

    async def get_models_by_provider(self, provider: str) -> List[str]:
        """Возвращает список id моделей указанного провайдера из БД."""
        models = await self._repository.list_by_provider(provider)
        return [m.model_id for m in models]

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

    async def _list_background_schedules(self, interval: int) -> list[PlatformScheduledTask]:
        schedules = await self._scheduler_client.list_schedules(
            PlatformScheduleFilter(
                target_service=_LLM_SYNC_TARGET_SERVICE,
                task_name=_LLM_SYNC_TASK_NAME,
                limit=500,
                offset=0,
            )
        )
        return [task for task in schedules if self._is_compatible_background_schedule(task, interval)]

    @staticmethod
    def _pick_single_or_raise(tasks: list[PlatformScheduledTask], status: ScheduledTaskStatus) -> PlatformScheduledTask | None:
        matched = [task for task in tasks if task.status == status]
        if not matched:
            return None
        if len(matched) > 1:
            task_ids = ", ".join(task.id for task in matched)
            raise ValueError(f"multiple LLM sync schedules with status={status}: {task_ids}")
        return matched[0]

    async def start_background_sync(self, interval: int = 60) -> None:
        """Создает recurring schedule для синхронизации ВСЕХ провайдеров."""
        if interval <= 0:
            raise ValueError("interval must be positive")
        self._sync_interval_seconds = interval
        schedules = await self._list_background_schedules(interval=interval)
        pending = self._pick_single_or_raise(schedules, ScheduledTaskStatus.PENDING)
        if pending is not None:
            self._sync_schedule_id = pending.id
            logger.info("Фоновая синхронизация уже запланирована (task_id=%s)", pending.id)
            return
        paused = self._pick_single_or_raise(schedules, ScheduledTaskStatus.PAUSED)
        if paused is not None:
            resumed = await self._scheduler_client.resume_schedule(paused.id)
            self._sync_schedule_id = resumed.id
            logger.info("Фоновая синхронизация возобновлена (task_id=%s)", resumed.id)
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
        self._sync_schedule_id = schedule.id
        logger.info("Фоновая синхронизация моделей запланирована в scheduler (task_id=%s)", schedule.id)

    async def stop_background_sync(self) -> None:
        """Отменяет recurring schedule синхронизации моделей."""
        if not self._sync_schedule_id:
            return
        await self._scheduler_client.cancel_schedule(self._sync_schedule_id)
        logger.info("Фоновая синхронизация моделей остановлена (task_id=%s)", self._sync_schedule_id)
        self._sync_schedule_id = None

