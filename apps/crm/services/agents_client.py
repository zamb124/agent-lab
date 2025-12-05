"""
AgentsClient - HTTP клиент для вызова AI агентов из apps/agents.

CRM вызывает apps/agents через Flow API с синхронным ожиданием результата.
"""

import json
import logging
import re
from typing import Dict, Any, List, Optional

from core.http import get_httpx_client
from core.context import get_context

logger = logging.getLogger(__name__)


class AgentsClient:
    """
    HTTP клиент для вызова CRM агентов в apps/agents через Flow API.
    
    Flows:
    - crm_entity_extractor - извлечение сущностей из текста
    - crm_entity_comparison - сравнение/дедупликация сущностей
    """
    
    DEFAULT_TIMEOUT = 60.0  # секунд на выполнение
    
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
        if context and context.auth_token:
            headers["Authorization"] = f"Bearer {context.auth_token}"
        
        return headers
    
    async def _call_flow(
        self, 
        flow_id: str, 
        message: str,
        timeout: float = DEFAULT_TIMEOUT
    ) -> Dict[str, Any]:
        """
        Вызывает flow синхронно с ожиданием результата.
        
        Args:
            flow_id: ID flow
            message: Текст сообщения
            timeout: Максимальное время ожидания
            
        Returns:
            Результат выполнения flow
        """
        headers = self._get_headers()
        url = f"{self._base_url}/agents/api/v1/flows/{flow_id}/message"
        
        payload = {
            "message": message,
            "role": "user",
            "user_id": headers.get("X-User-Id", "crm_service"),
            "wait_timeout": timeout,  # Синхронный режим
        }
        
        async with get_httpx_client(timeout=timeout + 10, use_proxy_from_config=False) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
        
        if result.get("status") != "completed":
            raise ValueError(f"Flow {flow_id} не завершился: {result}")
        
        return result.get("result", {})
    
    async def extract_entities(
        self,
        text: str,
        entity_types: Optional[List[Dict[str, Any]]] = None,
        generate_summary: bool = False,
    ) -> Dict[str, Any]:
        """
        Извлекает сущности из текста через Flow API.
        
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
        """
        message_parts = [text]
        
        if generate_summary:
            message_parts.append("\n\nТакже создай краткое резюме текста.")
        
        if entity_types:
            types_info = "\n".join([
                f"- {t.get('type_id')}: {t.get('prompt', t.get('description', ''))}" 
                for t in entity_types
            ])
            message_parts.append(f"\n\nДоступные типы сущностей:\n{types_info}")
        
        message = "\n".join(message_parts)
        
        result = await self._call_flow("crm_entity_extractor", message)
        
        return self._parse_extraction_result(result)
    
    def _parse_extraction_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Парсит результат извлечения сущностей из ответа агента"""
        # Если результат уже в нужном формате
        if "entities" in result:
            return result
        
        # Ответ агента в поле response или message
        response_text = result.get("response") or result.get("message") or ""
        
        # Пробуем извлечь JSON из ответа
        json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Пробуем парсить весь ответ как JSON
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            pass
        
        # Возвращаем пустой результат
        logger.warning(f"Не удалось распарсить ответ агента: {response_text[:200]}")
        return {"entities": [], "relationships": [], "summary": response_text}
    
    async def compare_entities(
        self,
        entity_1: Dict[str, Any],
        entity_2: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Сравнивает две сущности для определения дубликатов.
        """
        message = f"""Сравни две сущности и определи, являются ли они дубликатами:

Сущность 1:
{json.dumps(entity_1, ensure_ascii=False, indent=2)}

Сущность 2:
{json.dumps(entity_2, ensure_ascii=False, indent=2)}

Ответь в формате JSON:
```json
{{
    "is_duplicate": true/false,
    "confidence": 0.0-1.0,
    "reason": "объяснение"
}}
```"""
        
        result = await self._call_flow("crm_entity_comparison", message, timeout=30.0)
        return self._parse_comparison_result(result)
    
    def _parse_comparison_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Парсит результат сравнения сущностей"""
        if "is_duplicate" in result:
            return result
        
        response_text = result.get("response") or result.get("message") or ""
        
        json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        return {"is_duplicate": False, "confidence": 0.0, "reason": "Не удалось определить"}
    
    async def health_check(self) -> bool:
        """Проверяет доступность сервиса агентов"""
        url = f"{self._base_url}/agents/health"
        
        async with get_httpx_client(timeout=5.0, use_proxy_from_config=False) as client:
            response = await client.get(url)
            response.raise_for_status()
            return True
