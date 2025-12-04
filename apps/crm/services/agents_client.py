"""
AgentsClient - HTTP клиент для вызова AI агентов из apps/agents.

CRM не создает собственные агенты, а вызывает apps/agents через HTTP API.
"""

import logging
from typing import Dict, Any, List, Optional

import httpx

from core.http import get_httpx_client
from core.context import get_context

logger = logging.getLogger(__name__)


class AgentsClient:
    """
    HTTP клиент для вызова CRM агентов в apps/agents.
    
    Агенты:
    - crm_entity_extractor - извлечение сущностей из текста
    - crm_entity_comparison - сравнение/дедупликация сущностей
    """
    
    def __init__(self, agents_base_url: str):
        self._base_url = agents_base_url.rstrip("/")
    
    def _get_headers(self) -> Dict[str, str]:
        """Формирует заголовки с контекстом"""
        headers = {"Content-Type": "application/json"}
        
        context = get_context()
        if context and context.active_company:
            headers["X-Company-Id"] = context.active_company.company_id
        if context and context.user:
            headers["X-User-Id"] = context.user.user_id
        
        return headers
    
    async def extract_entities(
        self,
        text: str,
        entity_types: Optional[List[Dict[str, Any]]] = None,
        generate_summary: bool = False,
    ) -> Dict[str, Any]:
        """
        Извлекает сущности из текста.
        
        Args:
            text: Текст для анализа
            entity_types: Список типов с промптами (опционально)
            generate_summary: Генерировать резюме текста
            
        Returns:
            {
                "entities": [...],
                "relationships": [...],
                "summary": "..." (если generate_summary=True)
            }
            
        Raises:
            httpx.HTTPStatusError: Ошибка HTTP запроса
        """
        url = f"{self._base_url}/agents/api/v1/invoke/crm_entity_extractor"
        
        payload = {
            "text": text,
            "generate_summary": generate_summary,
        }
        if entity_types:
            payload["entity_types"] = entity_types
        
        async with get_httpx_client(timeout=60.0, use_proxy_from_config=True) as client:
            response = await client.post(
                url,
                json=payload,
                headers=self._get_headers(),
            )
            response.raise_for_status()
            return response.json()
    
    async def compare_entities(
        self,
        entity_1: Dict[str, Any],
        entity_2: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Сравнивает две сущности для определения дубликатов.
        
        Args:
            entity_1: Первая сущность
            entity_2: Вторая сущность
            
        Returns:
            {
                "is_duplicate": bool,
                "confidence": float,
                "reason": str
            }
            
        Raises:
            httpx.HTTPStatusError: Ошибка HTTP запроса
        """
        url = f"{self._base_url}/agents/api/v1/invoke/crm_entity_comparison"
        
        payload = {
            "entity_1": entity_1,
            "entity_2": entity_2,
        }
        
        async with get_httpx_client(timeout=30.0, use_proxy_from_config=True) as client:
            response = await client.post(
                url,
                json=payload,
                headers=self._get_headers(),
            )
            response.raise_for_status()
            return response.json()
    
    async def health_check(self) -> bool:
        """
        Проверяет доступность сервиса агентов.
        
        Raises:
            httpx.RequestError: Сервис недоступен
        """
        url = f"{self._base_url}/agents/health"
        
        async with get_httpx_client(timeout=5.0, use_proxy_from_config=False) as client:
            response = await client.get(url)
            response.raise_for_status()
            return True
