"""
Сервис синхронизации LLM моделей от провайдеров.
"""

import asyncio
from typing import Dict, List, Optional

import httpx

from apps.flows.config import get_settings
from core.http import get_httpx_client
from apps.flows.src.db import LLMModelRepository
from core.logging import get_logger
from apps.flows.src.models import LLMModel

logger = get_logger(__name__)


class LLMModelsService:
    """Сервис для синхронизации и получения списка LLM моделей."""

    def __init__(self, repository: LLMModelRepository):
        self._repository = repository
        self._sync_task: Optional[asyncio.Task] = None

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

    async def start_background_sync(self, interval: int = 60) -> None:
        """Запускает фоновую задачу синхронизации ВСЕХ провайдеров."""
        async def _sync_loop():
            while True:
                await asyncio.sleep(interval)
                try:
                    await self.sync_all_providers()
                except Exception as e:
                    logger.error(f"Ошибка в фоновой синхронизации моделей: {e}")

        self._sync_task = asyncio.create_task(_sync_loop())
        logger.info(f"Фоновая синхронизация моделей запущена (интервал: {interval}с)")

    async def stop_background_sync(self) -> None:
        """Останавливает фоновую задачу синхронизации."""
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
            self._sync_task = None
            logger.info("Фоновая синхронизация моделей остановлена")

