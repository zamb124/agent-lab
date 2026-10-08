"""Порт слушающего сокета. ``getsockname()[1]`` в stub — Any."""

import socket
from typing import cast


def listening_tcp_port(sock: socket.socket, *, label: str) -> int:
    port_raw = cast(object, sock.getsockname()[1])
    if isinstance(port_raw, bool) or not isinstance(port_raw, int):
        raise RuntimeError(f"{label} port must be int")
    if port_raw < 1 or port_raw > 65535:
        raise RuntimeError(f"{label} port out of range")
    return port_raw
