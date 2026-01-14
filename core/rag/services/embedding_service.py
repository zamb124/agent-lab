"""
Сервис для генерации embeddings через OpenRouter и другие совместимые API.

Поддерживает fallback между моделями одной размерности.
Включает billing для учёта использования.
"""

import logging
import tiktoken
from typing import List, Optional, TYPE_CHECKING

from core.http import get_httpx_client
from core.context import get_context
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
    - OpenRouter API (по умолчанию)
    - Любой OpenAI-совместимый API
    - Fallback между моделями одной размерности
    - Billing для учёта использования
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
        # Billing параметры
        cost_per_1m_tokens: float = 5.0,
        platform_markup: float = 1.1,
        billing_service: Optional["BillingService"] = None,
    ):
        """
        Args:
            api_key: API ключ (OpenRouter по умолчанию)
            models: Список моделей для fallback (первая рабочая будет использована)
            base_url: Кастомный URL API (по умолчанию OpenRouter)
            timeout: Таймаут запросов
            dimension: Ожидаемая размерность (для валидации)
            cost_per_1m_tokens: Средняя цена за 1M токенов (в рублях)
            platform_markup: Наценка платформы (1.1 = +10%)
            billing_service: Сервис биллинга (опционально)
        """
        if not api_key:
            raise ValueError("API key обязателен для EmbeddingService")
        
        self.api_key = api_key
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
        
        if base_url:
            self.api_url = base_url.rstrip("/")
            if not self.api_url.endswith("/embeddings"):
                self.api_url = f"{self.api_url}/embeddings"
        else:
            self.api_url = self.OPENROUTER_URL
        
        logger.info(f"EmbeddingService: models={self.models}, url={self.api_url}")
    
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
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://humanitec.ru",
            "X-Title": "Humanitec RAG",
        }
        
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
                
                # Проверяем размерность
                if embeddings and self.dimension:
                    actual_dim = len(embeddings[0])
                    if actual_dim != self.dimension:
                        logger.warning(
                            f"Model {model} returned dimension {actual_dim}, "
                            f"expected {self.dimension}"
                        )
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
        
        # Все модели недоступны
        raise ValueError(
            f"All embedding models failed: {self.models}. "
            "Check API key and model availability."
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
        
        # Подсчитываем токены для billing
        token_count = self.count_tokens(texts)
        
        logger.info(f"Генерация embeddings для {len(texts)} текстов ({token_count} токенов)")
        
        all_embeddings = []
        total_batches = (len(texts) + self.BATCH_SIZE - 1) // self.BATCH_SIZE
        
        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i:i + self.BATCH_SIZE]
            batch_num = i // self.BATCH_SIZE + 1
            logger.debug(f"Batch {batch_num}/{total_batches}: {len(batch)} текстов")
            
            batch_embeddings = await self._generate_embeddings_batch(batch)
            all_embeddings.extend(batch_embeddings)
        
        # Записываем billing
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
