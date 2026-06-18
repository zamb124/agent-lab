from __future__ import annotations

import asyncio
import re
from abc import ABC
from typing import cast, override
from urllib.parse import quote

import httpx

from core.ai.adapters.base import AIProviderAdapter
from core.ai.models import AIModelRecord, AIRuntimeEndpoint
from core.ai.providers import (
    ACCOUNT_FREE_TIER_LLM_PROVIDER_SLUGS,
    GITHUB_MODELS_API_VERSION,
    LLM_CAPABILITIES,
    LLM_PROVIDER_DEFAULT_MODELS_URLS,
    PROVIDER_LITSERVE,
    AICapability,
)
from core.config import BaseSettings, get_settings
from core.config.llm_openai_compat import (
    resolve_provider_openai_v1_base_url,
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
from core.logging import get_logger
from core.rag.openai_http_contracts import PROVIDER_LITSERVE_PLACEHOLDER_BEARER
from core.types import JsonArray, JsonObject, JsonValue, parse_json_value, require_json_object

logger = get_logger(__name__)

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

_DIMENSION_RE = re.compile(
    r"(?:vector\s+dimension|embedding\s+dimension|dimension|dimensions)\D{0,16}(\d{2,5})",
    re.IGNORECASE,
)
_EMBEDDING_MODEL_ID_MARKERS = (
    "embedding",
    "embed",
    "bge-m3",
    "e5-",
    "gte-",
    "gte_",
    "gte/",
)
_RERANK_MODEL_ID_MARKERS = ("rerank", "reranker")
_MAX_EMBEDDING_PROBES_PER_PROVIDER = 5
_EMBEDDING_PROBE_TIMEOUT_SECONDS = 8.0


class AIProviderAdapterError(RuntimeError):
    """Provider catalog discovery failed before records could be normalized."""


class BaseModelCatalogAdapter(AIProviderAdapter, ABC):
    def __init__(self, settings: BaseSettings | None = None) -> None:
        self._settings: BaseSettings = settings or get_settings()

    @override
    def runtime_endpoint(self, capability: AICapability) -> AIRuntimeEndpoint:
        base_url = resolve_provider_openai_v1_base_url(self._settings.llm, self.provider)
        endpoint_url = f"{base_url.rstrip('/')}/rerank" if capability == AICapability.RERANK else None
        return AIRuntimeEndpoint(
            provider=self.provider,
            capability=capability,
            base_url=base_url,
            endpoint_url=endpoint_url,
            headers=cast(JsonObject, self.provider_model_list_headers()),
        )

    @staticmethod
    def _json_str(value: JsonValue) -> str | None:
        if not isinstance(value, str):
            return None
        stripped = value.strip()
        if not stripped:
            return None
        return stripped

    @staticmethod
    def _json_int(value: JsonValue | None) -> int | None:
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        return None

    @staticmethod
    def _json_string_tuple(value: JsonValue | None) -> tuple[str, ...]:
        if not isinstance(value, list):
            return ()
        values: list[str] = []
        for item in value:
            if isinstance(item, str):
                cleaned = item.strip()
                if cleaned:
                    values.append(cleaned)
        return tuple(sorted(set(values)))

    @staticmethod
    def _merge_string_tuples(left: tuple[str, ...], right: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted({*left, *right}))

    @staticmethod
    def _merge_capability_tuples(
        left: tuple[AICapability, ...],
        right: tuple[AICapability, ...],
    ) -> tuple[AICapability, ...]:
        values = {*left, *right}
        return tuple(cap for cap in AICapability if cap in values)

    @staticmethod
    def _json_object(value: JsonValue | None) -> JsonObject:
        if isinstance(value, dict):
            return require_json_object(value, "provider.model.object")
        return {}

    @staticmethod
    def _float_zero(value: JsonValue | None) -> bool:
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            return False
        try:
            return float(value) == 0.0
        except ValueError:
            return False

    @classmethod
    def _pricing_is_free(cls, item: JsonObject) -> bool | None:
        pricing_raw = item.get("pricing")
        if not isinstance(pricing_raw, dict):
            return None
        pricing = require_json_object(pricing_raw, "provider.model.pricing")
        price_fields = ("prompt", "completion", "input", "output", "request", "image")
        present_values = [pricing.get(field) for field in price_fields if field in pricing]
        if not present_values:
            return None
        return all(cls._float_zero(value) for value in present_values)

    @classmethod
    def _dimension_from_item(cls, item: JsonObject) -> int | None:
        for key in (
            "native_dimension",
            "embedding_dimension",
            "embedding_dimensions",
            "dimension",
            "dimensions",
            "storage_dimension",
        ):
            value = cls._json_int(item.get(key))
            if value is not None:
                return value
        description = cls._json_str(item.get("description"))
        if description is None:
            return None
        match = _DIMENSION_RE.search(description)
        if match is None:
            return None
        return int(match.group(1))

    def _storage_dimension_for_embedding(self, native_dimension: int | None) -> int | None:
        if native_dimension is None:
            return None
        storage_dimension = self._settings.rag.embedding.api.dimension
        if native_dimension == storage_dimension:
            return storage_dimension
        return None

    @classmethod
    def _capabilities_from_model_item(
        cls,
        *,
        model_id: str,
        input_modalities: tuple[str, ...],
        output_modalities: tuple[str, ...],
        supported_generation_methods: tuple[str, ...],
    ) -> tuple[AICapability, ...]:
        model_id_lower = model_id.lower()
        input_set = {value.lower() for value in input_modalities}
        output_set = {value.lower() for value in output_modalities}
        method_set = {value.lower() for value in supported_generation_methods}

        capabilities: set[AICapability] = set()
        if (
            "embedding" in output_set
            or "embeddings" in output_set
            or "vector" in output_set
            or "vectors" in output_set
            or "embedcontent" in method_set
            or any(marker in model_id_lower for marker in _EMBEDDING_MODEL_ID_MARKERS)
        ):
            capabilities.add(AICapability.EMBEDDING)

        if (
            "scores" in output_set
            or "rerank" in output_set
            or any(marker in model_id_lower for marker in _RERANK_MODEL_ID_MARKERS)
        ):
            capabilities.add(AICapability.RERANK)

        if "image" in output_set:
            capabilities.add(AICapability.IMAGE_GEN)

        can_generate_text = (
            "text" in output_set
            or "generatecontent" in method_set
            or (not output_set and not capabilities)
        )
        if can_generate_text and not capabilities.intersection({AICapability.EMBEDDING, AICapability.RERANK}):
            capabilities.update(
                {
                    AICapability.LLM_CHAT,
                    AICapability.LLM_SUMMARIZE,
                    AICapability.LLM_FORMAT_MARKDOWN,
                    AICapability.LLM_CODEGEN,
                }
            )
            if "image" in input_set:
                capabilities.add(AICapability.LLM_VISION)

        if not capabilities:
            capabilities.update(LLM_CAPABILITIES)

        return tuple(cap for cap in AICapability if cap in capabilities)

    def _record_from_model_item(
        self,
        item: JsonObject,
        *,
        provider: str,
        primary_key: str,
        fallback_key: str | None = None,
        forced_capabilities: tuple[AICapability, ...] = (),
        forced_input_modalities: tuple[str, ...] = (),
        forced_output_modalities: tuple[str, ...] = (),
    ) -> AIModelRecord | None:
        model_id = self._model_id_from_object(
            item,
            primary_key=primary_key,
            fallback_key=fallback_key,
        )
        if model_id is None:
            return None
        if provider == "google":
            model_id = model_id.removeprefix("models/")
        architecture = self._json_object(item.get("architecture"))
        input_modalities = self._json_string_tuple(architecture.get("input_modalities"))
        output_modalities = self._json_string_tuple(architecture.get("output_modalities"))
        if forced_input_modalities:
            input_modalities = self._merge_string_tuples(input_modalities, forced_input_modalities)
        if forced_output_modalities:
            output_modalities = self._merge_string_tuples(output_modalities, forced_output_modalities)
        supported_parameters = self._json_string_tuple(item.get("supported_parameters"))
        supported_generation_methods = self._json_string_tuple(item.get("supportedGenerationMethods"))
        if not supported_generation_methods:
            supported_generation_methods = self._json_string_tuple(item.get("supported_generation_methods"))

        explicit_capabilities: list[AICapability] = []
        for raw_capability in self._json_string_tuple(item.get("capabilities")):
            try:
                explicit_capabilities.append(AICapability(raw_capability))
            except ValueError:
                continue
        if forced_capabilities:
            capabilities = forced_capabilities
        elif explicit_capabilities:
            capabilities = tuple(explicit_capabilities)
        else:
            capabilities = self._capabilities_from_model_item(
                model_id=model_id,
                input_modalities=input_modalities,
                output_modalities=output_modalities,
                supported_generation_methods=supported_generation_methods,
            )
        native_dimension = self._dimension_from_item(item) if AICapability.EMBEDDING in capabilities else None
        storage_dimension = self._storage_dimension_for_embedding(native_dimension)
        mrl_output_dimension = self._json_int(item.get("mrl_output_dimension"))
        if mrl_output_dimension is not None and storage_dimension is None:
            storage_dimension = self._settings.rag.embedding.api.dimension

        supports_tools = "tools" in supported_parameters or "tool_choice" in supported_parameters
        supports_structured_output = (
            "response_format" in supported_parameters
            or "structured_outputs" in supported_parameters
            or "json_schema" in supported_parameters
        )
        is_free = self._pricing_is_free(item)
        raw = require_json_object(item, f"{provider}.model.{model_id}")
        return AIModelRecord(
            model_id=model_id,
            provider=provider,
            capabilities=capabilities,
            input_modalities=input_modalities,
            output_modalities=output_modalities,
            supported_parameters=supported_parameters,
            context_length=self._json_int(item.get("context_length")) or self._json_int(item.get("inputTokenLimit")),
            created=self._json_int(item.get("created")),
            native_dimension=native_dimension,
            storage_dimension=storage_dimension,
            mrl_output_dimension=mrl_output_dimension,
            supports_tools=supports_tools,
            supports_structured_output=supports_structured_output,
            is_free=is_free,
            free_reason="zero_price_catalog" if is_free else None,
            metadata_status="verified" if native_dimension is not None else "discovered",
            raw=raw,
        )

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

    def _records_from_array(
        self,
        items: JsonArray,
        *,
        provider: str,
        primary_key: str,
        fallback_key: str | None = None,
        forced_capabilities: tuple[AICapability, ...] = (),
        forced_input_modalities: tuple[str, ...] = (),
        forced_output_modalities: tuple[str, ...] = (),
    ) -> list[AIModelRecord]:
        records: list[AIModelRecord] = []
        for idx, raw_item in enumerate(items):
            item = require_json_object(raw_item, f"{provider}.models[{idx}]")
            record = self._record_from_model_item(
                item,
                provider=provider,
                primary_key=primary_key,
                fallback_key=fallback_key,
                forced_capabilities=forced_capabilities,
                forced_input_modalities=forced_input_modalities,
                forced_output_modalities=forced_output_modalities,
            )
            if record is not None:
                records.append(record)
        return records

    def _extract_openai_compatible_model_records(
        self,
        payload: JsonObject,
        provider: str,
    ) -> list[AIModelRecord]:
        data = payload.get("data")
        if not isinstance(data, list):
            raise ValueError(f"{provider} models response: data must be an array")
        return self._records_from_array(data, provider=provider, primary_key="id")

    def _extract_bothub_model_records(self, payload: JsonValue) -> list[AIModelRecord]:
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            data = payload.get("data")
            if not isinstance(data, list):
                raise ValueError("bothub models response: data must be an array")
            items = data
        else:
            raise ValueError("bothub models response must be object or array")
        return self._records_from_array(items, provider="bothub", primary_key="name", fallback_key="id")

    def _extract_github_catalog_model_records(self, payload: JsonValue) -> list[AIModelRecord]:
        if not isinstance(payload, list):
            raise ValueError("github models catalog response must be an array")
        return self._records_from_array(payload, provider="github", primary_key="id")

    def _extract_provider_model_records(self, payload: JsonValue, provider: str) -> list[AIModelRecord]:
        if provider == "bothub":
            return self._extract_bothub_model_records(payload)
        if provider == "github":
            return self._extract_github_catalog_model_records(payload)
        payload_object = require_json_object(payload, f"{provider}.models.response")
        return self._extract_openai_compatible_model_records(payload_object, provider)

    def _merge_model_records(self, records: list[AIModelRecord]) -> list[AIModelRecord]:
        merged: dict[str, AIModelRecord] = {}
        for record in records:
            existing = merged.get(record.model_id)
            if existing is None:
                merged[record.model_id] = record
                continue
            if existing.is_free is True or record.is_free is True:
                is_free: bool | None = True
            elif existing.is_free is None and record.is_free is None:
                is_free = None
            else:
                is_free = False
            raw: JsonObject
            if existing.raw == record.raw:
                raw = existing.raw
            else:
                raw = {"sources": [existing.raw, record.raw]}
            merged[record.model_id] = existing.model_copy(
                update={
                    "capabilities": self._merge_capability_tuples(existing.capabilities, record.capabilities),
                    "input_modalities": self._merge_string_tuples(existing.input_modalities, record.input_modalities),
                    "output_modalities": self._merge_string_tuples(existing.output_modalities, record.output_modalities),
                    "supported_parameters": self._merge_string_tuples(
                        existing.supported_parameters,
                        record.supported_parameters,
                    ),
                    "context_length": record.context_length or existing.context_length,
                    "created": existing.created or record.created,
                    "native_dimension": record.native_dimension or existing.native_dimension,
                    "storage_dimension": record.storage_dimension or existing.storage_dimension,
                    "mrl_output_dimension": record.mrl_output_dimension or existing.mrl_output_dimension,
                    "supports_tools": existing.supports_tools or record.supports_tools,
                    "supports_structured_output": (
                        existing.supports_structured_output or record.supports_structured_output
                    ),
                    "is_free": is_free,
                    "free_reason": existing.free_reason or record.free_reason,
                    "metadata_status": (
                        "verified"
                        if existing.metadata_status == "verified" or record.metadata_status == "verified"
                        else "discovered"
                    ),
                    "raw": raw,
                }
            )
        return list(merged.values())

    async def _fetch_provider_catalog_payload(
        self,
        *,
        url: str,
        headers: dict[str, str],
        response_label: str,
    ) -> JsonValue:
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
            raise AIProviderAdapterError(f"{self.provider} models response не получен")
        _ = response.raise_for_status()
        return parse_json_value(response.content, response_label)

    def _configured_llm_provider(self) -> _ConfiguredLLMProvider | None:
        llm = self._settings.llm
        if self.provider == "openrouter":
            return llm.openrouter
        if self.provider == "bothub":
            return llm.bothub
        if self.provider == "groq":
            return llm.groq
        if self.provider == "google":
            return llm.google
        if self.provider == "github":
            return llm.github
        if self.provider == "huggingface":
            return llm.huggingface
        if self.provider == "deepinfra":
            return llm.deepinfra
        if self.provider == "openai":
            return llm.openai
        if self.provider == "yandex":
            return llm.yandex
        return None

    def _provider_models_url(self, cfg: _ConfiguredLLMProvider) -> str:
        configured_models_url = cfg.models_url
        if isinstance(configured_models_url, str) and configured_models_url.strip():
            return configured_models_url.strip()
        if self.provider == "yandex":
            yandex_config = cast(YandexLLMProviderConfig, cfg)
            return f"{yandex_llm_openai_root_from_provider_cfg(yandex_config).rstrip('/')}/models"
        configured_base_url = cfg.base_url
        if isinstance(configured_base_url, str) and configured_base_url.strip():
            return f"{configured_base_url.strip().rstrip('/')}/models"
        default_models_url = LLM_PROVIDER_DEFAULT_MODELS_URLS.get(self.provider)
        if default_models_url is None:
            raise ValueError(f"{self.provider} models_url не настроен")
        return default_models_url

    def provider_model_list_headers(self) -> dict[str, str]:
        cfg = self._configured_llm_provider()
        if cfg is None:
            raise ValueError(f"{self.provider} provider config не настроен")
        api_key = cfg.api_key
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError(f"{self.provider} API key не настроен")
        headers = {"Content-Type": "application/json"}
        if self.provider == "yandex":
            yandex_config = cast(YandexLLMProviderConfig, cfg)
            return {
                **yandex_provider_http_headers(yandex_config),
                "Content-Type": "application/json",
            }
        headers["Authorization"] = f"Bearer {api_key.strip()}"
        if self.provider == "openrouter":
            openrouter_config = cast(OpenRouterProviderConfig, cfg)
            site_url = openrouter_config.site_url
            site_name = openrouter_config.site_name
            if site_url.strip():
                headers["HTTP-Referer"] = site_url.strip()
            if site_name.strip():
                headers["X-Title"] = site_name.strip()
        if self.provider == "github":
            github_config = cast(GitHubModelsProviderConfig, cfg)
            api_version = github_config.api_version
            headers["Accept"] = "application/vnd.github+json"
            headers["X-GitHub-Api-Version"] = (
                api_version.strip()
                if api_version.strip()
                else GITHUB_MODELS_API_VERSION
            )
        return headers

    @override
    def is_configured(self) -> bool:
        if self.provider == PROVIDER_LITSERVE:
            try:
                _ = self._provider_litserve_openai_v1_base_url()
            except (AttributeError, ValueError):
                return False
            return True
        cfg = self._configured_llm_provider()
        if cfg is None or not cfg.api_key:
            return False
        if self.provider == "yandex":
            yandex_config = cast(YandexLLMProviderConfig, cfg)
            folder_id = yandex_config.folder_id
            return isinstance(folder_id, str) and bool(folder_id.strip())
        if self.provider in ACCOUNT_FREE_TIER_LLM_PROVIDER_SLUGS:
            smoke_model = cfg.smoke_model
            return isinstance(smoke_model, str) and bool(smoke_model.strip())
        return True

    def embedding_probe_url(self) -> str:
        if self.provider == PROVIDER_LITSERVE:
            return f"{self._provider_litserve_openai_v1_base_url().rstrip('/')}/embeddings"
        return f"{resolve_provider_openai_v1_base_url(self._settings.llm, self.provider).rstrip('/')}/embeddings"

    def embedding_probe_headers(self) -> dict[str, str]:
        if self.provider == PROVIDER_LITSERVE:
            return self._provider_litserve_model_list_headers()
        cfg = self._configured_llm_provider()
        if cfg is None:
            raise ValueError(f"{self.provider} provider config не настроен")
        if self.provider == "google":
            api_key = (cfg.api_key or "").strip()
            if not api_key:
                raise ValueError("google provider api_key не настроен")
            return {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
        return self.provider_model_list_headers()

    def embedding_probe_timeout_seconds(self) -> float:
        return _EMBEDDING_PROBE_TIMEOUT_SECONDS

    @staticmethod
    def _provider_litserve_model_list_headers() -> dict[str, str]:
        return {
            "Authorization": f"Bearer {PROVIDER_LITSERVE_PLACEHOLDER_BEARER}",
            "Content-Type": "application/json",
        }

    def _provider_litserve_openai_v1_base_url(self) -> str:
        return self._settings.provider_litserve.resolve_openai_v1_base_url()

    @staticmethod
    def _huggingface_feature_extraction_probe_url(model_id: str) -> str:
        model_path = quote(model_id, safe="")
        return (
            "https://router.huggingface.co/hf-inference/models/"
            f"{model_path}/pipeline/feature-extraction"
        )

    @classmethod
    def _dimension_from_embedding_payload(cls, value: JsonValue) -> int | None:
        if not isinstance(value, list) or not value:
            return None
        if all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value):
            return len(value)
        first = value[0]
        if isinstance(first, list):
            return cls._dimension_from_embedding_payload(first)
        return None

    @override
    async def probe_embedding_dimension(self, model_id: str) -> int | None:
        if self.provider == "huggingface":
            return await self._probe_huggingface_embedding_dimension(model_id)
        try:
            response = await request_with_strategy(
                "POST",
                self.embedding_probe_url(),
                headers=self.embedding_probe_headers(),
                json={"model": model_id, "input": "dimension probe"},
                timeout=self.embedding_probe_timeout_seconds(),
                strategy=ProxyStrategy.DIRECT_ONLY,
                direct_attempts=1,
            )
        except (httpx.HTTPError, OSError, ValueError) as exc:
            logger.info(
                "model_catalog.embedding_probe_failed",
                provider=self.provider,
                model_id=model_id,
                error=str(exc),
            )
            return None
        if response.status_code != 200:
            logger.info(
                "model_catalog.embedding_probe_rejected",
                provider=self.provider,
                model_id=model_id,
                status_code=response.status_code,
            )
            return None
        payload = parse_json_value(response.content, f"{self.provider}.embedding_probe.response")
        payload_object = require_json_object(payload, f"{self.provider}.embedding_probe.response")
        data = payload_object.get("data")
        if not isinstance(data, list) or not data:
            return None
        first = require_json_object(data[0], f"{self.provider}.embedding_probe.data[0]")
        embedding = first.get("embedding")
        if not isinstance(embedding, list):
            return None
        return len(embedding)

    async def _probe_huggingface_embedding_dimension(self, model_id: str) -> int | None:
        try:
            response = await request_with_strategy(
                "POST",
                self._huggingface_feature_extraction_probe_url(model_id),
                headers=self.embedding_probe_headers(),
                json={"inputs": "dimension probe"},
                timeout=_EMBEDDING_PROBE_TIMEOUT_SECONDS,
                strategy=ProxyStrategy.DIRECT_ONLY,
                direct_attempts=1,
            )
        except (httpx.HTTPError, OSError, ValueError) as exc:
            logger.info(
                "model_catalog.embedding_probe_failed",
                provider="huggingface",
                model_id=model_id,
                error=str(exc),
            )
            return None
        if response.status_code != 200:
            logger.info(
                "model_catalog.embedding_probe_rejected",
                provider="huggingface",
                model_id=model_id,
                status_code=response.status_code,
            )
            return None
        payload = parse_json_value(response.content, "huggingface.embedding_probe.response")
        return self._dimension_from_embedding_payload(payload)

    async def _probe_embedding_dimensions(
        self,
        records: list[AIModelRecord],
    ) -> list[AIModelRecord]:
        updated = list(records)
        probe_indexes: list[int] = []
        for index, record in enumerate(records):
            if AICapability.EMBEDDING not in record.capabilities or record.native_dimension is not None:
                continue
            if len(probe_indexes) >= _MAX_EMBEDDING_PROBES_PER_PROVIDER:
                break
            probe_indexes.append(index)
        if not probe_indexes:
            return updated

        dimensions = await asyncio.gather(
            *(self.probe_embedding_dimension(records[index].model_id) for index in probe_indexes)
        )
        for index, dimension in zip(probe_indexes, dimensions, strict=True):
            if dimension is None:
                continue
            updated[index] = records[index].model_copy(
                update={
                    "native_dimension": dimension,
                    "storage_dimension": self._storage_dimension_for_embedding(dimension),
                    "metadata_status": "verified",
                }
            )
        return updated


__all__ = [
    "AIProviderAdapterError",
    "BaseModelCatalogAdapter",
]
