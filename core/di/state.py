"""Где живёт собранный DI процесса: ``app.state.di`` (ASGI) и ``TaskiqState.di`` (worker).

Состояния Starlette и TaskIQ нетипизированы; типизированная граница — только здесь.
Вложенный lifespan того же приложения (ASGI-клиенты в тестах) восстанавливает внешний DI.
"""

from __future__ import annotations

from typing import Protocol, cast

from starlette.applications import Starlette
from starlette.requests import HTTPConnection
from taskiq import TaskiqState

from core.di.kit import ServiceDi


class _DiState(Protocol):
    di: ServiceDi


def _app_of(source: HTTPConnection | Starlette) -> Starlette:
    if isinstance(source, Starlette):
        return source
    return cast(Starlette, source.app)


def set_app_di(app: Starlette, di: ServiceDi) -> ServiceDi | None:
    """Открыть DI приложения; результат — DI внешнего lifespan для ``reset_app_di``."""
    previous = cast(_DiState, cast(object, app.state)).di if hasattr(app.state, "di") else None
    app.state.di = di
    return previous


def reset_app_di(app: Starlette, previous: ServiceDi | None) -> None:
    if previous is None:
        del app.state.di
        return
    app.state.di = previous


def app_di(source: HTTPConnection | Starlette) -> ServiceDi:
    app = _app_of(source)
    if not hasattr(app.state, "di"):
        raise RuntimeError("Service DI is not open: the ASGI lifespan is not running")
    return cast(_DiState, cast(object, app.state)).di


def set_task_di(state: TaskiqState, di: ServiceDi) -> None:
    state.di = di


def clear_task_di(state: TaskiqState) -> None:
    """Снять DI со state; TaskIQ зовёт shutdown и после startup, который DI не опубликовал."""
    if "di" in state:
        del state.di


def task_state_di(state: TaskiqState) -> ServiceDi:
    if "di" not in state:
        raise RuntimeError("Service DI is not open: the worker startup did not build it")
    return cast(_DiState, cast(object, state)).di
