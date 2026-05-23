"""
HTTP клиент с поддержкой прокси и автоматической ротацией при ошибках.

Использование:
    async with get_httpx_client(strategy=ProxyStrategy.DIRECT_FIRST) as client:
        response = await client.post("https://api.example.com", json={...})
"""

from collections.abc import Callable, Mapping
from contextlib import AbstractAsyncContextManager
from enum import Enum
from ssl import SSLContext
from types import TracebackType
from typing import ClassVar, TypedDict, Unpack, cast
from urllib.parse import urljoin, urlparse

import httpx
from httpx._transports.base import AsyncBaseTransport
from httpx._types import (
    AuthTypes,
    CertTypes,
    CookieTypes,
    HeaderTypes,
    QueryParamTypes,
    RequestContent,
    RequestData,
    RequestExtensions,
    RequestFiles,
)

from core.config import BaseSettings, get_settings
from core.http.egress_route_preference import (
    egress_prefer_proxy_delete,
    egress_prefer_proxy_get,
    egress_prefer_proxy_set,
    normalized_http_origin,
)
from core.logging import get_logger
from core.types import require_json_value

logger = get_logger(__name__)

_CONNECT_RETRY_EXCEPTIONS = (httpx.ConnectError, httpx.ConnectTimeout)

# Ключи, допустимые в httpx.request(...), но не в httpx.AsyncClient(...).
_HTTPX_REQUEST_ONLY_KEYS = frozenset({"content", "data", "files", "json", "extensions"})

# Базовый набор статусов для SMART (401 добавляется через settings.proxy.retry_http_401_via_proxy).
HTTP_STATUS_RETRY_VIA_PROXY = frozenset({403, 429, 451})


class HttpRequestKwargs(TypedDict, total=False):
    content: RequestContent | None
    data: RequestData | None
    files: RequestFiles | None
    json: object | None
    params: QueryParamTypes | None
    headers: HeaderTypes | None
    cookies: CookieTypes | None
    auth: AuthTypes | None
    follow_redirects: bool
    extensions: RequestExtensions | None


class HttpClientKwargs(TypedDict, total=False):
    auth: AuthTypes | None
    params: QueryParamTypes | None
    headers: HeaderTypes | None
    cookies: CookieTypes | None
    verify: SSLContext | str | bool
    cert: CertTypes | None
    http1: bool
    http2: bool
    mounts: Mapping[str, AsyncBaseTransport | None] | None
    follow_redirects: bool
    limits: httpx.Limits
    max_redirects: int
    event_hooks: Mapping[str, list[Callable[..., object]]] | None
    base_url: httpx.URL | str
    transport: AsyncBaseTransport | None
    default_encoding: str | Callable[[bytes], str]


def _normalized_request_kwargs(kwargs: HttpRequestKwargs) -> HttpRequestKwargs:
    if "json" not in kwargs or kwargs["json"] is None:
        return kwargs
    normalized = dict(kwargs)
    normalized["json"] = require_json_value(kwargs["json"], "http request json")
    return cast(HttpRequestKwargs, cast(object, normalized))


async def _send_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    kwargs: HttpRequestKwargs,
) -> httpx.Response:
    return await client.request(method, url, **_normalized_request_kwargs(kwargs))


def _httpx_async_client_kwargs(merged_kwargs: HttpRequestKwargs) -> HttpClientKwargs:
    """Отделяет kwargs конструктора AsyncClient от параметров одного HTTP-запроса."""
    client_kwargs = {
        k: v for k, v in merged_kwargs.items() if k not in _HTTPX_REQUEST_ONLY_KEYS
    }
    return cast(HttpClientKwargs, cast(object, client_kwargs))


PUBLIC_OAUTH_DIRECT_ATTEMPTS_BEFORE_PROXY = 3
PUBLIC_OAUTH_DIRECT_ATTEMPTS_AFTER_PROXY = 2


class ProxyStrategy(Enum):
    """Стратегия использования прокси для HTTP запросов."""

    DIRECT_FIRST = "direct_first"  # Сначала прямое подключение, затем прокси
    PROXY_FIRST = "proxy_first"  # Сначала прокси, затем прямое подключение
    DIRECT_ONLY = "direct_only"  # Только прямое подключение
    PROXY_ONLY = "proxy_only"  # Только через прокси
    SMART = (
        "smart"  # Сначала напрямую; при триггерных статусах — через platform proxy; learn в Redis
    )


def _require_proxy_strategy(strategy: ProxyStrategy | str) -> ProxyStrategy:
    if isinstance(strategy, ProxyStrategy):
        return strategy
    try:
        return ProxyStrategy(strategy)
    except ValueError as exc:
        raise ValueError(f"Unknown strategy: {strategy}") from exc


def _platform_proxy_active() -> bool:
    p = get_settings().proxy
    return bool(p.enabled and p.proxies)


def _retry_http_statuses_for_smart() -> frozenset[int]:
    s = set(HTTP_STATUS_RETRY_VIA_PROXY)
    if get_settings().proxy.retry_http_401_via_proxy:
        s.add(401)
    return frozenset(s)


async def _request_direct_burst(
    method: str,
    url: str,
    *,
    timeout: float,
    attempts: int,
    httpx_client_kwargs: HttpClientKwargs | None = None,
    **kwargs: Unpack[HttpRequestKwargs],
) -> httpx.Response:
    http_method = method.upper()
    last: BaseException | None = None
    hck = httpx_client_kwargs or {}
    for attempt in range(attempts):
        async with get_httpx_client(
            timeout=timeout, strategy=ProxyStrategy.DIRECT_ONLY, **hck
        ) as client:
            try:
                return await client.request(http_method, url, **kwargs)
            except _CONNECT_RETRY_EXCEPTIONS as e:
                last = e
                logger.warning(
                    "Прямой запрос к %s: %s (попытка %s/%s)",
                    url,
                    type(e).__name__,
                    attempt + 1,
                    attempts,
                )
    if last is None:
        raise RuntimeError("request_public_oauth: attempts must be >= 1")
    raise last


async def request_public_oauth(
    method: str,
    url: str,
    *,
    timeout: float = 30.0,
    direct_attempts_before_proxy: int = PUBLIC_OAUTH_DIRECT_ATTEMPTS_BEFORE_PROXY,
    direct_attempts_after_proxy: int = PUBLIC_OAUTH_DIRECT_ATTEMPTS_AFTER_PROXY,
    httpx_client_kwargs: HttpClientKwargs | None = None,
    **kwargs: Unpack[HttpRequestKwargs],
) -> httpx.Response:
    """
    Исходящие запросы к публичным OAuth/identity API: несколько попыток без прокси,
    затем через platform proxy (если proxy.enabled и список proxies непустой),
    затем снова несколько попыток без прокси.
    """
    hck = httpx_client_kwargs or {}
    try:
        return await _request_direct_burst(
            method,
            url,
            timeout=timeout,
            attempts=direct_attempts_before_proxy,
            httpx_client_kwargs=hck,
            **kwargs,
        )
    except _CONNECT_RETRY_EXCEPTIONS:
        pass

    if _platform_proxy_active():
        try:
            async with get_httpx_client(
                timeout=timeout, strategy=ProxyStrategy.PROXY_ONLY, **hck
            ) as client:
                return await client.request(method.upper(), url, **kwargs)
        except _CONNECT_RETRY_EXCEPTIONS as e:
            logger.warning(
                "Запрос через прокси к %s не удался (%s), снова прямое подключение",
                url,
                type(e).__name__,
            )

    return await _request_direct_burst(
        method,
        url,
        timeout=timeout,
        attempts=direct_attempts_after_proxy,
        httpx_client_kwargs=hck,
        **kwargs,
    )


async def request_with_strategy(
    method: str,
    url: str,
    *,
    strategy: ProxyStrategy | str = ProxyStrategy.DIRECT_FIRST,
    proxy_attempts: int = 3,
    direct_attempts: int = 2,
    timeout: float = 30.0,
    **kwargs: Unpack[HttpRequestKwargs],
) -> httpx.Response:
    """
    Программируемый HTTP клиент с настраиваемой стратегией прокси.

    Args:
        method: HTTP метод (GET, POST и т.д.)
        url: URL для запроса
        strategy: Стратегия использования прокси (`ProxyStrategy` или ее строковое значение)
        proxy_attempts: Количество попыток через прокси (для proxy_first)
        direct_attempts: Количество попыток прямого подключения (для direct_first)
        timeout: Таймаут запросов
        **kwargs: Параметры для `client.request` (json, data, files, headers, ...). Ключи только
            для запроса (`json`, `data`, `files`, `content`, `extensions`) не передаются в
            конструктор `httpx.AsyncClient`.

    Returns:
        httpx.Response

    Raises:
        httpx.ConnectError: Если все попытки подключения не удались
    """
    strategy = _require_proxy_strategy(strategy)

    if strategy == ProxyStrategy.DIRECT_ONLY:
        return await _request_direct_burst(
            method,
            url,
            timeout=timeout,
            attempts=direct_attempts,
            **kwargs,
        )

    if strategy == ProxyStrategy.PROXY_ONLY:
        if not _platform_proxy_active():
            raise httpx.ConnectError("Proxy requested but not configured")
        client_kw = _httpx_async_client_kwargs(kwargs)
        async with get_httpx_client(
            timeout=timeout,
            strategy=ProxyStrategy.PROXY_ONLY,
            proxy_attempts=proxy_attempts,
            **client_kw,
        ) as client:
            return await client.request(method.upper(), url, **kwargs)

    if strategy == ProxyStrategy.DIRECT_FIRST:
        # Проверяем, помечен ли origin для прокси (обучение SMART/DIRECT_FIRST)
        origin = normalized_http_origin(url)
        prefer = False
        if _platform_proxy_active():
            try:
                prefer = await egress_prefer_proxy_get(origin)
            except Exception:
                pass

        if not prefer:
            try:
                return await _request_direct_burst(
                    method,
                    url,
                    timeout=timeout,
                    attempts=direct_attempts,
                    **kwargs,
                )
            except _CONNECT_RETRY_EXCEPTIONS:
                pass

        if _platform_proxy_active():
            try:
                client_kw = _httpx_async_client_kwargs(kwargs)
                async with get_httpx_client(
                    timeout=timeout,
                    strategy=ProxyStrategy.PROXY_ONLY,
                    proxy_attempts=proxy_attempts,
                    **client_kw,
                ) as client:
                    resp = await client.request(method.upper(), url, **kwargs)
                    # Запоминаем: этот origin работает через прокси
                    try:
                        await egress_prefer_proxy_set(origin)
                    except Exception:
                        pass
                    return resp
            except _CONNECT_RETRY_EXCEPTIONS:
                logger.warning(
                    "Запрос через прокси к %s не удался, повторное прямое подключение",
                    url,
                )
                # Прокси тоже не работает — сбрасываем предпочтение
                try:
                    await egress_prefer_proxy_delete(origin)
                except Exception:
                    pass

        return await _request_direct_burst(
            method,
            url,
            timeout=timeout,
            attempts=1,
            **kwargs,
        )

    if strategy == ProxyStrategy.PROXY_FIRST:
        if _platform_proxy_active():
            try:
                client_kw = _httpx_async_client_kwargs(kwargs)
                async with get_httpx_client(
                    timeout=timeout,
                    strategy=ProxyStrategy.PROXY_ONLY,
                    proxy_attempts=proxy_attempts,
                    **client_kw,
                ) as client:
                    return await client.request(method.upper(), url, **kwargs)
            except _CONNECT_RETRY_EXCEPTIONS:
                logger.warning(
                    "Запрос через прокси к %s не удался, переключение на прямое подключение",
                    url,
                )

        return await _request_direct_burst(
            method,
            url,
            timeout=timeout,
            attempts=direct_attempts,
            **kwargs,
        )

    if strategy == ProxyStrategy.SMART:
        client_kw = _httpx_async_client_kwargs(kwargs)
        async with get_httpx_client(
            timeout=timeout, strategy=ProxyStrategy.SMART, **client_kw
        ) as client:
            return await client.request(method.upper(), url, **kwargs)


class SmartProxyClient:
    """
    HTTP клиент с автоматической ротацией прокси при таймаутах.

    При ConnectTimeout автоматически пробует следующий прокси.
    """

    MAX_PROXY_RETRIES: ClassVar[int] = 3

    def __init__(
        self,
        timeout: float = 30.0,
        use_proxy: bool = False,
        *,
        strategy: ProxyStrategy = ProxyStrategy.DIRECT_FIRST,
        proxy_attempts: int = 3,
        direct_attempts: int = 2,
        **kwargs: Unpack[HttpClientKwargs],
    ) -> None:
        self.timeout: float = timeout
        self.use_proxy: bool = use_proxy
        self.kwargs: HttpClientKwargs = kwargs
        self._client: httpx.AsyncClient | None = None
        self._settings: BaseSettings | None = None
        self._strategy: ProxyStrategy = strategy
        self._proxy_attempts: int = proxy_attempts
        self._direct_attempts: int = direct_attempts

    async def __aenter__(self) -> "SmartProxyClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def aclose(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_settings(self) -> BaseSettings:
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    def platform_settings(self) -> BaseSettings:
        return self._get_settings()

    @property
    def strategy(self) -> ProxyStrategy:
        return self._strategy

    def _create_client(self, proxy_url: str | None = None) -> httpx.AsyncClient:
        if self.use_proxy:
            settings = self._get_settings()
            connect_timeout = settings.proxy.connect_timeout
        else:
            connect_timeout = float(self.timeout)

        kwargs = self.kwargs

        return httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout, connect=connect_timeout),
            proxy=proxy_url,
            trust_env=False,
            **kwargs,
        )

    def create_client(self, proxy_url: str | None = None) -> httpx.AsyncClient:
        return self._create_client(proxy_url)

    def _absolute_request_url(self, url: str) -> str:
        if url.startswith("http://") or url.startswith("https://"):
            return url
        base = self.kwargs.get("base_url")
        if base is None:
            raise ValueError(
                "SmartProxyClient: для относительного URL нужен base_url в kwargs клиента "
                + "(egress preference по origin)."
            )
        return urljoin(str(base), url)

    def absolute_request_url(self, url: str) -> str:
        return self._absolute_request_url(url)

    def _is_local_url(self, url: str) -> bool:
        try:
            hostname = urlparse(url).hostname or ""
            return (
                hostname in ("localhost", "127.0.0.1", "::1")
                or hostname.endswith(".localhost")
                or hostname.startswith("192.168.")
                or hostname.startswith("10.")
                or hostname.startswith("172.16.")
            )
        except Exception:
            return False

    def is_local_url(self, url: str) -> bool:
        return self._is_local_url(url)

    async def _request_via_proxy_rotation(
        self, http_method: str, url: str, **kwargs: Unpack[HttpRequestKwargs]
    ) -> httpx.Response:
        settings = self._get_settings()

        for attempt in range(self.MAX_PROXY_RETRIES):
            proxy_url = settings.proxy.get_next_proxy()
            logger.debug(
                "Using proxy: %s... -> %s",
                proxy_url[:40] if proxy_url else "None",
                url,
            )

            try:
                async with self._create_client(proxy_url) as client:
                    response = await _send_request(client, http_method, url, kwargs)
                    return response

            except (httpx.ConnectTimeout, httpx.ConnectError) as e:
                settings.proxy.mark_last_proxy_failed()

                if attempt < self.MAX_PROXY_RETRIES - 1:
                    logger.warning(
                        "Proxy %s failed (%s), switching to next proxy (attempt %s/%s)",
                        proxy_url,
                        type(e).__name__,
                        attempt + 2,
                        self.MAX_PROXY_RETRIES,
                    )
                else:
                    logger.error("All proxy attempts failed for %s", url)
                    raise
        raise RuntimeError("proxy rotation exited without response")

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs: Unpack[HttpRequestKwargs],
    ) -> httpx.Response:
        http_method = method.upper()
        strategy = getattr(self, "_strategy", ProxyStrategy.DIRECT_FIRST)

        if self._is_local_url(url):
            async with self._create_client() as client:
                return await _send_request(client, http_method, url, kwargs)

        absolute_url = self._absolute_request_url(url)
        origin = normalized_http_origin(absolute_url)

        prefer = False
        if (
            _platform_proxy_active()
            and strategy in (ProxyStrategy.SMART, ProxyStrategy.DIRECT_FIRST)
            and not self.use_proxy
        ):
            prefer = await egress_prefer_proxy_get(origin)

        if prefer and strategy in (ProxyStrategy.SMART, ProxyStrategy.DIRECT_FIRST):
            try:
                response = await self._request_via_proxy_rotation(http_method, url, **kwargs)
            except _CONNECT_RETRY_EXCEPTIONS:
                await egress_prefer_proxy_delete(origin)
                async with self._create_client() as client:
                    return await _send_request(client, http_method, url, kwargs)
            if response.is_success:
                await egress_prefer_proxy_set(origin)
                return response
            await response.aclose()
            await egress_prefer_proxy_delete(origin)
            async with self._create_client() as client:
                direct_resp = await _send_request(client, http_method, url, kwargs)
            return direct_resp

        if strategy == ProxyStrategy.SMART:
            try:
                async with self._create_client() as client:
                    response = await _send_request(client, http_method, url, kwargs)
            except _CONNECT_RETRY_EXCEPTIONS:
                if _platform_proxy_active():
                    response = await self._request_via_proxy_rotation(http_method, url, **kwargs)
                    if response.is_success:
                        await egress_prefer_proxy_set(origin)
                    return response
                raise
            retry_status = _retry_http_statuses_for_smart()
            if response.status_code in retry_status and _platform_proxy_active():
                logger.warning(
                    "HTTP %s для %s, повтор через platform proxy",
                    response.status_code,
                    url,
                )
                await response.aclose()
                response = await self._request_via_proxy_rotation(http_method, url, **kwargs)
                if response.is_success:
                    await egress_prefer_proxy_set(origin)
                return response
            return response

        if not self.use_proxy:
            async with self._create_client() as client:
                return await _send_request(client, http_method, url, kwargs)

        return await self._request_via_proxy_rotation(http_method, url, **kwargs)

    async def get(self, url: str, **kwargs: Unpack[HttpRequestKwargs]) -> httpx.Response:
        return await self._request_with_retry("get", url, **kwargs)

    async def post(self, url: str, **kwargs: Unpack[HttpRequestKwargs]) -> httpx.Response:
        return await self._request_with_retry("post", url, **kwargs)

    async def put(self, url: str, **kwargs: Unpack[HttpRequestKwargs]) -> httpx.Response:
        return await self._request_with_retry("put", url, **kwargs)

    async def delete(self, url: str, **kwargs: Unpack[HttpRequestKwargs]) -> httpx.Response:
        return await self._request_with_retry("delete", url, **kwargs)

    async def patch(self, url: str, **kwargs: Unpack[HttpRequestKwargs]) -> httpx.Response:
        return await self._request_with_retry("patch", url, **kwargs)

    async def request(
        self,
        method: str,
        url: str,
        **kwargs: Unpack[HttpRequestKwargs],
    ) -> httpx.Response:
        return await self._request_with_retry(method.lower(), url, **kwargs)

    def stream(
        self,
        method: str,
        url: str,
        **kwargs: Unpack[HttpRequestKwargs],
    ) -> "_StreamContextManager":
        return _StreamContextManager(self, method, url, **kwargs)


class _StreamContextManager:
    """Context manager для streaming запросов с retry прокси"""

    def __init__(
        self,
        smart_client: SmartProxyClient,
        method: str,
        url: str,
        **kwargs: Unpack[HttpRequestKwargs],
    ) -> None:
        self._smart_client: SmartProxyClient = smart_client
        self._method: str = method
        self._url: str = url
        self._kwargs: HttpRequestKwargs = kwargs
        self._client: httpx.AsyncClient | None = None
        self._stream_cm: AbstractAsyncContextManager[httpx.Response] | None = None

    async def _enter_direct_stream(self) -> httpx.Response:
        self._client = self._smart_client.create_client()
        self._stream_cm = self._client.stream(
            self._method,
            self._url,
            **_normalized_request_kwargs(self._kwargs),
        )
        return await self._stream_cm.__aenter__()

    async def _cleanup_stream(self) -> None:
        if self._stream_cm:
            _ = await self._stream_cm.__aexit__(None, None, None)
            self._stream_cm = None
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> httpx.Response:
        strategy = self._smart_client.strategy

        if self._smart_client.is_local_url(self._url):
            return await self._enter_direct_stream()

        absolute_url = self._smart_client.absolute_request_url(self._url)
        origin = normalized_http_origin(absolute_url)

        prefer = False
        if (
            _platform_proxy_active()
            and strategy in (ProxyStrategy.SMART, ProxyStrategy.DIRECT_FIRST)
            and not self._smart_client.use_proxy
        ):
            prefer = await egress_prefer_proxy_get(origin)

        if prefer and strategy in (ProxyStrategy.SMART, ProxyStrategy.DIRECT_FIRST):
            settings = self._smart_client.platform_settings()
            last_exc: BaseException | None = None
            for attempt in range(self._smart_client.MAX_PROXY_RETRIES):
                proxy_url = settings.proxy.get_next_proxy()
                try:
                    self._client = self._smart_client.create_client(proxy_url)
                    self._stream_cm = self._client.stream(
                        self._method,
                        self._url,
                        **_normalized_request_kwargs(self._kwargs),
                    )
                    response = await self._stream_cm.__aenter__()
                    if response.is_success:
                        await egress_prefer_proxy_set(origin)
                        return response
                    await self._cleanup_stream()
                    await egress_prefer_proxy_delete(origin)
                    return await self._enter_direct_stream()
                except (httpx.ConnectTimeout, httpx.ConnectError) as e:
                    last_exc = e
                    settings.proxy.mark_last_proxy_failed()
                    await self._cleanup_stream()
                    if attempt < self._smart_client.MAX_PROXY_RETRIES - 1:
                        logger.warning(
                            "Proxy %s failed (%s), switching to next proxy (stream)",
                            proxy_url,
                            type(e).__name__,
                        )
            await egress_prefer_proxy_delete(origin)
            if last_exc is not None:
                return await self._enter_direct_stream()
            raise RuntimeError("stream proxy rotation: unexpected state")

        if strategy == ProxyStrategy.SMART:
            try:
                response = await self._enter_direct_stream()
            except _CONNECT_RETRY_EXCEPTIONS:
                if _platform_proxy_active():
                    settings = self._smart_client.platform_settings()
                    for attempt in range(self._smart_client.MAX_PROXY_RETRIES):
                        proxy_url = settings.proxy.get_next_proxy()
                        try:
                            self._client = self._smart_client.create_client(proxy_url)
                            self._stream_cm = self._client.stream(
                                self._method,
                                self._url,
                                **_normalized_request_kwargs(self._kwargs),
                            )
                            response = await self._stream_cm.__aenter__()
                            if response.is_success:
                                await egress_prefer_proxy_set(origin)
                            return response
                        except (httpx.ConnectTimeout, httpx.ConnectError) as e:
                            settings.proxy.mark_last_proxy_failed()
                            await self._cleanup_stream()
                            if attempt < self._smart_client.MAX_PROXY_RETRIES - 1:
                                logger.warning(
                                    "Proxy %s failed (%s), stream connect retry",
                                    proxy_url,
                                    type(e).__name__,
                                )
                            else:
                                raise
                else:
                    raise
            else:
                retry_status = _retry_http_statuses_for_smart()
                if response.status_code in retry_status and _platform_proxy_active():
                    logger.warning(
                        "HTTP %s для stream %s, повтор через platform proxy",
                        response.status_code,
                        self._url,
                    )
                    await self._cleanup_stream()
                    settings = self._smart_client.platform_settings()
                    for attempt in range(self._smart_client.MAX_PROXY_RETRIES):
                        proxy_url = settings.proxy.get_next_proxy()
                        try:
                            self._client = self._smart_client.create_client(proxy_url)
                            self._stream_cm = self._client.stream(
                                self._method,
                                self._url,
                                **_normalized_request_kwargs(self._kwargs),
                            )
                            response = await self._stream_cm.__aenter__()
                            if response.is_success:
                                await egress_prefer_proxy_set(origin)
                            return response
                        except (httpx.ConnectTimeout, httpx.ConnectError) as e:
                            settings.proxy.mark_last_proxy_failed()
                            await self._cleanup_stream()
                            if attempt < self._smart_client.MAX_PROXY_RETRIES - 1:
                                logger.warning(
                                    "Proxy %s failed (%s), stream (attempt %s/%s)",
                                    proxy_url,
                                    type(e).__name__,
                                    attempt + 2,
                                    self._smart_client.MAX_PROXY_RETRIES,
                                )
                            else:
                                logger.error("All proxy stream attempts failed for %s", self._url)
                                raise
                return response

        if not self._smart_client.use_proxy:
            return await self._enter_direct_stream()

        settings = self._smart_client.platform_settings()

        for attempt in range(self._smart_client.MAX_PROXY_RETRIES):
            proxy_url = settings.proxy.get_next_proxy()
            logger.debug(
                "Using proxy for stream: %s... -> %s",
                proxy_url[:40] if proxy_url else "None",
                self._url,
            )

            try:
                self._client = self._smart_client.create_client(proxy_url)
                self._stream_cm = self._client.stream(
                    self._method,
                    self._url,
                    **_normalized_request_kwargs(self._kwargs),
                )
                return await self._stream_cm.__aenter__()

            except (httpx.ConnectTimeout, httpx.ConnectError) as e:
                settings.proxy.mark_last_proxy_failed()
                await self._cleanup_stream()

                if attempt < self._smart_client.MAX_PROXY_RETRIES - 1:
                    logger.warning(
                        "Proxy %s failed (%s), stream (attempt %s/%s)",
                        proxy_url,
                        type(e).__name__,
                        attempt + 2,
                        self._smart_client.MAX_PROXY_RETRIES,
                    )
                else:
                    logger.error("All proxy attempts failed for %s", self._url)
                    raise
        raise RuntimeError("stream proxy rotation exited without response")

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._stream_cm:
            _ = await self._stream_cm.__aexit__(exc_type, exc_val, exc_tb)
        if self._client:
            await self._client.aclose()
            self._client = None


def get_httpx_client(
    timeout: float = 30.0,
    strategy: ProxyStrategy | str = ProxyStrategy.DIRECT_FIRST,
    proxy_attempts: int = 3,
    direct_attempts: int = 2,
    **kwargs: Unpack[HttpClientKwargs],
) -> SmartProxyClient:
    """
    Создает HTTP клиент с настраиваемой стратегией прокси.

    Args:
        timeout: Таймаут запросов
        strategy: Стратегия (direct_first, proxy_first, direct_only, proxy_only, smart)
        proxy_attempts: Количество попыток через прокси (для proxy_first)
        direct_attempts: Количество попыток прямого подключения (для direct_first)
        **kwargs: Дополнительные параметры для httpx.AsyncClient

    Returns:
        SmartProxyClient с настроенной стратегией
    """
    raw_kwargs = cast(Mapping[str, object], kwargs)
    if "proxy" in raw_kwargs:
        raise ValueError(
            "get_httpx_client: unsupported keyword 'proxy'; "
            + "use strategy=ProxyStrategy.PROXY_ONLY, DIRECT_ONLY, etc."
        )
    strategy = _require_proxy_strategy(strategy)
    use_proxy = strategy in (ProxyStrategy.PROXY_FIRST, ProxyStrategy.PROXY_ONLY)
    return SmartProxyClient(
        timeout=timeout,
        use_proxy=use_proxy,
        strategy=strategy,
        proxy_attempts=proxy_attempts,
        direct_attempts=direct_attempts,
        **kwargs,
    )
