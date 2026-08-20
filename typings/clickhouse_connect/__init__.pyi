"""Typed surface used by the platform."""

from clickhouse_connect.driver.asyncclient import AsyncClient

async def get_async_client(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    database: str,
    secure: bool,
    verify: bool,
    connect_timeout: int = 10,
    send_receive_timeout: int = 300,
) -> AsyncClient: ...
