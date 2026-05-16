"""
Безопасные обертки для использования в inline коде.
"""

from __future__ import annotations

from typing import Any, TypeVar, overload

import httpx
from a2a.types import Message
from pydantic import BaseModel

from core.clients.llm.factory import MessageInput, get_llm
from core.context import get_current_channel
from core.errors import SafeEvalError
from core.http import ProxyStrategy, get_httpx_client
from core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


def _coerce_timeout_seconds(timeout: Any) -> float:
    if timeout is None:
        return float(HttpxModule.default_timeout)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise SafeEvalError("timeout must be a number of seconds")
    return float(timeout)


def _coerce_url(url: str | httpx.URL) -> str:
    return str(url)


def _normalize_tools_for_llm(tools: list[Any] | None) -> list[dict[str, Any]] | None:
    """
    Приводит элементы tools к OpenAI-словарям для HTTP-тела.

    Принимает либо уже готовые dict, либо экземпляры BaseTool / @tool (to_openai_schema).
    Сырая функция без обёртки не поддерживается — используйте декоратор tool(...) в namespace.
    """
    if not tools:
        return None
    out: list[dict[str, Any]] = []
    for i, item in enumerate(tools):
        if isinstance(item, dict):
            out.append(item)
            continue
        to_schema = getattr(item, "to_openai_schema", None)
        if callable(to_schema):
            schema = to_schema()
            if not isinstance(schema, dict):
                raise SafeEvalError(f"tools[{i}].to_openai_schema() must return dict")
            out.append(schema)
            continue
        raise SafeEvalError(
            f"tools[{i}]: ожидается dict (OpenAI tool) или объект с to_openai_schema() "
            f"(класс BaseTool / результат @tool), получено {type(item).__name__}. "
            f"Объяви функцию через @tool(name=..., description=..., tags=[...]) и передай имя в tools=[...]."
        )
    return out


class SafeLLMClient:
    """
    Обертка над LLM для inline-кода: делегирует в core get_llm().chat.

    Семантика и полный набор kwargs совпадают с фабричным клиентом, включая
    seed, reasoning_effort, extra_body (произвольные поля тела запроса к провайдеру).
    """

    def _get_llm(self, model: str | None = None):
        """Получает LLM клиент."""
        return get_llm(model_name=model)

    @overload
    async def chat(
        self,
        messages: MessageInput,
        *,
        response_model: type[T],
        tools: list[Any] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        max_tokens: int | None = None,
        frequency_penalty: float | None = None,
        presence_penalty: float | None = None,
        seed: int | None = None,
        reasoning_effort: str | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> T: ...

    @overload
    async def chat(
        self,
        messages: MessageInput,
        *,
        response_model: None = None,
        tools: list[Any] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        max_tokens: int | None = None,
        frequency_penalty: float | None = None,
        presence_penalty: float | None = None,
        seed: int | None = None,
        reasoning_effort: str | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> Message: ...

    async def chat(
        self,
        messages: MessageInput,
        *,
        response_model: type[T] | None = None,
        tools: list[Any] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        max_tokens: int | None = None,
        frequency_penalty: float | None = None,
        presence_penalty: float | None = None,
        seed: int | None = None,
        reasoning_effort: str | None = None,
        extra_body: dict[str, Any] | None = None,
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
            tools: OpenAI dict или экземпляры @tool / BaseTool (см. to_openai_schema); смешивание типов допустимо
            model: Имя модели
            temperature: Температура генерации (0.0-2.0)
            top_p: Top-P семплирование (0.0-1.0)
            top_k: Top-K семплирование
            max_tokens: Максимальное количество токенов
            frequency_penalty: Штраф за частоту токенов (-2.0-2.0)
            presence_penalty: Штраф за присутствие токенов (-2.0-2.0)
            seed: Фиксированный seed (детерминизм), если провайдер поддерживает
            reasoning_effort: Режим reasoning (OpenAI-совместимые API), строка
            extra_body: Доп. поля тела запроса к провайдеру (dict); мержатся поверх сформированного JSON и перекрывают совпадающие ключи

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

            # Function calling: @tool(...) def my_tool(...): ...  ->  tools=[my_tool]
            msg = await llm.chat("2+2?", tools=[my_tool])
        """
        llm = self._get_llm(model)
        coerced_tools = _normalize_tools_for_llm(tools)
        return await llm.chat(
            messages,
            response_model=response_model,
            tools=coerced_tools,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            max_tokens=max_tokens,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            seed=seed,
            reasoning_effort=reasoning_effort,
            extra_body=extra_body,
        )


class SafeContext:
    """
    Безопасная обертка над контекстом выполнения.
    Предоставляет только чтение основных полей.
    """

    def __init__(self, context: Any | None = None):
        self._context = context

    @property
    def channel(self) -> str:
        """Канал коммуникации: a2a, api, telegram, max, voip."""
        if self._context is None:
            return "unknown"
        return self._context.channel

    @property
    def user_id(self) -> str | None:
        """ID пользователя."""
        if self._context is None or self._context.user is None:
            return None
        return self._context.user.user_id

    @property
    def session_id(self) -> str | None:
        """ID сессии."""
        if self._context is None:
            return None
        return self._context.session_id

    @property
    def flow_id(self) -> str | None:
        """ID агента."""
        if self._context is None:
            return None
        return self._context.flow_id

    @property
    def metadata(self) -> dict[str, Any]:
        """Метаданные запроса (только для чтения)."""
        if self._context is None:
            return {}
        return dict(self._context.metadata)


class SafeChannel:
    """
    Безопасная обертка для отправки сообщений пользователю.
    """

    def __init__(self, context: Any | None = None):
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
        self, content: str, buttons: list[str]
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


class _SandboxAsyncClientContext:
    """
    `async with httpx.AsyncClient(...) as client` в sandbox: тот же SmartProxyClient,
    что открывается внутри httpx.get / post (стратегия SMART).
    """

    __slots__ = ("_timeout", "_cm")

    def __init__(self, *, timeout: float) -> None:
        self._timeout = timeout
        self._cm: Any = None

    async def __aenter__(self) -> Any:
        self._cm = get_httpx_client(timeout=self._timeout, strategy=ProxyStrategy.SMART)
        return await self._cm.__aenter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        if self._cm is not None:
            await self._cm.__aexit__(exc_type, exc, tb)


class HttpxModule:
    """
    Модуль-обертка httpx с функциями верхнего уровня.
    Предоставляет простой API: httpx.get(), httpx.post() и т.д.
    """

    default_timeout = 30.0

    RequestError = httpx.RequestError
    HTTPStatusError = httpx.HTTPStatusError
    TimeoutException = httpx.TimeoutException
    ConnectError = httpx.ConnectError
    ConnectTimeout = httpx.ConnectTimeout

    class AsyncClient:
        """В sandbox только `timeout=...`; остальные аргументы конструктора запрещены."""

        def __new__(cls, **kwargs: Any) -> _SandboxAsyncClientContext:
            timeout_raw = kwargs.pop("timeout", None)
            if kwargs:
                unknown = ", ".join(sorted(kwargs.keys()))
                raise SafeEvalError(
                    f"В sandbox httpx.AsyncClient доступен только timeout=...; лишние аргументы: {unknown}",
                )
            timeout = _coerce_timeout_seconds(timeout_raw)
            return _SandboxAsyncClientContext(timeout=timeout)

    @staticmethod
    async def get(
        url: str | httpx.URL,
        *,
        params: dict[str, Any] | httpx.QueryParams | None = None,
        headers: dict[str, str] | httpx.Headers | None = None,
        cookies: dict[str, str] | httpx.Cookies | None = None,
        auth: httpx.Auth | None = None,
        follow_redirects: bool = False,
        timeout: float | None = None,
        **kwargs,
    ) -> httpx.Response:
        """GET с strategy=SMART (прямой канал, при блокировках — egress + learn в Redis)."""
        timeout = _coerce_timeout_seconds(timeout)
        async with get_httpx_client(timeout=timeout, strategy=ProxyStrategy.SMART) as client:
            return await client.get(
                _coerce_url(url),
                params=params,
                headers=headers,
                cookies=cookies,
                auth=auth,
                follow_redirects=follow_redirects,
                **kwargs,
            )

    @staticmethod
    async def post(
        url: str | httpx.URL,
        *,
        content: str | bytes | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        json: Any | None = None,
        params: dict[str, Any] | httpx.QueryParams | None = None,
        headers: dict[str, str] | httpx.Headers | None = None,
        cookies: dict[str, str] | httpx.Cookies | None = None,
        auth: httpx.Auth | None = None,
        follow_redirects: bool = False,
        timeout: float | None = None,
        **kwargs,
    ) -> httpx.Response:
        """POST с strategy=SMART."""
        timeout = _coerce_timeout_seconds(timeout)
        async with get_httpx_client(timeout=timeout, strategy=ProxyStrategy.SMART) as client:
            return await client.post(
                _coerce_url(url),
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
        url: str | httpx.URL,
        *,
        content: str | bytes | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        json: Any | None = None,
        params: dict[str, Any] | httpx.QueryParams | None = None,
        headers: dict[str, str] | httpx.Headers | None = None,
        cookies: dict[str, str] | httpx.Cookies | None = None,
        auth: httpx.Auth | None = None,
        follow_redirects: bool = False,
        timeout: float | None = None,
        **kwargs,
    ) -> httpx.Response:
        """PUT с strategy=SMART."""
        timeout = _coerce_timeout_seconds(timeout)
        async with get_httpx_client(timeout=timeout, strategy=ProxyStrategy.SMART) as client:
            return await client.put(
                _coerce_url(url),
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
        url: str | httpx.URL,
        *,
        content: str | bytes | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        json: Any | None = None,
        params: dict[str, Any] | httpx.QueryParams | None = None,
        headers: dict[str, str] | httpx.Headers | None = None,
        cookies: dict[str, str] | httpx.Cookies | None = None,
        auth: httpx.Auth | None = None,
        follow_redirects: bool = False,
        timeout: float | None = None,
        **kwargs,
    ) -> httpx.Response:
        """PATCH с strategy=SMART."""
        timeout = _coerce_timeout_seconds(timeout)
        async with get_httpx_client(timeout=timeout, strategy=ProxyStrategy.SMART) as client:
            return await client.patch(
                _coerce_url(url),
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
        url: str | httpx.URL,
        *,
        params: dict[str, Any] | httpx.QueryParams | None = None,
        headers: dict[str, str] | httpx.Headers | None = None,
        cookies: dict[str, str] | httpx.Cookies | None = None,
        auth: httpx.Auth | None = None,
        follow_redirects: bool = False,
        timeout: float | None = None,
        **kwargs,
    ) -> httpx.Response:
        """DELETE с strategy=SMART."""
        timeout = _coerce_timeout_seconds(timeout)
        async with get_httpx_client(timeout=timeout, strategy=ProxyStrategy.SMART) as client:
            return await client.delete(
                _coerce_url(url),
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
        url: str | httpx.URL,
        *,
        content: str | bytes | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        json: Any | None = None,
        params: dict[str, Any] | httpx.QueryParams | None = None,
        headers: dict[str, str] | httpx.Headers | None = None,
        cookies: dict[str, str] | httpx.Cookies | None = None,
        auth: httpx.Auth | None = None,
        follow_redirects: bool = False,
        timeout: float | None = None,
        **kwargs,
    ) -> httpx.Response:
        """request() с strategy=SMART."""
        timeout = _coerce_timeout_seconds(timeout)
        async with get_httpx_client(timeout=timeout, strategy=ProxyStrategy.SMART) as client:
            return await client.request(
                method,
                _coerce_url(url),
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
