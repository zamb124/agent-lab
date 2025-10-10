"""
Клиент для SGR Deep Research сервиса.
Обеспечивает HTTP взаимодействие с микросервисом исследований.
"""

import logging
import httpx
from typing import Optional, AsyncIterator
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class SGRMessage(BaseModel):
    """Сообщение для SGR API"""
    role: str
    content: str


class SGRRequest(BaseModel):
    """Запрос к SGR API"""
    messages: list[SGRMessage]
    stream: bool = False
    model: str = "sgr-agent"


class SGRResponse(BaseModel):
    """Ответ от SGR API"""
    content: str
    report_path: Optional[str] = None
    sources: list[str] = []


class SGRClient:
    """
    Клиент для взаимодействия с SGR Deep Research сервисом.
    
    SGR Deep Research - это микросервис для глубоких исследований с помощью
    Schema-Guided Reasoning и веб-поиска.
    """
    
    def __init__(
        self,
        base_url: str = "http://localhost:8010",
        timeout: float = 300.0,
        api_key: Optional[str] = None
    ):
        """
        Args:
            base_url: URL SGR сервиса
            timeout: Таймаут запросов (по умолчанию 5 минут для долгих исследований)
            api_key: Опциональный API ключ для аутентификации
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.api_key = api_key
        
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            follow_redirects=True
        )
    
    async def close(self):
        """Закрывает HTTP клиент"""
        await self.client.aclose()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    def _get_headers(self) -> dict:
        """Формирует заголовки для запросов"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers
    
    async def research(
        self,
        query: str,
        model: str = "sgr_agent"
    ) -> SGRResponse:
        """
        Выполняет исследование через SGR сервис.
        
        SGR поддерживает только streaming режим, поэтому метод
        автоматически собирает все чанки в единый ответ.
        
        Args:
            query: Запрос для исследования
            model: Модель агента (sgr_agent, sgr_tool_calling_agent, etc)
            
        Returns:
            SGRResponse с результатами исследования
            
        Raises:
            httpx.HTTPStatusError: При ошибке HTTP
            ValueError: При ошибке валидации
        """
        if not query:
            raise ValueError("query не может быть пустым")
        
        logger.info(f"SGR исследование: {query[:100]}...")
        
        content = ""
        async for chunk in self.research_streaming(query, model):
            content += chunk
        
        logger.info(f"SGR исследование завершено: {len(content)} символов")
        
        return SGRResponse(
            content=content,
            report_path=None,
            sources=[]
        )
    
    async def research_streaming(
        self,
        query: str,
        model: str = "sgr_agent"
    ) -> AsyncIterator[str]:
        """
        Выполняет исследование со streaming ответов.
        
        Args:
            query: Запрос для исследования
            model: Модель агента
            
        Yields:
            Части ответа по мере генерации
        """
        if not query:
            raise ValueError("query не может быть пустым")
        
        logger.info(f"SGR streaming исследование: {query[:100]}...")
        
        request = SGRRequest(
            messages=[SGRMessage(role="user", content=query)],
            stream=True,
            model=model
        )
        
        async with self.client.stream(
            "POST",
            f"{self.base_url}/v1/chat/completions",
            json=request.model_dump(),
            headers=self._get_headers()
        ) as response:
            response.raise_for_status()
            
            async for chunk in response.aiter_text():
                if chunk.strip():
                    yield chunk
    
    async def get_models(self) -> list[str]:
        """
        Получает список доступных моделей агентов.
        
        Returns:
            Список ID моделей
        """
        response = await self.client.get(
            f"{self.base_url}/v1/models",
            headers=self._get_headers()
        )
        response.raise_for_status()
        
        data = response.json()
        if "data" in data:
            return [model["id"] for model in data["data"]]
        return []
    
    async def health_check(self) -> bool:
        """
        Проверяет доступность SGR сервиса.
        
        Returns:
            True если сервис доступен, False при любых ошибках
        """
        response = await self.client.get(
            f"{self.base_url}/v1/models",
            headers=self._get_headers(),
            timeout=5.0
        )
        return response.status_code == 200

