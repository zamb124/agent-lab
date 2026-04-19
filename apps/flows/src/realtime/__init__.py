"""WS realtime для сервиса flows: command-handlers и push-события.

Регистрация handler'ов выполняется в `on_startup` сервиса
(`apps/flows/main.py`) вызовом `register_flows_ws_commands()`.
"""

from apps.flows.src.realtime.command_router import register_flows_ws_commands

__all__ = ["register_flows_ws_commands"]
