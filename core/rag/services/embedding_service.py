"""
Сервис для генерации embeddings через OpenAI-совместимый POST .../embeddings
(OpenRouter, локальный provider_litserve и др.).

Поддерживает fallback между моделями одной размерности.
Биллинг: span'ы с billing_pending_settlement — фоновая джоба settlement.
"""

from core.logging import get_logger
import tiktoken
from typing import Any, Dict, List, Optional

from core.billing import get_billing_service
from core.billing.service import BALANCE_BLOCK_OPERATION_EMBEDDING
from core.context import get_context
from core.http import get_httpx_client
from core.models.billing_models import UsageType
from core.tracing import attributes as trace_attributes
from core.tracing.operation_span import traced_operation

logger = get_logger(__name__)
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
    "qwen/qwen3-embedding-0.6b": 1024,
    "google/gemini-embedding-001": 768,
}

class EmbeddingService:
    """
    Сервис для генерации embeddings.
    
    Поддерживает:
    - OpenRouter API (по умолчанию)
    - Любой OpenAI-совместимый API
    - Fallback между моделями одной размерности
    """
    
    OPENROUTER_URL = "https://openrouter.ai/api/v1/embeddings"
    BATCH_SIZE = 50  # Максимум текстов в одном запросе
    
    def __init__(
        self,
        api_key: str,
        models: Optional[List[str]] = None,
        base_url: Optional[str] = None,
        timeout: int = 15,
        dimension: Optional[int] = None,
        mrl_output_dimension: Optional[int] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ):
        if not api_key:
            raise ValueError("API key обязателен для EmbeddingService")
        
        self.api_key = api_key
        self.timeout = timeout
        self.dimension = dimension
        self.mrl_output_dimension = mrl_output_dimension
        
        if mrl_output_dimension is not None and dimension is not None:
            if mrl_output_dimension > dimension:
                raise ValueError(
                    f"mrl_output_dimension ({mrl_output_dimension}) "
                    f"не может быть больше полной размерности ({dimension})"
                )
        
        self._tokenizer = tiktoken.get_encoding("cl100k_base")
        self._extra_headers: Dict[str, str] = dict(extra_headers) if extra_headers else {}
        
        # Список моделей для fallback
        if models:
            self.models = models
        else:
            self.models = ["openai/text-embedding-3-small"]
        
        # Текущая активная модель (будет определена при первом запросе)
        self._active_model: Optional[str] = None
        self._active_dimension: Optional[int] = None
        
        if base_url:
            self.api_url = base_url.rstrip("/")
            if not self.api_url.endswith("/embeddings"):
                self.api_url = f"{self.api_url}/embeddings"
        else:
            self.api_url = self.OPENROUTER_URL
        
        logger.info(f"EmbeddingService: models={self.models}, url={self.api_url}")

    def _embedding_lengths_ok(self, model: str, actual_dim: int) -> bool:
        """
        Допускает ответ API полной размерности модели (напр. 1024 у Qwen3-Embedding-0.6B) при хранении MRL N:
        ``dimension`` и ``mrl_output_dimension`` задают размер в pgvector, не длину ответа.
        """
        if self.mrl_output_dimension is not None:
            native_expected = MODEL_DIMENSIONS.get(model)
            if native_expected is not None and actual_dim != native_expected:
                logger.warning(
                    f"Model {model} returned dimension {actual_dim}, "
                    f"expected native {native_expected} for MRL path"
                )
                return False
            if actual_dim < self.mrl_output_dimension:
                logger.warning(
                    f"Model {model} returned dimension {actual_dim}, "
                    f"shorter than mrl_output_dimension ({self.mrl_output_dimension})"
                )
                return False
            return True
        if self.dimension is not None and actual_dim != self.dimension:
            logger.warning(
                f"Model {model} returned dimension {actual_dim}, "
                f"expected {self.dimension}"
            )
            return False
        return True

    @property
    def model(self) -> str:
        """Текущая активная модель"""
        return self._active_model or self.models[0]
    
    def count_tokens(self, texts: List[str]) -> int:
        total = 0
        for text in texts:
            total += len(self._tokenizer.encode(text))
        return total
    
    async def _try_model(self, model: str, texts: List[str]) -> Optional[List[List[float]]]:
        """
        Пробует сгенерировать embeddings с указанной моделью.
        
        Returns:
            Список embeddings или None если модель недоступна
        """
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
                proxy=True
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
                    error_text = response.text[:200]
                    logger.warning(f"Model {model} returned {response.status_code}: {error_text}")
                    return None
                
                data = response.json()
                
                if "data" not in data:
                    logger.warning(f"Model {model} returned unexpected response: {str(data)[:200]}")
                    return None
                
                embeddings = [item["embedding"] for item in data["data"]]

                if embeddings and not self._embedding_lengths_ok(model, len(embeddings[0])):
                    return None

                return embeddings
                
        except Exception as e:
            logger.warning(f"Model {model} failed: {e}")
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
        
        # Все модели недоступны (endpoint тот же OpenAI-совместимый формат: OpenRouter или LitServe).
        raise ValueError(
            f"All embedding models failed: {self.models}. "
            f"Embeddings URL: {self.api_url}. "
            "Проверьте доступность сервиса, модель и ключ (если провайдер его требует)."
        )
    
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
        resource_hint = self._active_model or (self.models[0] if self.models else "embedding")

        trace_extra: dict[str, Any] = {
            trace_attributes.ATTR_EMBED_TEXT_COUNT: len(texts),
            trace_attributes.ATTR_EMBED_BATCH_SIZE: self.BATCH_SIZE,
            trace_attributes.ATTR_LLM_INPUT_TOKENS: token_count,
        }
        actx = get_context()
        if actx is None or actx.active_company is None:
            raise ValueError("Контекст с active_company обязателен для generate_embeddings")
        if actx.user is None or not str(actx.user.user_id).strip():
            raise ValueError("Контекст с user обязателен для generate_embeddings (биллинг и уведомления)")

        await get_billing_service().require_balance_for_billable_operation(
            actx.active_company.company_id,
            str(actx.user.user_id).strip(),
            operation_code=BALANCE_BLOCK_OPERATION_EMBEDDING,
            notification_service="rag",
        )
        trace_extra[trace_attributes.ATTR_TENANT_COMPANY_ID] = actx.active_company.company_id
        if actx.user is not None and str(actx.user.user_id).strip() != "":
            trace_extra[trace_attributes.ATTR_USER_ID] = str(actx.user.user_id).strip()

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
            logger.info(f"Генерация embeddings для {len(texts)} текстов ({token_count} токенов)")

            all_embeddings: List[List[float]] = []
            total_batches = (len(texts) + self.BATCH_SIZE - 1) // self.BATCH_SIZE

            for i in range(0, len(texts), self.BATCH_SIZE):
                batch = texts[i : i + self.BATCH_SIZE]
                batch_num = i // self.BATCH_SIZE + 1
                logger.debug(f"Batch {batch_num}/{total_batches}: {len(batch)} текстов")

                batch_embeddings = await self._generate_embeddings_batch(batch)
                all_embeddings.extend(batch_embeddings)

            resolved_model = self._active_model or ""
            span.set_attribute(trace_attributes.ATTR_EMBED_MODEL, resolved_model)
            span.set_attribute(
                trace_attributes.ATTR_BILLING_RESOURCE_NAME,
                f"embedding:{resolved_model}",
            )

            logger.info(
                f"Сгенерировано {len(all_embeddings)} embeddings "
                f"(model={self._active_model}, tokens={token_count})"
            )

            if self.mrl_output_dimension is not None and all_embeddings:
                all_embeddings = self._truncate_vectors(all_embeddings)

            return all_embeddings

    def _truncate_vectors(
        self,
        vectors: List[List[float]],
    ) -> List[List[float]]:
        """
        MRL: первые ``mrl_output_dimension`` компонент — L2 по префиксу.

        Если ``dimension == mrl_output_dimension``, в БД пишется плотный вектор длины N без паддинга.
        Если ``dimension > mrl_output_dimension``, хвост добивается нулями до ``dimension`` (legacy).
        """
        if self.mrl_output_dimension is None:
            return vectors
        n = self.mrl_output_dimension
        dense_storage = self.dimension is not None and self.dimension == n
        padded: List[List[float]] = []
        for vec in vectors:
            if len(vec) < n:
                raise ValueError(
                    f"Вектор длины {len(vec)} короче mrl_output_dimension ({n})"
                )
            tail = vec[:n]
            norm = sum(v * v for v in tail) ** 0.5
            if norm > 0.0:
                tail = [v / norm for v in tail]
            if dense_storage:
                padded.append(tail)
                continue
            full = self.dimension or self._active_dimension
            if full is None or full <= 0:
                raise ValueError(
                    "Для MRL с паддингом задайте dimension в конфиге "
                    "или выполните запрос к API для определения размерности модели"
                )
            if n > full:
                raise ValueError("mrl_output_dimension не может превышать полную размерность вектора")
            padded.append(tail + [0.0] * (full - n))
        return padded

    def get_embedding_dimension(self) -> int:
        """Размерность вектора в pgvector (поле ``dimension`` конфига — размер столбца)."""
        if self.dimension is not None:
            return self.dimension
        if self._active_dimension is not None:
            return self._active_dimension
        for model in self.models:
            if model in MODEL_DIMENSIONS:
                return MODEL_DIMENSIONS[model]
        raise ValueError(
            "Не задана размерность embedding: укажите dimension в конфиге или используйте модель из MODEL_DIMENSIONS"
        )
    
    def get_active_model(self) -> Optional[str]:
        """Возвращает текущую активную модель (или None если ещё не определена)"""
        return self._active_model

    def runtime_snapshot(self, *, embedding_tokens: int) -> dict[str, Any]:
        """Текущее состояние runtime для записи в indexing_runtime.

        Provider определяется по api_url, чтобы не лгать в логах при LitServe.
        """
        url = (self.api_url or "").lower()
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
        snap: dict[str, Any] = {
            "provider": provider,
            "api_url": self.api_url,
            "model_used": self.model,
            "dimension": self.get_embedding_dimension(),
            "embedding_tokens": embedding_tokens,
        }
        if self.mrl_output_dimension is not None:
            snap["mrl_output_dimension"] = self.mrl_output_dimension
        return snap
