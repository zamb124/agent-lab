"""Вспомогательные функции для aiohttp TCPSite на свободном порту (xdist без коллизий)."""

from aiohttp import web


def tcp_site_assigned_port(site: web.TCPSite) -> int:
    server = site._server
    if server is None:
        raise RuntimeError("TCPSite не запущен")
    sockets = server.sockets  # pyright: ignore[reportAttributeAccessIssue]
    if not sockets:
        raise RuntimeError("У сервера нет сокетов после start()")
    return sockets[0].getsockname()[1]
