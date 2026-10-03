"""Граница ``redis.asyncio.Redis.from_url``.

Stub ``from_url`` частично неизвестен, поэтому открытие клиента живёт здесь одним ``cast``.
"""

from typing import Protocol, cast

from redis.asyncio.client import Redis


class _RedisFromUrl[T](Protocol):
    def __call__(
        self,
        url: str,
        *,
        decode_responses: bool = ...,
        socket_connect_timeout: int = ...,
        socket_timeout: int = ...,
    ) -> T: ...


def redis_client_from_url[T](
    client_type: type[T],
    url: str,
    *,
    decode_responses: bool,
    socket_connect_timeout: int | None = None,
    socket_timeout: int | None = None,
) -> T:
    _ = client_type
    from_url = cast(_RedisFromUrl[T], Redis.from_url)
    if socket_connect_timeout is None and socket_timeout is None:
        return from_url(url, decode_responses=decode_responses)
    if socket_connect_timeout is None or socket_timeout is None:
        raise ValueError("Redis socket timeouts are set together")
    return from_url(
        url,
        decode_responses=decode_responses,
        socket_connect_timeout=socket_connect_timeout,
        socket_timeout=socket_timeout,
    )
