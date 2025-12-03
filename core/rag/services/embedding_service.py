"""
Сервис для генерации embeddings через OpenRouter и другие совместимые API.
"""

import logging
from typing import List, Optional

from core.http import get_httpx_client

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Сервис для генерации embeddings.
    По умолчанию использует OpenRouter, но поддерживает любой OpenAI-совместимый API.
    """
    
    OPENROUTER_URL = "https://openrouter.ai/api/v1/embeddings"
    DEFAULT_MODEL = "openai/text-embedding-3-small"
    
    def __init__(
        self,
        api_key: str,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 30,
    ):
        """
        Args:
            api_key: API ключ (OpenRouter по умолчанию)
            model: Модель для embeddings (например: openai/text-embedding-3-small)
            base_url: Кастомный URL API (по умолчанию OpenRouter)
            timeout: Таймаут запросов
        """
        if not api_key:
            raise ValueError("API key обязателен для EmbeddingService")
        
        self.api_key = api_key
        self.model = model or self.DEFAULT_MODEL
        self.timeout = timeout
        
        if base_url:
            self.api_url = base_url.rstrip("/")
            if not self.api_url.endswith("/embeddings"):
                self.api_url = f"{self.api_url}/embeddings"
        else:
            self.api_url = self.OPENROUTER_URL
        
        logger.info(f"EmbeddingService: model={self.model}, url={self.api_url}")
    
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
    
    BATCH_SIZE = 50  # Максимум текстов в одном запросе (OpenRouter лимит)
    
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
        
        logger.info(f"Генерация embeddings для {len(texts)} текстов, batch_size={self.BATCH_SIZE}")
        
        all_embeddings = []
        total_batches = (len(texts) + self.BATCH_SIZE - 1) // self.BATCH_SIZE
        
        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i:i + self.BATCH_SIZE]
            batch_num = i // self.BATCH_SIZE + 1
            logger.info(f"Batch {batch_num}/{total_batches}: {len(batch)} текстов")
            
            batch_embeddings = await self._generate_embeddings_batch(batch)
            all_embeddings.extend(batch_embeddings)
        
        logger.info(f"Всего сгенерировано {len(all_embeddings)} embeddings")
        return all_embeddings
    
    async def _generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Генерирует embeddings для одного батча текстов."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://humanitec.ru",
            "X-Title": "Humanitec RAG",
        }
        
        async with get_httpx_client(
            timeout=self.timeout,
            use_proxy_from_config=True
        ) as client:
            response = await client.post(
                self.api_url,
                headers=headers,
                json={
                    "model": self.model,
                    "input": texts,
                },
            )
            
            if response.status_code != 200:
                error_text = response.text[:500]
                logger.error(f"Embedding API error {response.status_code}: {error_text}")
                raise ValueError(f"Embedding API error {response.status_code}: {error_text}")
            
            data = response.json()
            
            if "data" not in data:
                logger.error(f"Unexpected API response: {str(data)[:500]}")
                raise ValueError(f"Unexpected API response: no 'data' field")
        
        return [item["embedding"] for item in data["data"]]
    
    def get_embedding_dimension(self) -> int:
        """
        Возвращает размерность embedding для текущей модели.
        
        Returns:
            Размерность вектора
        """
        dimensions = {
            "openai/text-embedding-3-small": 1536,
            "openai/text-embedding-3-large": 3072,
            "openai/text-embedding-ada-002": 1536,
            "cohere/embed-english-v3.0": 1024,
            "cohere/embed-multilingual-v3.0": 1024,
            "voyage/voyage-3": 1024,
            "voyage/voyage-3-lite": 512,
        }
        return dimensions.get(self.model, 1536)
