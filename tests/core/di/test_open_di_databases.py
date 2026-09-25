"""open_di держит пулы Oxyde процесса: вложенный DI не закрывает пулы внешнего владельца."""

from __future__ import annotations

import pytest
from oxyde.db.registry import get_connection

from core.config import get_settings
from core.di import ProcessIdentity, ServiceDi, open_di


class Probe:
    pass


class NestedProcessDi(ServiceDi):
    probe: Probe


@pytest.mark.asyncio
async def test_nested_open_di_exit_keeps_pools_of_the_outer_owner() -> None:
    settings = get_settings()
    outer = ProcessIdentity(service_name="outer", files_route_segment="outer")
    inner = ProcessIdentity(service_name="inner", files_route_segment="inner")

    async with open_di(NestedProcessDi, settings=settings, identity=outer, database="shared_url"):
        async with open_di(NestedProcessDi, settings=settings, identity=inner, database="flows_url"):
            pass

        outer_default = await get_connection("default")

    assert outer_default.name == "default"
    still_open = await get_connection("default")
    assert still_open.name == "default"
