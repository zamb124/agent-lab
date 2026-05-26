"""
Сервис для генерации embeddings через OpenAI-совместимый POST .../embeddings
(OpenRouter, локальный provider_litserve и др.).

Биллинг: span'ы с billing_pending_settlement — фоновая джоба settlement.
"""

from __future__ import annotations

import math
from typing import ClassVar

import httpx
import tiktoken
from pydantic import Field, ValidationError

import core.tracing.attributes as trace_attributes
from core.billing import get_billing_service
from core.billing.service import BALANCE_BLOCK_OPERATION_EMBEDDING
from core.context import get_context
from core.http import ProxyStrategy, get_httpx_client
from core.logging import get_logger
from core.models import StrictBaseModel
from core.models.billing_models import UsageType
from core.tracing.operation_span import traced_operation
from core.types import JsonObject, OtelAttributeValue

logger = get_logger(__name__)
# Размерности известных моделей
MODEL_DIMENSIONS: dict[str, int] = {
    # 1536
    "openai/text-embedding-3-small": 1536,
    "openai/text-embedding-3-large": 3072,
    "openai/text-embedding-ada-002": 1536,
    "mistralai/codestral-embed-2505": 1536,
    # 1024
    "mistralai/mistral-embed-2312": 1024,
    "baai/bge-m3": 1024,
    "intfloat/multilingual-e5-large": 1024,
    "thenlper/gte-large": 1024,
    "intfloat/e5-large-v2": 1024,
    "baai/bge-large-en-v1.5": 1024,
    # 768
    "thenlper/gte-base": 768,
    "intfloat/e5-base-v2": 768,
    "baai/bge-base-en-v1.5": 768,
    "sentence-transformers/multi-qa-mpnet-base-dot-v1": 768,
    "sentence-transformers/all-mpnet-base-v2": 768,
    # 384
    "sentence-transformers/paraphrase-minilm-l6-v2": 384,
    "sentence-transformers/all-minilm-l12-v2": 384,
    "sentence-transformers/all-minilm-l6-v2": 384,
    # Large
    "qwen/qwen3-embedding-0.6b": 1024,
    "google/gemini-embedding-001": 768,
}


class EmbeddingResponseItem(StrictBaseModel):
    embedding: list[float] = Field(min_length=1)


class EmbeddingResponsePayload(StrictBaseModel):
    data: list[EmbeddingResponseItem]


class EmbeddingService:
    """
    Сервис для генерации embeddings.

    Поддерживает:
    - OpenRouter API (по умолчанию)
    - Любой OpenAI-совместимый API
    """

    OPENROUTER_URL: ClassVar[str] = "https://openrouter.ai/api/v1/embeddings"
    BATCH_SIZE: ClassVar[int] = 50  # Максимум текстов в одном запросе

    def __init__(
        self,
        api_key: str,
        model: str = "openai/text-embedding-3-small",
        base_url: str | None = None,
        timeout: int = 15,
        dimension: int | None = None,
        mrl_output_dimension: int | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("API key обязателен для EmbeddingService")
        if not model.strip():
            raise ValueError("Embedding model обязателен для EmbeddingService")

        self.api_key: str = api_key
        self.model_name: str = model.strip()
        self.timeout: int = timeout
        self.dimension: int | None = dimension
        self.mrl_output_dimension: int | None = mrl_output_dimension

        if mrl_output_dimension is not None and dimension is not None:
            if mrl_output_dimension > dimension:
                message = (
                    f"mrl_output_dimension ({mrl_output_dimension}) "
                    + f"не может быть больше полной размерности ({dimension})"
                )
                raise ValueError(message)

        self._tokenizer: tiktoken.Encoding = tiktoken.get_encoding("cl100k_base")
        self._extra_headers: dict[str, str] = dict(extra_headers) if extra_headers else {}
        self._response_dimension: int | None = None

        if base_url:
            self.api_url: str = base_url.rstrip("/")
            if not self.api_url.endswith("/embeddings"):
                self.api_url = f"{self.api_url}/embeddings"
        else:
            self.api_url = self.OPENROUTER_URL

        logger.info("embedding.service_initialized", model=self.model_name, url=self.api_url)

    def _embedding_lengths_ok(self, model: str, actual_dim: int) -> bool:
        """
        Допускает ответ API полной размерности модели (напр. 1024 у Qwen3-Embedding-0.6B) при хранении MRL N:
        ``dimension`` и ``mrl_output_dimension`` задают размер в pgvector, не длину ответа.
        """
        if self.mrl_output_dimension is not None:
            native_expected = MODEL_DIMENSIONS.get(model)
            if native_expected is not None and actual_dim != native_expected:
                logger.warning(
                    "embedding.model_dimension_mismatch",
                    model=model,
                    actual_dimension=actual_dim,
                    expected_dimension=native_expected,
                    mode="mrl_native",
                )
                return False
            if actual_dim < self.mrl_output_dimension:
                logger.warning(
                    "embedding.model_dimension_too_short",
                    model=model,
                    actual_dimension=actual_dim,
                    mrl_output_dimension=self.mrl_output_dimension,
                )
                return False
            return True
        if self.dimension is not None and actual_dim != self.dimension:
            logger.warning(
                "embedding.model_dimension_mismatch",
                model=model,
                actual_dimension=actual_dim,
                expected_dimension=self.dimension,
                mode="storage_dimension",
            )
            return False
        return True

    @property
    def model(self) -> str:
        """Модель embeddings."""
        return self.model_name

    def count_tokens(self, texts: list[str]) -> int:
        total = 0
        for text in texts:
            total += len(self._tokenizer.encode(text))
        return total

    async def _request_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Запрашивает embeddings у единственного настроенного model."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://humanitec.ru",
            "X-Title": "Humanitec RAG",
        }
        if self._extra_headers:
            headers = {**headers, **self._extra_headers}

        try:
            async with get_httpx_client(
                timeout=self.timeout,
                strategy=ProxyStrategy.SMART,
            ) as client:
                response = await client.post(
                    self.api_url,
                    headers=headers,
                    json={
                        "model": self.model_name,
                        "input": texts,
                    },
                )
        except (httpx.HTTPError, OSError) as exc:
            raise ValueError(f"Embedding request failed for model {self.model_name!r}: {exc}") from exc

        if response.status_code != 200:
            error_text = response.text[:200]
            raise ValueError(
                f"Embedding model {self.model_name!r} returned status {response.status_code}: {error_text}"
            )

        try:
            payload = EmbeddingResponsePayload.model_validate_json(response.text)
        except ValidationError as exc:
            raise ValueError(
                f"Embedding model {self.model_name!r} returned invalid response: {response.text[:200]}"
            ) from exc

        embeddings = [item.embedding for item in payload.data]

        if embeddings and not self._embedding_lengths_ok(self.model_name, len(embeddings[0])):
            raise ValueError(
                f"Embedding model {self.model_name!r} returned vector dimension {len(embeddings[0])}"
            )
        if embeddings:
            self._response_dimension = len(embeddings[0])

        return embeddings

    async def _generate_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """Генерирует embeddings для одного батча текстов."""
        return await self._request_embeddings(texts)

    async def generate_embedding(self, text: str) -> list[float]:
        """
        Генерирует embedding для одного текста.

        Args:
            text: Текст для embedding

        Returns:
            Вектор embedding
        """
        embeddings = await self.generate_embeddings([text])
        return embeddings[0]

    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """
        Генерирует embeddings для списка текстов (batch).
        Автоматически разбивает на батчи если текстов много.

        Args:
            texts: Список текстов

        Returns:
            Список векторов embedding
        """
        if not texts:
            return []

        token_count = self.count_tokens(texts)
        resource_hint = self.model_name

        trace_extra: dict[str, OtelAttributeValue] = {
            trace_attributes.ATTR_EMBED_TEXT_COUNT: len(texts),
            trace_attributes.ATTR_EMBED_BATCH_SIZE: self.BATCH_SIZE,
            trace_attributes.ATTR_LLM_INPUT_TOKENS: token_count,
        }
        actx = get_context()
        if actx is None or actx.active_company is None:
            raise ValueError("Контекст с active_company обязателен для generate_embeddings")
        user_id = str(actx.user.user_id).strip()
        if not user_id:
            raise ValueError("Контекст с user обязателен для generate_embeddings (биллинг и уведомления)")

        await get_billing_service().require_balance_for_billable_operation(
            actx.active_company.company_id,
            user_id,
            operation_code=BALANCE_BLOCK_OPERATION_EMBEDDING,
            notification_service="rag",
        )
        trace_extra[trace_attributes.ATTR_TENANT_COMPANY_ID] = actx.active_company.company_id
        trace_extra[trace_attributes.ATTR_USER_ID] = user_id

        async with traced_operation(
            "rag.embed.batch",
            event_type="rag.embeddings",
            operation_category="embedding",
            billing_usage_type=UsageType.EMBEDDING_REQUEST.value,
            billing_resource_name=f"embedding:{resource_hint}",
            billing_quantity=token_count,
            billing_pending_settlement=True,
            extra_attributes=trace_extra,
        ) as span:
            logger.info(
                "embedding.batch_started",
                text_count=len(texts),
                token_count=token_count,
            )

            all_embeddings: list[list[float]] = []
            total_batches = (len(texts) + self.BATCH_SIZE - 1) // self.BATCH_SIZE

            for i in range(0, len(texts), self.BATCH_SIZE):
                batch = texts[i : i + self.BATCH_SIZE]
                batch_num = i // self.BATCH_SIZE + 1
                logger.debug(
                    "embedding.batch_chunk_started",
                    batch_num=batch_num,
                    total_batches=total_batches,
                    text_count=len(batch),
                )

                batch_embeddings = await self._generate_embeddings_batch(batch)
                all_embeddings.extend(batch_embeddings)

            span.set_attribute(trace_attributes.ATTR_EMBED_MODEL, self.model_name)
            span.set_attribute(
                trace_attributes.ATTR_BILLING_RESOURCE_NAME,
                f"embedding:{self.model_name}",
            )

            logger.info(
                "embedding.batch_finished",
                embedding_count=len(all_embeddings),
                model=self.model_name,
                token_count=token_count,
            )

            if self.mrl_output_dimension is not None and all_embeddings:
                all_embeddings = self._truncate_vectors(all_embeddings)

            return all_embeddings

    def _truncate_vectors(
        self,
        vectors: list[list[float]],
    ) -> list[list[float]]:
        """
        MRL: первые ``mrl_output_dimension`` компонент — L2 по префиксу.

        Если ``dimension == mrl_output_dimension``, в БД пишется плотный вектор длины N.
        Если ``dimension > mrl_output_dimension``, хвост добивается нулями до ``dimension``.
        """
        if self.mrl_output_dimension is None:
            return vectors
        n = self.mrl_output_dimension
        dense_storage = self.dimension is not None and self.dimension == n
        padded: list[list[float]] = []
        for vec in vectors:
            if len(vec) < n:
                raise ValueError(
                    f"Вектор длины {len(vec)} короче mrl_output_dimension ({n})"
                )
            tail: list[float] = vec[:n]
            norm = math.sqrt(sum(value * value for value in tail))
            if norm > 0.0:
                tail = [v / norm for v in tail]
            if dense_storage:
                padded.append(tail)
                continue
            full = self.dimension or self._response_dimension
            if full is None or full <= 0:
                message = (
                    "Для MRL с паддингом задайте dimension в конфиге "
                    + "или выполните запрос к API для определения размерности модели"
                )
                raise ValueError(message)
            if n > full:
                raise ValueError("mrl_output_dimension не может превышать полную размерность вектора")
            padded.append(tail + [0.0] * (full - n))
        return padded

    def get_embedding_dimension(self) -> int:
        """Размерность вектора в pgvector (поле ``dimension`` конфига — размер столбца)."""
        if self.dimension is not None:
            return self.dimension
        if self._response_dimension is not None:
            return self._response_dimension
        if self.model_name in MODEL_DIMENSIONS:
            return MODEL_DIMENSIONS[self.model_name]
        raise ValueError(
            "Не задана размерность embedding: укажите dimension в конфиге или используйте модель из MODEL_DIMENSIONS"
        )

    def get_active_model(self) -> str | None:
        """Возвращает настроенную модель."""
        return self.model_name

    def runtime_snapshot(self, *, embedding_tokens: int) -> JsonObject:
        """Текущее состояние runtime для записи в indexing_runtime.

        Provider определяется по api_url, чтобы не лгать в логах при LitServe.
        """
        url = self.api_url.lower()
        if "openrouter.ai" in url:
            provider = "openrouter"
        elif "8014" in url or "provider_litserve" in url or "provider-litserve" in url:
            provider = "provider_litserve"
        elif "api.openai.com" in url:
            provider = "openai"
        elif "bothub.chat" in url:
            provider = "bothub"
        elif "yandex" in url:
            provider = "yandex"
        else:
            provider = "custom_openai_compatible"
        snap: JsonObject = {
            "provider": provider,
            "api_url": self.api_url,
            "model_used": self.model,
            "dimension": self.get_embedding_dimension(),
            "embedding_tokens": embedding_tokens,
        }
        if self.mrl_output_dimension is not None:
            snap["mrl_output_dimension"] = self.mrl_output_dimension
        return snap
