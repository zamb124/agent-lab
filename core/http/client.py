"""
HTTP клиент с поддержкой прокси и автоматической ротацией при ошибках.

Использование:
    async with get_httpx_client(proxy=True) as client:
        response = await client.post("https://api.example.com", json={...})
"""

from typing import Optional

import httpx

from core.logging import get_logger

logger = get_logger(__name__)

_CONNECT_RETRY_EXCEPTIONS = (httpx.ConnectError, httpx.ConnectTimeout)

PUBLIC_OAUTH_DIRECT_ATTEMPTS_BEFORE_PROXY = 3
PUBLIC_OAUTH_DIRECT_ATTEMPTS_AFTER_PROXY = 2


def _platform_proxy_active() -> bool:
    from core.config import get_settings

    p = get_settings().proxy
    return bool(p.enabled and p.proxies)


async def _request_direct_burst(
    method: str,
    url: str,
    *,
    timeout: float,
    attempts: int,
    **kwargs,
) -> httpx.Response:
    m = method.lower()
    last: BaseException | None = None
    for attempt in range(attempts):
        async with get_httpx_client(timeout=timeout, proxy=False) as client:
            try:
                return await getattr(client, m)(url, **kwargs)
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
    **kwargs,
) -> httpx.Response:
    """
    Исходящие запросы к публичным OAuth/identity API: несколько попыток без прокси,
    затем через platform proxy (если proxy.enabled и список proxies непустой),
    затем снова несколько попыток без прокси.
    """
    try:
        return await _request_direct_burst(
            method,
            url,
            timeout=timeout,
            attempts=direct_attempts_before_proxy,
            **kwargs,
        )
    except _CONNECT_RETRY_EXCEPTIONS:
        pass

    if _platform_proxy_active():
        try:
            async with get_httpx_client(timeout=timeout, proxy=True) as client:
                return await getattr(client, method.lower())(url, **kwargs)
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
        **kwargs,
    )


class SmartProxyClient:
    """
    HTTP клиент с автоматической ротацией прокси при таймаутах.

    При ConnectTimeout автоматически пробует следующий прокси.
    """

    MAX_PROXY_RETRIES = 3

    def __init__(self, timeout: float = 30.0, use_proxy: bool = False, **kwargs):
        self.timeout = timeout
        self.use_proxy = use_proxy
        self.kwargs = kwargs
        self._client: Optional[httpx.AsyncClient] = None
        self._settings = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()

    def _get_settings(self):
        if self._settings is None:
            from core.config import get_settings

            self._settings = get_settings()
        return self._settings

    def _create_client(self, proxy_url: Optional[str] = None) -> httpx.AsyncClient:
        """Создаёт httpx клиент с указанным прокси"""
        if self.use_proxy:
            settings = self._get_settings()
            connect_timeout = settings.proxy.connect_timeout
        else:
            # Без прокси общий timeout задаёт read/write; connect не должен быть жёстко 15с
            # (иначе OpenRouter/embeddings при медленном TLS падают с ConnectTimeout).
            connect_timeout = float(self.timeout)

        return httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout, connect=connect_timeout),
            proxy=proxy_url,
            trust_env=False,
            **self.kwargs,
        )

    def _is_local_url(self, url: str) -> bool:
        """Проверяет что URL ведёт на localhost или приватную сеть."""
        try:
            from urllib.parse import urlparse
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

    async def _request_with_retry(self, method: str, url: str, **kwargs) -> httpx.Response:
        """
        Выполняет запрос с автоматическим retry при таймауте прокси.
        Локальные адреса (localhost, 192.168.x.x и т.д.) всегда идут напрямую.
        """
        if not self.use_proxy or self._is_local_url(url):
            async with self._create_client() as client:
                return await getattr(client, method)(url, **kwargs)

        settings = self._get_settings()

        for attempt in range(self.MAX_PROXY_RETRIES):
            proxy_url = settings.proxy.get_next_proxy()
            logger.debug(f"Using proxy: {proxy_url[:40] if proxy_url else 'None'}... -> {url}")

            try:
                async with self._create_client(proxy_url) as client:
                    response = await getattr(client, method)(url, **kwargs)
                    return response

            except (httpx.ConnectTimeout, httpx.ConnectError) as e:
                settings.proxy.mark_last_proxy_failed()

                if attempt < self.MAX_PROXY_RETRIES - 1:
                    logger.warning(
                        f"Proxy {proxy_url} failed ({type(e).__name__}), "
                        f"switching to next proxy (attempt {attempt + 2}/{self.MAX_PROXY_RETRIES})"
                    )
                else:
                    logger.error(f"All proxy attempts failed for {url}")
                    raise

    async def get(self, url: str, **kwargs) -> httpx.Response:
        return await self._request_with_retry("get", url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        return await self._request_with_retry("post", url, **kwargs)

    async def put(self, url: str, **kwargs) -> httpx.Response:
        return await self._request_with_retry("put", url, **kwargs)

    async def delete(self, url: str, **kwargs) -> httpx.Response:
        return await self._request_with_retry("delete", url, **kwargs)

    async def patch(self, url: str, **kwargs) -> httpx.Response:
        return await self._request_with_retry("patch", url, **kwargs)

    async def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Универсальный метод для любого HTTP метода"""
        return await self._request_with_retry(method.lower(), url, **kwargs)

    def stream(self, method: str, url: str, **kwargs):
        """
        Возвращает stream context manager с retry при таймауте прокси.

        Использование:
            async with client.stream("POST", url, json={...}) as response:
                async for chunk in response.aiter_bytes():
                    ...
        """
        return _StreamContextManager(self, method, url, **kwargs)


class _StreamContextManager:
    """Context manager для streaming запросов с retry прокси"""

    def __init__(self, smart_client: SmartProxyClient, method: str, url: str, **kwargs):
        self._smart_client = smart_client
        self._method = method
        self._url = url
        self._kwargs = kwargs
        self._client: Optional[httpx.AsyncClient] = None
        self._stream_cm = None

    async def __aenter__(self):
        if not self._smart_client.use_proxy or self._smart_client._is_local_url(self._url):
            self._client = self._smart_client._create_client()
            self._stream_cm = self._client.stream(self._method, self._url, **self._kwargs)
            return await self._stream_cm.__aenter__()

        settings = self._smart_client._get_settings()

        for attempt in range(self._smart_client.MAX_PROXY_RETRIES):
            proxy_url = settings.proxy.get_next_proxy()
            logger.debug(f"Using proxy for stream: {proxy_url[:40] if proxy_url else 'None'}... -> {self._url}")

            try:
                self._client = self._smart_client._create_client(proxy_url)
                self._stream_cm = self._client.stream(self._method, self._url, **self._kwargs)
                return await self._stream_cm.__aenter__()

            except (httpx.ConnectTimeout, httpx.ConnectError) as e:
                settings.proxy.mark_last_proxy_failed()
                if self._client:
                    await self._client.aclose()
                    self._client = None
                self._stream_cm = None

                if attempt < self._smart_client.MAX_PROXY_RETRIES - 1:
                    logger.warning(
                        f"Proxy {proxy_url} failed ({type(e).__name__}), "
                        f"switching to next proxy (attempt {attempt + 2}/{self._smart_client.MAX_PROXY_RETRIES})"
                    )
                else:
                    logger.error(f"All proxy attempts failed for {self._url}")
                    raise

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._stream_cm:
            await self._stream_cm.__aexit__(exc_type, exc_val, exc_tb)
        if self._client:
            await self._client.aclose()


def get_httpx_client(timeout: float = 30.0, proxy: bool = False, **kwargs) -> SmartProxyClient:
    """
    Создает HTTP клиент с умной ротацией прокси.

    Args:
        timeout: Таймаут запросов
        proxy: Использовать прокси с автоматической ротацией при ошибках
        **kwargs: Дополнительные параметры для httpx.AsyncClient

    Returns:
        SmartProxyClient с автоматическим retry
    """
    return SmartProxyClient(timeout=timeout, use_proxy=proxy, **kwargs)
