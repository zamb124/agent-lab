"""
Сервис для генерации embeddings через OpenRouter и другие совместимые API.

Поддерживает fallback между моделями одной размерности.
Включает billing для учёта использования.
"""

import logging
from collections.abc import AsyncIterator, Sequence
from typing import TYPE_CHECKING, Any, List, Literal, Optional

import tiktoken

from core.context import get_context
from core.http import get_httpx_client
from core.models.billing_models import UsageType

if TYPE_CHECKING:
    from core.billing.service import BillingService

logger = logging.getLogger(__name__)


# Размерности известных моделей
MODEL_DIMENSIONS = {
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
    "qwen/qwen3-embedding-4b": 2560,
    "qwen/qwen3-embedding-8b": 4096,
    "google/gemini-embedding-001": 768,
}


class EmbeddingService:
    """
    Сервис для генерации embeddings.

    Поддерживает:
    - OpenRouter и другие OpenAI-совместимые API (корень ``…/v1`` из конфигурации)
    - Любой OpenAI-совместимый endpoint
    - Fallback между моделями одной размерности
    - Billing для учёта использования
    """

    BATCH_SIZE = 50  # Максимум текстов в одном запросе

    def __init__(
        self,
        api_key: str,
        base_url: str,
        models: Optional[List[str]] = None,
        timeout: int = 15,
        dimension: Optional[int] = None,
        provider: Literal["openrouter", "provider_litserve"] = "openrouter",
        # Billing параметры
        cost_per_1m_tokens: float = 5.0,
        platform_markup: float = 1.1,
        billing_service: Optional["BillingService"] = None,
    ):
        """
        Args:
            api_key: API ключ; для provider_litserve не используется
            base_url: Корень OpenAI-совместимого API (суффикс ``/v1``), из merged-конфига; ``…/embeddings`` добавляется при необходимости
            models: Список моделей для fallback (первая рабочая будет использована)
            timeout: Таймаут запросов
            dimension: Ожидаемая размерность (для валидации)
            provider: openrouter — облачный API; provider_litserve — локальные веса через OpenAI-совместимый шлюз (``/v1/embeddings``)
            cost_per_1m_tokens: Средняя цена за 1M токенов (в рублях)
            platform_markup: Наценка платформы (1.1 = +10%)
            billing_service: Сервис биллинга (опционально)
        """
        if provider != "provider_litserve" and not api_key:
            raise ValueError("API key обязателен для EmbeddingService (кроме provider=provider_litserve)")

        self.api_key = api_key
        self.provider: Literal["openrouter", "provider_litserve"] = provider
        self.timeout = timeout
        self.dimension = dimension

        # Billing
        self.cost_per_1m_tokens = cost_per_1m_tokens
        self.platform_markup = platform_markup
        self.billing_service = billing_service

        # Tokenizer для подсчёта токенов
        self._tokenizer = tiktoken.get_encoding("cl100k_base")

        # Список моделей для fallback
        if models:
            self.models = models
        else:
            self.models = ["openai/text-embedding-3-small"]

        # Текущая активная модель (будет определена при первом запросе)
        self._active_model: Optional[str] = None
        self._active_dimension: Optional[int] = None

        if not str(base_url).strip():
            raise ValueError(
                "EmbeddingService: base_url обязателен; итоговый корень …/v1 задаётся "
                "resolve_rag_embedding_runtime (rag.embedding, llm, provider_litserve) или явно в embedding_config."
            )
        self.api_url = str(base_url).strip().rstrip("/")
        if not self.api_url.endswith("/embeddings"):
            self.api_url = f"{self.api_url}/embeddings"

        logger.info(
            "EmbeddingService: provider=%s models=%s url=%s",
            self.provider,
            self.models,
            self.api_url,
        )

    def runtime_snapshot(self, *, embedding_tokens: int | None = None) -> dict[str, Any]:
        """
        Параметры эмбеддинга после вызова ``generate_embeddings``
        (``model_used`` — фактически выбранная модель).
        """
        snap: dict[str, Any] = {
            "provider": self.provider,
            "models": list(self.models),
            "model_used": self._active_model or self.models[0],
            "dimension_config": self.dimension,
            "output_dimension": self._active_dimension,
            "api_url": self.api_url,
            "timeout_seconds": self.timeout,
        }
        if embedding_tokens is not None:
            snap["embedding_tokens"] = int(embedding_tokens)
        return snap

    @property
    def model(self) -> str:
        """Текущая активная модель"""
        return self._active_model or self.models[0]

    def count_tokens(self, texts: List[str]) -> int:
        """Подсчитывает количество токенов в текстах"""
        total = 0
        for text in texts:
            total += len(self._tokenizer.encode(text))
        return total

    def calculate_cost(self, token_count: int) -> float:
        """
        Рассчитывает стоимость embedding.

        cost = (tokens / 1M) * cost_per_1m * platform_markup
        """
        base_cost = (token_count / 1_000_000) * self.cost_per_1m_tokens
        return base_cost * self.platform_markup

    def _get_billing_service(self):
        """Получает billing_service из контекста или параметра инициализации"""
        if self.billing_service:
            return self.billing_service

        from core.billing import get_billing_service
        return get_billing_service()

    async def _record_usage(self, token_count: int, cost: float):
        """Записывает использование embedding в billing"""
        context = get_context()

        # Проверяем контекст пользователя - без user/company это системная операция
        if not context or not context.user or not context.active_company:
            logger.debug("Системная операция embedding без контекста пользователя")
            return

        # Есть user/company - billing обязателен
        billing = self.billing_service or self._get_billing_service()

        logger.info(f"💰 Embedding billing: записываем {token_count} tokens, cost={cost:.4f}₽")

        await billing.record_usage(
            user=context.user,
            company=context.active_company,
            resource_name=f"embedding:{self._active_model or 'unknown'}",
            cost=cost,
            usage_type=UsageType.EMBEDDING_REQUEST,
            quantity=token_count,
            metadata={
                "model": self._active_model,
                "tokens": token_count,
                "cost_per_1m_tokens": self.cost_per_1m_tokens,
                "platform_markup": self.platform_markup,
            }
        )

    async def _try_model(self, model: str, texts: List[str]) -> Optional[List[List[float]]]:
        """
        Пробует сгенерировать embeddings с указанной моделью.

        Returns:
            Список embeddings или None если модель недоступна
        """
        headers = {
            "Content-Type": "application/json",
            "HTTP-Referer": "https://humanitec.ru",
            "X-Title": "Humanitec RAG",
        }
        if self.provider != "provider_litserve":
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            # Внешние OpenAI-compatible API (OpenRouter и т.д.) — без прокси: иначе
            # SmartProxyClient шлёт openrouter.ai через proxy.get_next_proxy(), что часто
            # даёт ConnectError/пустое исключение и «All embedding models failed».
            async with get_httpx_client(
                timeout=self.timeout,
                proxy=False,
            ) as client:
                response = await client.post(
                    self.api_url,
                    headers=headers,
                    json={
                        "model": model,
                        "input": texts,
                    },
                )

                if response.status_code != 200:
                    error_text = response.text[:500]
                    logger.warning(
                        "Model %s returned %s: %s",
                        model,
                        response.status_code,
                        error_text,
                    )
                    return None

                data = response.json()

                if "data" not in data:
                    logger.warning(
                        "Model %s returned unexpected response: %s",
                        model,
                        str(data)[:500],
                    )
                    return None

                embeddings = [item["embedding"] for item in data["data"]]
                if not embeddings and texts:
                    logger.warning(
                        "Model %s returned HTTP 200 but empty data[] for %s inputs",
                        model,
                        len(texts),
                    )
                    return None

                # Проверяем размерность
                if embeddings and self.dimension:
                    actual_dim = len(embeddings[0])
                    if actual_dim != self.dimension:
                        logger.warning(
                            "Model %s returned dimension %s, expected %s",
                            model,
                            actual_dim,
                            self.dimension,
                        )
                        return None

                return embeddings

        except Exception as e:
            logger.warning(
                "Model %s embedding request failed: %s",
                model,
                repr(e),
            )
            return None

    async def _generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Генерирует embeddings для одного батча текстов с fallback.
        """
        # Если уже есть активная модель, пробуем её первой
        if self._active_model:
            result = await self._try_model(self._active_model, texts)
            if result:
                return result
            # Активная модель перестала работать
            logger.warning(f"Active model {self._active_model} failed, trying fallback")
            self._active_model = None

        # Пробуем модели по порядку
        for model in self.models:
            result = await self._try_model(model, texts)
            if result:
                if self._active_model != model:
                    logger.info(f"Switched to embedding model: {model}")
                    self._active_model = model
                    self._active_dimension = len(result[0]) if result else None
                return result

        # Все модели недоступны
        if self.provider == "provider_litserve":
            hint = (
                f"Проверьте provider_litserve и URL {self.api_url!r} "
                "(provider_litserve.api.base_url, корень …/v1)."
            )
        else:
            hint = "Check API key and model availability."
        raise ValueError(f"All embedding models failed: {self.models}. {hint}")

    async def generate_embedding(self, text: str) -> List[float]:
        """
        Генерирует embedding для одного текста.

        Args:
            text: Текст для embedding

        Returns:
            Вектор embedding
        """
        embeddings = await self.generate_embeddings([text])
        return embeddings[0]

    async def iter_embedding_batches(
        self,
        texts: Sequence[str],
    ) -> AsyncIterator[tuple[int, List[str], List[List[float]]]]:
        """
        Последовательные HTTP-батчи эмбеддингов без накопления всех векторов в одном списке.

        Yields:
            (start_index, batch_texts, batch_embeddings) — индексы в ``texts``, срез текстов батча,
            векторы в том же порядке.

        Billing не вызывается — после полного прохода вызовите ``apply_embedding_billing``.
        """
        n = len(texts)
        if n == 0:
            return
        total_batches = (n + self.BATCH_SIZE - 1) // self.BATCH_SIZE
        for start in range(0, n, self.BATCH_SIZE):
            end = min(start + self.BATCH_SIZE, n)
            batch = [texts[i] for i in range(start, end)]
            batch_num = start // self.BATCH_SIZE + 1
            logger.debug(f"Batch {batch_num}/{total_batches}: {len(batch)} текстов")

            batch_embeddings = await self._generate_embeddings_batch(batch)
            yield start, batch, batch_embeddings

    async def apply_embedding_billing(self, token_count: int) -> None:
        """Запись биллинга после ``iter_embedding_batches`` (один раз на документ)."""
        if token_count <= 0:
            return
        cost = self.calculate_cost(token_count)
        await self._record_usage(token_count, cost)

    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
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
        logger.info(f"Генерация embeddings для {len(texts)} текстов ({token_count} токенов)")

        all_embeddings: List[List[float]] = []
        async for _start, _batch, batch_embeddings in self.iter_embedding_batches(texts):
            all_embeddings.extend(batch_embeddings)

        cost = self.calculate_cost(token_count)
        await self._record_usage(token_count, cost)

        logger.info(
            f"Сгенерировано {len(all_embeddings)} embeddings "
            f"(model={self._active_model}, tokens={token_count}, cost={cost:.4f}₽)"
        )
        return all_embeddings

    def get_embedding_dimension(self) -> int:
        """
        Возвращает размерность embedding для текущей модели.

        Returns:
            Размерность вектора
        """
        if self._active_dimension:
            return self._active_dimension

        if self.dimension:
            return self.dimension

        # Используем известные размерности
        for model in self.models:
            if model in MODEL_DIMENSIONS:
                return MODEL_DIMENSIONS[model]

        return 1536  # Default fallback

    def get_active_model(self) -> Optional[str]:
        """Возвращает текущую активную модель (или None если ещё не определена)"""
        return self._active_model
