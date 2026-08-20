"""Typed surface used by the platform."""

from ssl import SSLContext

from asyncmy.connection import Connection

async def connect(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    db: str,
    ssl: SSLContext | None,
    connect_timeout: int,
) -> Connection: ...
