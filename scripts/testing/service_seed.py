"""Общая подготовка данных тест-стека одним процессом вместо сида в каждом granian-воркере.

Вызывается из ``scripts.testing.stack up`` в две фазы:

- ``service_seed`` — до спауна процессов: reseed системной компании CRM.
  Granian-воркеры crm потом идут insert-only fast-path по ``CompanyMapping``
  вместо полного reseed под ``pg_advisory_lock`` в каждом процессе.
- ``service_seed after`` — после readiness стека: сид каталога flows и reconcile
  stale-задач CRM. Части сида ходят по HTTP в secrets/realtime/MCP-peers — на
  спаде старта они недоступны, сид не завершается и маркер не пишется, поэтому
  каждый воркер пересиживал каталог под локом. После readiness peers живы.

Сид бежит через тот же ``open_di`` + lifecycle-рецепты, что и ASGI-lifespan
сервиса: одинаковый код пути, без дублирования шагов.
"""

import asyncio
import sys

from apps.crm.config import CRMSettings
from apps.crm.di import CrmDi
from apps.crm.main import crm_test_stack_reconcile, crm_test_stack_seed
from apps.flows.config import FlowSettings
from apps.flows.di import FlowsDi
from apps.flows.main import seed_testing_bundle
from core.app.factory import prepare_service_settings
from core.di import recipe
from core.di.kit import ProcessIdentity, Recipe
from core.di.process import open_di


async def _seed_flows_bundle() -> None:
    settings, _project_root, files_segment = prepare_service_settings(
        "flows", FlowSettings, documentation_gateway_prefix=None
    )
    async with open_di(
        FlowsDi,
        settings=settings,
        identity=ProcessIdentity(
            service_name="flows", files_route_segment=files_segment
        ),
        database="flows_url",
        lifecycle=(recipe(seed_testing_bundle),),
    ):
        pass


async def _run_crm(lifecycle: tuple[Recipe, ...]) -> None:
    settings, _project_root, files_segment = prepare_service_settings(
        "crm", CRMSettings, documentation_gateway_prefix=None
    )
    async with open_di(
        CrmDi,
        settings=settings,
        identity=ProcessIdentity(service_name="crm", files_route_segment=files_segment),
        database="crm_url",
        lifecycle=lifecycle,
    ):
        pass


async def _main() -> None:
    if "after" in sys.argv[1:]:
        await _seed_flows_bundle()
        await _run_crm((recipe(crm_test_stack_reconcile),))
        return
    await _run_crm((recipe(crm_test_stack_seed),))


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()) or 0)
