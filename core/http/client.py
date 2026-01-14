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
        connect_timeout = 15.0

        if self.use_proxy:
            settings = self._get_settings()
            connect_timeout = settings.proxy.connect_timeout

        return httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout, connect=connect_timeout),
            proxy=proxy_url,
            trust_env=False,
            **self.kwargs,
        )

    async def _request_with_retry(self, method: str, url: str, **kwargs) -> httpx.Response:
        """
        Выполняет запрос с автоматическим retry при таймауте прокси.
        """
        if not self.use_proxy:
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
        if not self._smart_client.use_proxy:
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
