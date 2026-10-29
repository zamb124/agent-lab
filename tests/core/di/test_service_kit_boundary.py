"""Service Kit на process boundary: один alias ``Di`` в FastAPI, TaskIQ и WS-каталоге команд."""

from __future__ import annotations

from typing import Annotated

import httpx2
import pytest
from fastapi import APIRouter, FastAPI
from taskiq import InMemoryBroker, TaskiqState
from taskiq.kicker import AsyncKicker

from core.di import (
    ServiceDi,
    build_di,
    clear_task_di,
    http_di,
    require_task_di,
    reset_app_di,
    set_app_di,
    set_task_di,
    task_di,
)
from core.models.base import StrictBaseModel
from core.models.identity_models import User
from core.websocket import Operation, RegisteredOperation, register_operations
from core.websocket.command_router import dispatch_ws_command


class Greeter:
    def greet(self, name: str) -> str:
        return f"hello {name}"


class GreeterDi(ServiceDi):
    greeter: Greeter


class Clock:
    pass


class ClockDi(ServiceDi):
    clock: Clock


Di = Annotated[GreeterDi, http_di(GreeterDi), task_di(GreeterDi)]


class GreetPayload(StrictBaseModel):
    name: str


class Greeting(StrictBaseModel):
    greeting: str


router = APIRouter()


@router.get("/greet/{name}")
async def greet(name: str, di: Di) -> Greeting:
    return Greeting(greeting=di.greeter.greet(name))


async def op_greeting_say(payload: GreetPayload, *, user: User, di: GreeterDi) -> Greeting:
    return Greeting(greeting=f"{di.greeter.greet(payload.name)} from {user.user_id}")


def _greeter_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


async def _get(app: FastAPI, path: str) -> httpx2.Response:
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://kit") as client:
        return await client.get(path)


async def test_http_route_reads_components_from_the_app_di() -> None:
    app = _greeter_app()

    async with build_di(GreeterDi, roots={}) as di:
        outer_di = set_app_di(app, di)
        try:
            response = await _get(app, "/greet/kit")
        finally:
            reset_app_di(app, outer_di)

    assert response.status_code == 200
    assert response.json() == {"greeting": "hello kit"}


async def test_http_route_fails_closed_before_the_lifespan_opens_di() -> None:
    app = _greeter_app()

    with pytest.raises(RuntimeError, match="Service DI is not open"):
        _ = await _get(app, "/greet/kit")


async def test_http_route_rejects_the_di_of_another_process() -> None:
    app = _greeter_app()

    async with build_di(ClockDi, roots={}) as di:
        outer_di = set_app_di(app, di)
        try:
            with pytest.raises(RuntimeError, match="ASGI app DI is ClockDi, the route expects GreeterDi"):
                _ = await _get(app, "/greet/kit")
        finally:
            reset_app_di(app, outer_di)


async def test_nested_lifespan_restores_the_outer_di() -> None:
    app = _greeter_app()

    async with build_di(GreeterDi, roots={}) as outer, build_di(GreeterDi, roots={}) as inner:
        outer_previous = set_app_di(app, outer)
        inner_previous = set_app_di(app, inner)
        reset_app_di(app, inner_previous)
        response = await _get(app, "/greet/outer")
        reset_app_di(app, outer_previous)

    assert inner_previous is outer
    assert outer_previous is None
    assert response.json() == {"greeting": "hello outer"}


async def test_taskiq_task_reads_components_from_the_worker_di(unique_id: str) -> None:
    broker = InMemoryBroker(await_inplace=True)
    task_name = f"kit_di_greet_{unique_id}"

    @broker.task(task_name=task_name)
    async def greet_task(name: str, di: Di) -> str:
        return di.greeter.greet(name)

    kicker: AsyncKicker[..., str] = AsyncKicker(task_name, broker, {})
    async with build_di(GreeterDi, roots={}) as di:
        set_task_di(broker.state, di)
        await broker.startup()
        try:
            task = await kicker.kiq(name="worker")
            result = await task.wait_result(timeout=5)
        finally:
            await broker.shutdown()
            clear_task_di(broker.state)

    _ = greet_task
    assert result.is_err is False
    assert result.return_value == "hello worker"


def test_worker_shutdown_after_a_failed_startup_clears_an_unpublished_di() -> None:
    state = TaskiqState()

    clear_task_di(state)

    with pytest.raises(RuntimeError, match="the worker startup did not build it"):
        _ = require_task_di(state, GreeterDi)


async def test_ws_command_runs_the_operation_with_the_owner_di(unique_id: str) -> None:
    command_type = f"kit/greeting/say_{unique_id}_requested"
    catalog: dict[str, RegisteredOperation[GreeterDi]] = {
        command_type: Operation(payload_model=GreetPayload, fn=op_greeting_say),
    }
    register_operations(catalog, GreeterDi)
    user = User(user_id=f"user-{unique_id}", name="Kit")

    async with build_di(GreeterDi, roots={}) as di:
        reply = await dispatch_ws_command(command_type, {"name": "ws"}, user, di)

    assert reply == (
        f"kit/greeting/say_{unique_id}_succeeded",
        {"greeting": f"hello ws from user-{unique_id}"},
    )


async def test_ws_command_fails_when_the_owner_app_has_another_di(unique_id: str) -> None:
    command_type = f"kit/greeting/say_{unique_id}_requested"
    catalog: dict[str, RegisteredOperation[GreeterDi]] = {
        command_type: Operation(payload_model=GreetPayload, fn=op_greeting_say),
    }
    register_operations(catalog, GreeterDi)
    user = User(user_id=f"user-{unique_id}", name="Kit")

    async with build_di(ClockDi, roots={}) as di:
        reply = await dispatch_ws_command(command_type, {"name": "ws"}, user, di)

    detail = "command expects GreeterDi, the owner app DI is ClockDi"
    assert reply == (
        f"kit/greeting/say_{unique_id}_failed",
        {"error_code": "internal", "error_detail": detail, "detail": detail},
    )
