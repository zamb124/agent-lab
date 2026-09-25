"""Доставка DI на process boundary: FastAPI, TaskIQ и прямое извлечение.

Один alias сервиса ``Di = Annotated[SvcDi, http_di(SvcDi), task_di(SvcDi)]`` работает
и в HTTP/WS-хендлерах, и в задачах TaskIQ: FastAPI берёт свой ``Depends``,
TaskIQ читает метаданные с конца и берёт свой ``Dependency``.
"""

from typing import Annotated, TypeVar

from fastapi import params
from starlette.applications import Starlette
from starlette.requests import HTTPConnection
from taskiq import Context, TaskiqState
from taskiq_dependencies.dependency import Dependency

from core.di.kit import ServiceDi
from core.di.state import app_di, task_state_di

DiT = TypeVar("DiT", bound=ServiceDi)


def require_di(source: HTTPConnection | Starlette, di_class: type[DiT]) -> DiT:
    di = app_di(source)
    if not isinstance(di, di_class):
        raise RuntimeError(
            f"ASGI app DI is {type(di).__qualname__}, the route expects {di_class.__qualname__}"
        )
    return di


def require_task_di(state: TaskiqState, di_class: type[DiT]) -> DiT:
    di = task_state_di(state)
    if not isinstance(di, di_class):
        raise RuntimeError(
            f"worker DI is {type(di).__qualname__}, the task expects {di_class.__qualname__}"
        )
    return di


def http_di(di_class: type[ServiceDi]) -> params.Depends:
    def di_from_connection(connection: HTTPConnection) -> ServiceDi:
        return require_di(connection, di_class)

    return params.Depends(dependency=di_from_connection)


def task_di(di_class: type[ServiceDi]) -> Dependency:
    def di_from_task(context: Annotated[Context, Dependency()]) -> ServiceDi:
        return require_task_di(context.state, di_class)

    return Dependency(di_from_task)
