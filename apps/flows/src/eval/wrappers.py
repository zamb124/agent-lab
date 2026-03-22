"""
Безопасные обертки для использования в inline коде.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Type, TypeVar, Union, overload

import httpx
from a2a.types import Message
from pydantic import BaseModel

from core.clients.llm.factory import get_llm, MessageInput
from core.context import get_current_channel
from core.http import get_httpx_client
from core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


class SafeLLMClient:
    """
    Безопасная обертка над LLM клиентом для использования в inline коде.
    
    Единый метод chat() для всех сценариев:
    - Простой чат: await llm.chat("Привет!")
    - С параметрами: await llm.chat("...", temperature=0.7, max_tokens=500)
    - Structured output: await llm.chat("...", response_model=MyModel)
    - Function calling: await llm.chat(messages, tools=[...])
    """

    def _get_llm(self, model: Optional[str] = None):
        """Получает LLM клиент."""
        return get_llm(model_name=model)

    @overload
    async def chat(
        self,
        messages: MessageInput,
        *,
        response_model: Type[T],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        max_tokens: Optional[int] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
    ) -> T: ...

    @overload
    async def chat(
        self,
        messages: MessageInput,
        *,
        response_model: None = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        max_tokens: Optional[int] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
    ) -> Message: ...

    async def chat(
        self,
        messages: MessageInput,
        *,
        response_model: Optional[Type[T]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        max_tokens: Optional[int] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
    ) -> Message | T:
        """
        Единый метод вызова LLM.
        
        Принимает messages в любом формате и возвращает:
        - T (экземпляр Pydantic модели) если указан response_model
        - Message с tool_calls если указаны tools (и нет response_model)
        - Message с текстом в остальных случаях
        
        Args:
            messages: Сообщения в любом формате:
                - str: "Привет!" 
                - List[str]: ["Привет!", "Привет! Как дела?", "Отлично!"]
                - Message или List[Message]: A2A сообщения
                - Dict или List[Dict]: {"role": "user", "content": "..."}
            response_model: Pydantic модель для structured output
            tools: Список tools для function calling
            model: Имя модели
            temperature: Температура генерации (0.0-2.0)
            top_p: Top-P семплирование (0.0-1.0)
            top_k: Top-K семплирование
            max_tokens: Максимальное количество токенов
            frequency_penalty: Штраф за частоту токенов (-2.0-2.0)
            presence_penalty: Штраф за присутствие токенов (-2.0-2.0)
        
        Returns:
            Message или экземпляр response_model
            
        Examples:
            # Простой чат
            msg = await llm.chat("Привет!")
            text = msg.parts[0].root.text
            
            # С параметрами
            msg = await llm.chat("Расскажи историю", temperature=0.9, max_tokens=500)
            
            # Structured output
            class User(BaseModel):
                name: str
                age: int
                
            user = await llm.chat("Extract: John is 25", response_model=User)
            print(user.name, user.age)
            
            # Function calling
            msg = await llm.chat(messages, tools=[...])
            if msg.metadata and msg.metadata.get("tool_calls"):
                ...
        """
        llm = self._get_llm(model)
        return await llm.chat(
            messages,
            response_model=response_model,
            tools=tools,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            max_tokens=max_tokens,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
        )


class SafeContext:
    """
    Безопасная обертка над контекстом выполнения.
    Предоставляет только чтение основных полей.
    """

    def __init__(self, context: Optional[Any] = None):
        self._context = context

    @property
    def channel(self) -> str:
        """Канал коммуникации: a2a, api, telegram, max, voip."""
        if self._context is None:
            return "unknown"
        return self._context.channel

    @property
    def user_id(self) -> Optional[str]:
        """ID пользователя."""
        if self._context is None or self._context.user is None:
            return None
        return self._context.user.user_id

    @property
    def session_id(self) -> Optional[str]:
        """ID сессии."""
        if self._context is None:
            return None
        return self._context.session_id

    @property
    def flow_id(self) -> Optional[str]:
        """ID агента."""
        if self._context is None:
            return None
        return self._context.flow_id

    @property
    def metadata(self) -> Dict[str, Any]:
        """Метаданные запроса (только для чтения)."""
        if self._context is None:
            return {}
        return dict(self._context.metadata)


class SafeChannel:
    """
    Безопасная обертка для отправки сообщений пользователю.
    """

    def __init__(self, context: Optional[Any] = None):
        self._context = context

    async def send(self, content: str) -> None:
        """
        Отправляет сообщение пользователю через текущий канал.

        Args:
            content: Текст сообщения
        """
        channel = get_current_channel()
        if channel is None:
            logger.warning("Cannot send message: no channel available")
            return

        await channel.send_to_user(content)

    async def send_with_buttons(
        self, content: str, buttons: List[str]
    ) -> None:
        """
        Отправляет сообщение с кнопками быстрого ответа.

        Args:
            content: Текст сообщения
            buttons: Список кнопок
        """
        channel = get_current_channel()
        if channel is None:
            logger.warning("Cannot send message: no channel available")
            return

        await channel.send_to_user(content, buttons=buttons)


class HttpxModule:
    """
    Модуль-обертка httpx с функциями верхнего уровня.
    Предоставляет простой API: httpx.get(), httpx.post() и т.д.
    """

    _default_timeout = 30.0

    @staticmethod
    async def get(
        url: Union[str, httpx.URL],
        *,
        params: Optional[Union[Dict[str, Any], httpx.QueryParams]] = None,
        headers: Optional[Union[Dict[str, str], httpx.Headers]] = None,
        cookies: Optional[Union[Dict[str, str], httpx.Cookies]] = None,
        auth: Optional[httpx.Auth] = None,
        follow_redirects: bool = False,
        timeout: Optional[Union[float, httpx.Timeout]] = None,
        **kwargs,
    ) -> httpx.Response:
        """GET запрос через прокси."""
        timeout = timeout or HttpxModule._default_timeout
        async with get_httpx_client(timeout=timeout, proxy=True) as client:
            return await client.get(
                url,
                params=params,
                headers=headers,
                cookies=cookies,
                auth=auth,
                follow_redirects=follow_redirects,
                **kwargs,
            )

    @staticmethod
    async def post(
        url: Union[str, httpx.URL],
        *,
        content: Optional[Union[str, bytes]] = None,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        json: Optional[Any] = None,
        params: Optional[Union[Dict[str, Any], httpx.QueryParams]] = None,
        headers: Optional[Union[Dict[str, str], httpx.Headers]] = None,
        cookies: Optional[Union[Dict[str, str], httpx.Cookies]] = None,
        auth: Optional[httpx.Auth] = None,
        follow_redirects: bool = False,
        timeout: Optional[Union[float, httpx.Timeout]] = None,
        **kwargs,
    ) -> httpx.Response:
        """POST запрос через прокси."""
        timeout = timeout or HttpxModule._default_timeout
        async with get_httpx_client(timeout=timeout, proxy=True) as client:
            return await client.post(
                url,
                content=content,
                data=data,
                files=files,
                json=json,
                params=params,
                headers=headers,
                cookies=cookies,
                auth=auth,
                follow_redirects=follow_redirects,
                **kwargs,
            )

    @staticmethod
    async def put(
        url: Union[str, httpx.URL],
        *,
        content: Optional[Union[str, bytes]] = None,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        json: Optional[Any] = None,
        params: Optional[Union[Dict[str, Any], httpx.QueryParams]] = None,
        headers: Optional[Union[Dict[str, str], httpx.Headers]] = None,
        cookies: Optional[Union[Dict[str, str], httpx.Cookies]] = None,
        auth: Optional[httpx.Auth] = None,
        follow_redirects: bool = False,
        timeout: Optional[Union[float, httpx.Timeout]] = None,
        **kwargs,
    ) -> httpx.Response:
        """PUT запрос через прокси."""
        timeout = timeout or HttpxModule._default_timeout
        async with get_httpx_client(timeout=timeout, proxy=True) as client:
            return await client.put(
                url,
                content=content,
                data=data,
                files=files,
                json=json,
                params=params,
                headers=headers,
                cookies=cookies,
                auth=auth,
                follow_redirects=follow_redirects,
                **kwargs,
            )

    @staticmethod
    async def patch(
        url: Union[str, httpx.URL],
        *,
        content: Optional[Union[str, bytes]] = None,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        json: Optional[Any] = None,
        params: Optional[Union[Dict[str, Any], httpx.QueryParams]] = None,
        headers: Optional[Union[Dict[str, str], httpx.Headers]] = None,
        cookies: Optional[Union[Dict[str, str], httpx.Cookies]] = None,
        auth: Optional[httpx.Auth] = None,
        follow_redirects: bool = False,
        timeout: Optional[Union[float, httpx.Timeout]] = None,
        **kwargs,
    ) -> httpx.Response:
        """PATCH запрос через прокси."""
        timeout = timeout or HttpxModule._default_timeout
        async with get_httpx_client(timeout=timeout, proxy=True) as client:
            return await client.patch(
                url,
                content=content,
                data=data,
                files=files,
                json=json,
                params=params,
                headers=headers,
                cookies=cookies,
                auth=auth,
                follow_redirects=follow_redirects,
                **kwargs,
            )

    @staticmethod
    async def delete(
        url: Union[str, httpx.URL],
        *,
        params: Optional[Union[Dict[str, Any], httpx.QueryParams]] = None,
        headers: Optional[Union[Dict[str, str], httpx.Headers]] = None,
        cookies: Optional[Union[Dict[str, str], httpx.Cookies]] = None,
        auth: Optional[httpx.Auth] = None,
        follow_redirects: bool = False,
        timeout: Optional[Union[float, httpx.Timeout]] = None,
        **kwargs,
    ) -> httpx.Response:
        """DELETE запрос через прокси."""
        timeout = timeout or HttpxModule._default_timeout
        async with get_httpx_client(timeout=timeout, proxy=True) as client:
            return await client.delete(
                url,
                params=params,
                headers=headers,
                cookies=cookies,
                auth=auth,
                follow_redirects=follow_redirects,
                **kwargs,
            )

    @staticmethod
    async def request(
        method: str,
        url: Union[str, httpx.URL],
        *,
        content: Optional[Union[str, bytes]] = None,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        json: Optional[Any] = None,
        params: Optional[Union[Dict[str, Any], httpx.QueryParams]] = None,
        headers: Optional[Union[Dict[str, str], httpx.Headers]] = None,
        cookies: Optional[Union[Dict[str, str], httpx.Cookies]] = None,
        auth: Optional[httpx.Auth] = None,
        follow_redirects: bool = False,
        timeout: Optional[Union[float, httpx.Timeout]] = None,
        **kwargs,
    ) -> httpx.Response:
        """Универсальный request через прокси."""
        timeout = timeout or HttpxModule._default_timeout
        async with get_httpx_client(timeout=timeout, proxy=True) as client:
            return await client.request(
                method,
                url,
                content=content,
                data=data,
                files=files,
                json=json,
                params=params,
                headers=headers,
                cookies=cookies,
                auth=auth,
                follow_redirects=follow_redirects,
                **kwargs,
            )
