"""
LLMResource - wrapper для llm ресурса.

Предоставляет доступ к LLM для генерации текста.
"""

from typing import Any, Dict, List, Optional

from core.logging import get_logger

logger = get_logger(__name__)


class LLMResource:
    """
    Ресурс для работы с LLM.
    
    Пример:
        summary = await gpt4.complete("Summarize this: " + text)
        
        response = await claude.chat([
            {"role": "user", "content": "Hello"}
        ])
    """
    
    def __init__(
        self,
        provider: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_key = api_key
        self.base_url = base_url
        self._client = None
    
    def _get_client(self):
        """Возвращает LLM клиент."""
        if self._client is None:
            from core.clients.llm import get_llm
            self._client = get_llm(
                model_name=self.model,
                temperature=self.temperature,
                provider=self.provider,
                api_key=self.api_key,
                base_url=self.base_url,
            )
        return self._client
    
    async def complete(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Генерация текста по промпту.
        
        Args:
            prompt: Текстовый промпт
            temperature: Температура (переопределяет дефолт)
            max_tokens: Макс. токенов (переопределяет дефолт)
            
        Returns:
            Сгенерированный текст
        """
        client = self._get_client()
        
        response = await client.chat(prompt)
        return self._extract_text(response)
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Чат с историей сообщений.
        
        Args:
            messages: Список сообщений [{"role": "user/assistant", "content": "..."}]
            temperature: Температура
            max_tokens: Макс. токенов
            
        Returns:
            Ответ модели
        """
        client = self._get_client()
        
        response = await client.chat(messages)
        return self._extract_text(response)
    
    def _extract_text(self, response: Any) -> str:
        """Извлекает текст из ответа LLM."""
        if hasattr(response, "parts") and response.parts:
            from a2a.utils.message import get_message_text
            return get_message_text(response)
        if hasattr(response, "content"):
            return response.content
        return str(response)
    
    async def chat_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]],
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Чат с поддержкой tools.
        
        Args:
            messages: История сообщений
            tools: Список tools в OpenAI формате
            
        Returns:
            Ответ с tool_calls если есть
        """
        client = self._get_client()
        
        client_with_tools = client.bind_tools(tools)
        response = await client_with_tools.ainvoke(messages)
        
        return {
            "content": response.content if hasattr(response, "content") else "",
            "tool_calls": response.tool_calls if hasattr(response, "tool_calls") else [],
        }
    
    def __repr__(self) -> str:
        return f"<LLMResource provider={self.provider} model={self.model}>"
