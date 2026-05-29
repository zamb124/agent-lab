"""Сервис синхронизации LLM моделей от провайдеров."""

import asyncio
from datetime import datetime, timezone
from typing import cast

import httpx

from apps.flows.config import get_settings
from apps.flows.src.db import LLMModelRepository
from apps.flows.src.models import LLMModel
from core.clients.llm.model_routing import (
    ACCOUNT_FREE_TIER_LLM_PROVIDER_SLUGS,
    HUMANITEC_LLM_PROVIDER,
    OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER,
    OPENAI_COMPATIBLE_LLM_PROVIDER_SLUGS,
    PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_SLUGS,
)
from core.clients.llm.platform_free_models import read_humanitec_llms_model_options
from core.clients.redis_client import RedisClient
from core.clients.scheduler_client import SchedulerClient
from core.config.llm_openai_compat import (
    yandex_llm_openai_root_from_provider_cfg,
    yandex_provider_http_headers,
)
from core.config.models import (
    BothubProviderConfig,
    DeepInfraProviderConfig,
    GitHubModelsProviderConfig,
    GoogleLLMProviderConfig,
    GroqProviderConfig,
    HuggingFaceProviderConfig,
    OpenAIProviderConfig,
    OpenRouterProviderConfig,
    YandexLLMProviderConfig,
)
from core.http import ProxyStrategy
from core.http.client import request_with_strategy
from core.llm_model_routing import GITHUB_MODELS_API_VERSION, LLM_PROVIDER_DEFAULT_MODELS_URLS
from core.logging import get_logger
from core.scheduler.models import (
    PlatformScheduleCreateRequest,
    PlatformScheduledTask,
    PlatformScheduleFilter,
    PlatformScheduleType,
    ScheduledTaskStatus,
)
from core.types import (
    JsonArray,
    JsonObject,
    JsonValue,
    parse_json_value,
    require_json_object,
)

logger = get_logger(__name__)

_LLM_SYNC_TASK_NAME = "sync_llm_models_task"
_LLM_SYNC_TARGET_SERVICE = "flows"
_LLM_SYNC_QUEUE_NAME = "idle"
_LLM_SYNC_PAYLOAD_MARKER = "llm_models_background_sync"
_PLATFORM_FREE_MODELS_TASK_NAME = "refresh_platform_free_models_task"
_PLATFORM_FREE_MODELS_PAYLOAD_MARKER = "platform_free_models_background_sync"
_ConfiguredLLMProvider = (
    OpenAIProviderConfig
    | OpenRouterProviderConfig
    | BothubProviderConfig
    | YandexLLMProviderConfig
    | GroqProviderConfig
    | GoogleLLMProviderConfig
    | GitHubModelsProviderConfig
    | HuggingFaceProviderConfig
    | DeepInfraProviderConfig
)


class LLMModelsService:
    """Сервис для синхронизации и получения списка LLM моделей."""

    def __init__(
        self,
        repository: LLMModelRepository,
        scheduler_client: SchedulerClient,
        redis_client: RedisClient,
    ):
        self._repository: LLMModelRepository = repository
        self._scheduler_client: SchedulerClient = scheduler_client
        self._redis_client: RedisClient = redis_client
        self._sync_schedule_task_id: str | None = None
        self._platform_free_schedule_task_id: str | None = None
        self._sync_interval_seconds: int = 60

    @staticmethod
    def _configured_llm_provider(provider: str) -> _ConfiguredLLMProvider | None:
        settings = get_settings()
        if provider == "openrouter":
            return settings.llm.openrouter
        if provider == "bothub":
            return settings.llm.bothub
        if provider == "groq":
            return settings.llm.groq
        if provider == "google":
            return settings.llm.google
        if provider == "github":
            return settings.llm.github
        if provider == "huggingface":
            return settings.llm.huggingface
        if provider == "deepinfra":
            return settings.llm.deepinfra
        if provider == "openai":
            return settings.llm.openai
        if provider == "yandex":
            return settings.llm.yandex
        return None

    @staticmethod
    def _json_str(value: JsonValue) -> str | None:
        if not isinstance(value, str):
            return None
        stripped = value.strip()
        if not stripped:
            return None
        return stripped

    @classmethod
    def _model_id_from_object(
        cls,
        item: JsonObject,
        *,
        primary_key: str,
        fallback_key: str | None = None,
    ) -> str | None:
        primary = cls._json_str(item.get(primary_key))
        if primary is not None:
            return primary
        if fallback_key is None:
            return None
        return cls._json_str(item.get(fallback_key))

    @classmethod
    def _extract_model_ids_from_array(
        cls,
        items: JsonArray,
        *,
        provider: str,
        primary_key: str,
        fallback_key: str | None = None,
    ) -> list[str]:
        models: list[str] = []
        for idx, raw_item in enumerate(items):
            item = require_json_object(raw_item, f"{provider}.models[{idx}]")
            model_id = cls._model_id_from_object(
                item,
                primary_key=primary_key,
                fallback_key=fallback_key,
            )
            if model_id is not None:
                models.append(model_id)
        return models

    @classmethod
    def _extract_openai_compatible_model_ids(cls, payload: JsonObject, provider: str) -> list[str]:
        data = payload.get("data")
        if not isinstance(data, list):
            raise ValueError(f"{provider} models response: data must be an array")
        return cls._extract_model_ids_from_array(data, provider=provider, primary_key="id")

    @classmethod
    def _extract_github_catalog_model_ids(cls, payload: JsonValue) -> list[str]:
        if not isinstance(payload, list):
            raise ValueError("github models catalog response must be an array")
        return cls._extract_model_ids_from_array(payload, provider="github", primary_key="id")

    @classmethod
    def _extract_google_model_ids(cls, payload: JsonValue) -> list[str]:
        payload_object = require_json_object(payload, "google.models.response")
        models_raw = payload_object.get("models")
        if not isinstance(models_raw, list):
            raise ValueError("google models response: models must be an array")
        raw_model_ids = cls._extract_model_ids_from_array(
            models_raw,
            provider="google",
            primary_key="name",
        )
        models: list[str] = []
        for model_id in raw_model_ids:
            normalized_model_id = model_id.removeprefix("models/")
            if normalized_model_id:
                models.append(normalized_model_id)
        return models

    @classmethod
    def _extract_provider_model_ids(cls, payload: JsonValue, provider: str) -> list[str]:
        if provider == "bothub":
            return cls._extract_bothub_model_ids(payload)
        if provider == "github":
            return cls._extract_github_catalog_model_ids(payload)
        if provider == "google":
            return cls._extract_google_model_ids(payload)
        payload_object = require_json_object(payload, f"{provider}.models.response")
        return cls._extract_openai_compatible_model_ids(payload_object, provider)

    @classmethod
    def _extract_bothub_model_ids(cls, payload: JsonValue) -> list[str]:
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            data = payload.get("data")
            if not isinstance(data, list):
                raise ValueError("bothub models response: data must be an array")
            items = data
        else:
            raise ValueError("bothub models response must be object or array")
        return cls._extract_model_ids_from_array(
            items,
            provider="bothub",
            primary_key="name",
            fallback_key="id",
        )

    async def _fetch_bothub_models(self) -> list[str]:
        """Запрос моделей BotHub через общий provider registry."""
        return await self._fetch_configured_provider_models("bothub")

    async def _fetch_openrouter_models(self) -> list[str]:
        """Запрос моделей OpenRouter через общий provider registry."""
        return await self._fetch_configured_provider_models("openrouter")

    async def _fetch_openai_models(self) -> list[str]:
        """Запрос моделей OpenAI через общий provider registry."""
        return await self._fetch_configured_provider_models("openai")

    @staticmethod
    def _provider_models_url(provider: str, cfg: _ConfiguredLLMProvider) -> str:
        configured_models_url = cfg.models_url
        if isinstance(configured_models_url, str) and configured_models_url.strip():
            return configured_models_url.strip()
        if provider == "yandex":
            yandex_config = cast(YandexLLMProviderConfig, cfg)
            return f"{yandex_llm_openai_root_from_provider_cfg(yandex_config).rstrip('/')}/models"
        configured_base_url = cfg.base_url
        if isinstance(configured_base_url, str) and configured_base_url.strip():
            return f"{configured_base_url.strip().rstrip('/')}/models"
        default_models_url = LLM_PROVIDER_DEFAULT_MODELS_URLS.get(provider)
        if default_models_url is None:
            raise ValueError(f"{provider} models_url не настроен")
        return default_models_url

    @staticmethod
    def _provider_model_list_headers(
        provider: str,
        cfg: _ConfiguredLLMProvider,
    ) -> dict[str, str]:
        api_key = cfg.api_key
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError(f"{provider} API key не настроен")
        headers = {"Content-Type": "application/json"}
        if provider == "yandex":
            yandex_config = cast(YandexLLMProviderConfig, cfg)
            return {
                **yandex_provider_http_headers(yandex_config),
                "Content-Type": "application/json",
            }
        if provider == "google":
            headers["x-goog-api-key"] = api_key.strip()
            return headers
        headers["Authorization"] = f"Bearer {api_key.strip()}"
        if provider == "openrouter":
            openrouter_config = cast(OpenRouterProviderConfig, cfg)
            site_url = openrouter_config.site_url
            site_name = openrouter_config.site_name
            if site_url.strip():
                headers["HTTP-Referer"] = site_url.strip()
            if site_name.strip():
                headers["X-Title"] = site_name.strip()
        if provider == "github":
            github_config = cast(GitHubModelsProviderConfig, cfg)
            api_version = github_config.api_version
            headers["Accept"] = "application/vnd.github+json"
            headers["X-GitHub-Api-Version"] = (
                api_version.strip()
                if api_version.strip()
                else GITHUB_MODELS_API_VERSION
            )
        return headers

    @staticmethod
    def _provider_is_configured(provider: str) -> bool:
        cfg = LLMModelsService._configured_llm_provider(provider)
        if cfg is None or not cfg.api_key:
            return False
        if provider == "yandex":
            yandex_config = cast(YandexLLMProviderConfig, cfg)
            folder_id = yandex_config.folder_id
            return isinstance(folder_id, str) and bool(folder_id.strip())
        if provider in ACCOUNT_FREE_TIER_LLM_PROVIDER_SLUGS:
            smoke_model = cfg.smoke_model
            return isinstance(smoke_model, str) and bool(smoke_model.strip())
        return True

    async def _fetch_configured_provider_models(self, provider: str) -> list[str]:
        """Запрос models catalog для обычного configured LLM provider."""
        if provider not in OPENAI_COMPATIBLE_LLM_PROVIDER_SLUGS:
            logger.warning("Неизвестный провайдер: %s", provider)
            return []
        cfg = self._configured_llm_provider(provider)
        if not self._provider_is_configured(provider):
            logger.warning("%s LLM provider не настроен", provider)
            return []
        if cfg is None:
            raise ValueError(f"{provider} provider config не настроен")

        url = self._provider_models_url(provider, cfg)
        headers = self._provider_model_list_headers(provider, cfg)
        response: httpx.Response | None = None
        for attempt_index in range(3):
            response = await request_with_strategy(
                "GET",
                url,
                headers=headers,
                timeout=30.0,
                strategy=ProxyStrategy.DIRECT_FIRST,
                direct_attempts=3,
                proxy_attempts=3,
            )
            if response.status_code != 429 or attempt_index == 2:
                break
            retry_after = cast(str | None, response.headers.get("retry-after"))
            try:
                retry_delay = float(retry_after) if retry_after is not None else 0.0
            except ValueError:
                retry_delay = 0.0
            await asyncio.sleep(min(max(retry_delay, 1.0 + attempt_index), 5.0))
        if response is None:
            raise RuntimeError(f"{provider} models response не получен")
        _ = response.raise_for_status()
        payload = parse_json_value(response.content, f"{provider}.models.response")
        models = self._extract_provider_model_ids(payload, provider)
        logger.info("%s: получено %d моделей", provider, len(models))
        return models

    async def _fetch_groq_models(self) -> list[str]:
        """Запрос моделей Groq через общий provider registry."""
        return await self._fetch_configured_provider_models("groq")

    async def _fetch_google_models(self) -> list[str]:
        """Запрос моделей Google Gemini API через общий provider registry."""
        return await self._fetch_configured_provider_models("google")

    async def _fetch_github_models(self) -> list[str]:
        """Запрос моделей GitHub Models catalog через общий provider registry."""
        return await self._fetch_configured_provider_models("github")

    async def _fetch_huggingface_models(self) -> list[str]:
        """Запрос моделей Hugging Face Inference Providers router через общий provider registry."""
        return await self._fetch_configured_provider_models("huggingface")

    async def _fetch_deepinfra_models(self) -> list[str]:
        """Запрос моделей DeepInfra через общий provider registry."""
        return await self._fetch_configured_provider_models("deepinfra")

    async def _fetch_yandex_models(self) -> list[str]:
        """Запрос моделей Yandex через общий provider registry."""
        return await self._fetch_configured_provider_models("yandex")

    async def fetch_models_by_provider(self, provider: str) -> list[str]:
        """Запрос моделей от указанного провайдера."""
        normalized_provider = provider.strip()
        if normalized_provider not in OPENAI_COMPATIBLE_LLM_PROVIDER_SLUGS:
            logger.warning("Неизвестный провайдер: %s", provider)
            return []
        return await self._fetch_configured_provider_models(normalized_provider)

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
                _ = await self._repository.set(model)

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
        results: dict[str, int] = {}

        for provider in OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER:
            if self._provider_is_configured(provider):
                results[provider] = await self.sync_models_by_provider(provider)

        total = sum(results.values())
        logger.info(f"Синхронизировано {total} моделей от всех провайдеров: {results}")
        return results

    async def get_models(self) -> list[str | JsonObject]:
        """Возвращает список id моделей текущего провайдера из БД."""
        settings = get_settings()
        return await self.get_models_by_provider(settings.llm.provider)

    async def get_models_by_provider(self, provider: str) -> list[str | JsonObject]:
        """Возвращает список id моделей указанного провайдера из БД."""
        if provider == HUMANITEC_LLM_PROVIDER:
            options = await read_humanitec_llms_model_options(self._redis_client)
            humanitec_models: list[str | JsonObject] = []
            humanitec_models.extend(options)
            return humanitec_models
        models = await self._repository.list_by_provider(provider)
        provider_models: list[str | JsonObject] = []
        provider_models.extend(m.model_id for m in models)
        return provider_models

    @staticmethod
    def get_configured_providers() -> list[str]:
        """Список реально настроенных LLM-провайдеров из conf.json.

        Провайдер считается настроенным, если в `settings.llm.<provider>` присутствует
        api_key; для yandex — ещё и непустой folder_id. humanitec_llm доступен,
        когда включён provider-neutral free pool с настроенным free-candidate provider.
        """
        settings = get_settings()
        configured_providers = [
            provider
            for provider in OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER
            if LLMModelsService._provider_is_configured(provider)
        ]
        providers: list[str] = []
        if (
            settings.llm.platform_free_pool.enabled
            and any(
                provider in configured_providers
                and provider in PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_SLUGS
                for provider in settings.llm.platform_free_pool.providers
            )
        ):
            providers.append(HUMANITEC_LLM_PROVIDER)
        providers.extend(configured_providers)
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

    async def start_platform_free_models_sync(self, interval: int) -> None:
        """Создает recurring schedule обновления Redis platform free-pool."""
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
        """Отменяет recurring schedule синхронизации моделей."""
        if not self._sync_schedule_task_id:
            return
        _ = await self._scheduler_client.cancel_schedule(self._sync_schedule_task_id)
        logger.info(
            "Фоновая синхронизация моделей остановлена (schedule_task_id=%s)",
            self._sync_schedule_task_id,
        )
        self._sync_schedule_task_id = None

    async def stop_platform_free_models_sync(self) -> None:
        """Отменяет recurring schedule обновления Redis platform free-pool."""
        if not self._platform_free_schedule_task_id:
            return
        _ = await self._scheduler_client.cancel_schedule(self._platform_free_schedule_task_id)
        logger.info(
            "Platform free-pool sync остановлен (schedule_task_id=%s)",
            self._platform_free_schedule_task_id,
        )
        self._platform_free_schedule_task_id = None
