"""
LLMResource - wrapper для llm ресурса.

Предоставляет доступ к LLM для генерации текста.
"""

from typing import Any, Dict, List, Optional

from apps.flows.src.runtime.llm_byok import is_llm_byok_resource
from core.billing.service import BALANCE_BLOCK_OPERATION_LLM
from core.context import get_context
from core.logging import get_logger
from core.models.billing_models import UsageType
from core.tracing.operation_span import traced_operation

logger = get_logger(__name__)


async def _require_balance_for_llm_resource() -> None:
    from apps.flows.src.container import get_container

    actx = get_context()
    if actx is None or actx.active_company is None:
        raise ValueError("Контекст с active_company обязателен для LLMResource")
    if actx.user is None or not str(actx.user.user_id).strip():
        raise ValueError("Контекст с user обязателен для LLMResource (биллинг и уведомления)")
    await get_container().billing_service.require_balance_for_billable_operation(
        actx.active_company.company_id,
        str(actx.user.user_id).strip(),
        operation_code=BALANCE_BLOCK_OPERATION_LLM,
        notification_service="flows",
    )


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
        folder_id: Optional[str] = None,
        extra_request_body: Optional[Dict[str, Any]] = None,
        extra_request_headers: Optional[Dict[str, str]] = None,
    ):
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_key = api_key
        self.base_url = base_url
        self.folder_id = folder_id
        self._extra_body = (
            dict(extra_request_body) if extra_request_body else None
        )
        self._extra_headers = (
            dict(extra_request_headers) if extra_request_headers else None
        )
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
                folder_id=self.folder_id,
            )
        return self._client
    
    def _billing_resource_name(self) -> str:
        if is_llm_byok_resource(api_key=self.api_key, base_url=self.base_url):
            return "llm:byok"
        return f"llm:{self.model}"

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
        if not is_llm_byok_resource(api_key=self.api_key, base_url=self.base_url):
            await _require_balance_for_llm_resource()

        br_name = self._billing_resource_name()
        async with traced_operation(
            "flows.llm_resource.complete",
            event_type="llm.complete",
            operation_category="llm",
            billing_usage_type=UsageType.LLM_REQUEST.value,
            billing_resource_name=br_name,
            billing_quantity=1,
            billing_pending_settlement=True,
        ):
            chat_kw: Dict[str, Any] = {}
            if temperature is not None:
                chat_kw["temperature"] = temperature
            if max_tokens is not None:
                chat_kw["max_tokens"] = max_tokens
            if self._extra_body is not None:
                chat_kw["extra_body"] = self._extra_body
            if self._extra_headers is not None:
                chat_kw["extra_headers"] = self._extra_headers
            response = await client.chat(prompt, **chat_kw)
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
        if not is_llm_byok_resource(api_key=self.api_key, base_url=self.base_url):
            await _require_balance_for_llm_resource()

        br_name = self._billing_resource_name()
        async with traced_operation(
            "flows.llm_resource.chat",
            event_type="llm.chat",
            operation_category="llm",
            billing_usage_type=UsageType.LLM_REQUEST.value,
            billing_resource_name=br_name,
            billing_quantity=1,
            billing_pending_settlement=True,
        ):
            chat_kw: Dict[str, Any] = {}
            if temperature is not None:
                chat_kw["temperature"] = temperature
            if max_tokens is not None:
                chat_kw["max_tokens"] = max_tokens
            if self._extra_body is not None:
                chat_kw["extra_body"] = self._extra_body
            if self._extra_headers is not None:
                chat_kw["extra_headers"] = self._extra_headers
            response = await client.chat(messages, **chat_kw)
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
        if not is_llm_byok_resource(api_key=self.api_key, base_url=self.base_url):
            await _require_balance_for_llm_resource()

        br_name = self._billing_resource_name()
        async with traced_operation(
            "flows.llm_resource.chat_with_tools",
            event_type="llm.chat_with_tools",
            operation_category="llm",
            billing_usage_type=UsageType.LLM_REQUEST.value,
            billing_resource_name=br_name,
            billing_quantity=1,
            billing_pending_settlement=True,
        ):
            client_with_tools = client.bind_tools(tools)
            response = await client_with_tools.ainvoke(messages)

            return {
                "content": response.content if hasattr(response, "content") else "",
                "tool_calls": response.tool_calls if hasattr(response, "tool_calls") else [],
            }
    
    def __repr__(self) -> str:
        return f"<LLMResource provider={self.provider} model={self.model}>"
