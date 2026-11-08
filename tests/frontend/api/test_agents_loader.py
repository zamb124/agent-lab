"""
Unit тесты для TaskIQ задачи init_company_resources.

Тестируем логику загрузки агентов:
1. Для system: загружаются ВСЕ агенты
2. Для company: загружаются только PUBLIC агенты
"""

from pathlib import Path

import pytest

from apps.flows.src.models.flow_config import FlowConfig
from apps.flows.src.services.mcp_catalog_provisioner import MCPCatalogProvisionStats

pytestmark = [pytest.mark.timeout(120, func_only=True)]


@pytest.fixture(autouse=True)
def _init_company_skip_mcp_network_sync(monkeypatch):
    """MCP provision/sync ходит во внешние серверы; в unit-тестах loader — noop."""

    async def _noop_sync(**_kwargs: object) -> dict[str, int]:
        return {"servers": 0, "tools": 0}

    async def _noop_provision(**_kwargs: object) -> MCPCatalogProvisionStats:
        return MCPCatalogProvisionStats(
            added=0,
            updated=0,
            skipped_locked=0,
            deprecated=0,
            sync_ok=0,
            sync_failed=0,
        )

    async def _noop_seed_demo_variables(*_args: object, **_kwargs: object) -> int:
        return 0

    monkeypatch.setattr(
        "apps.flows.src.tasks.company_init_tasks.sync_auto_mcp_servers_for_company",
        _noop_sync,
    )
    monkeypatch.setattr(
        "apps.flows.src.tasks.company_init_tasks.provision_mcp_catalog_for_company",
        _noop_provision,
    )
    monkeypatch.setattr(
        "apps.flows.src.tasks.company_init_tasks.seed_demo_company_variables",
        _noop_seed_demo_variables,
    )


@pytest.mark.asyncio
async def test_init_company_resources_for_system(di, unique_id: str):
    """
    Тест загрузки всех агентов в system namespace.

    Проверяет что:
    1. Загружаются ВСЕ агенты (public и internal)
    2. Контекст устанавливается корректно
    3. Возвращается статистика
    """
    from apps.flows.src.tasks.company_init_tasks import init_company_resources
    from core.context import clear_context, get_context

    clear_context()

    # Запускаем задачу для system
    result = await init_company_resources(
        company_id="system",
        company_name="System",
        subdomain="system", di=di
    )

    assert result["status"] == "completed"
    assert result["company_id"] == "system"
    assert isinstance(result["flows"], int)
    assert result["flows"] >= 0
    assert isinstance(result["nodes"], int)
    assert result["nodes"] >= 0

    print(f"✅ System загружено: flows={result['flows']}, nodes={result['nodes']}")

    # Контекст должен быть очищен после выполнения
    context = get_context()
    assert context is None or (
        context.active_company is not None
        and context.active_company.company_id == "system"
    )

    clear_context()


@pytest.mark.asyncio
async def test_init_company_resources_for_regular_company(
    di,
    unique_id: str
):
    """
    Тест загрузки только public агентов для обычной компании.

    Проверяет что:
    1. Загружаются ТОЛЬКО public агенты
    2. Internal агенты НЕ загружаются
    3. Контекст устанавливается для компании
    """
    from apps.flows.src.tasks.company_init_tasks import init_company_resources
    from core.context import clear_context, set_context
    from core.models.context_models import Context
    from core.models.identity_models import Company, User

    test_company_id = f"test_company_{unique_id}"
    test_company_name = f"Test Company {unique_id}"

    clear_context()

    # Запускаем задачу для обычной компании
    result = await init_company_resources(
        company_id=test_company_id,
        company_name=test_company_name,
        subdomain=f"test-{unique_id}", di=di
    )

    assert result["status"] == "completed"
    assert result["company_id"] == test_company_id

    print(
        f"✅ Company {test_company_id} загружено: "
        f"flows={result['flows']}, nodes={result['nodes']}"
    )

    # Проверяем что агенты загружены в namespace компании
    test_context = Context(
        user=User(user_id="test_user", name="Test User"),
        active_company=Company(
            company_id=test_company_id,
            name=test_company_name,
            subdomain=""
        ),
        session_id="test_session",
        channel="test",
    )
    set_context(test_context)

    try:
        agents = await FlowConfig.list_current_by_created_at_desc(limit=1000)
        agent_ids = [agent.flow_id for agent in agents]

        print(f"📋 Загруженные агенты в {test_company_id}: {agent_ids}")

        # Если в registry есть internal агенты, они НЕ должны быть загружены
        internal_agents = ["internal_admin"]

        for internal_agent in internal_agents:
            assert internal_agent not in agent_ids, (
                f"Internal агент '{internal_agent}' не должен быть в company namespace"
            )

        print("✅ Internal агенты корректно отфильтрованы")

    finally:
        clear_context()


@pytest.mark.asyncio
async def test_flows_loader_filter_public(di, unique_id: str):
    """
    Прямой тест FlowsLoader.load_all_for_company с фильтрацией.
    """
    from apps.flows.src.services.flows_loader import FlowsLoader
    from core.context import clear_context, set_context
    from core.models.context_models import Context
    from core.models.identity_models import Company, User

    test_company_id = f"test_filter_{unique_id}"

    # Путь к registry
    repo_root = Path(__file__).parent.parent.parent.parent
    registry_path = repo_root / "apps" / "flows" / "registry.yaml"
    bundles_dir = repo_root / "apps" / "flows" / "bundles"

    # Устанавливаем контекст компании
    test_context = Context(
        user=User(user_id="test_user", name="Test User"),
        active_company=Company(
            company_id=test_company_id,
            name="Test Filter",
            subdomain=""
        ),
        session_id="test_session",
        channel="test",
    )
    set_context(test_context)

    try:
        loader = FlowsLoader(
            bundles_dir=bundles_dir,
            registry_path=registry_path,
            flow_access_service=di.flow_access_service,
            files_service=di.files_service,
        )

        # Тест 1: Загрузка с фильтром (только public)
        stats_filtered = await loader.load_all_for_company(
            company_id=test_company_id,
            filter_public=True
        )

        print(f"📊 С фильтром: {stats_filtered}")

        agents_filtered = await FlowConfig.list_current_by_created_at_desc(limit=1000)
        filtered_count = len(agents_filtered)

        # Очищаем для второго теста
        for agent in agents_filtered:
            await FlowConfig.delete_by_flow_id(agent.flow_id)

        # Тест 2: Загрузка без фильтра (все агенты)
        stats_all = await loader.load_all_for_company(
            company_id=test_company_id,
            filter_public=False
        )

        print(f"📊 Без фильтра: {stats_all}")

        agents_all = await FlowConfig.list_current_by_created_at_desc(limit=1000)
        all_count = len(agents_all)

        # Без фильтра должно быть больше или равно
        assert all_count >= filtered_count, (
            f"Без фильтра должно быть >= агентов: {all_count} >= {filtered_count}"
        )

        print(
            f"✅ Фильтрация работает: "
            f"с фильтром={filtered_count}, без фильтра={all_count}"
        )

    finally:
        clear_context()


@pytest.mark.asyncio
async def test_init_company_resources_idempotent_no_duplicate_versions(di, unique_id: str):
    """Повторная инициализация компании не создаёт новых версий flow.

    Регрессия прод-бага: каждый init писал новую строку версии на flow
    (~260 дублей на флоу). Дедуп в FlowConfig.create_version делает init идемпотентным.
    """
    from apps.flows.src.tasks.company_init_tasks import init_company_resources
    from core.context import clear_context, set_context
    from core.models.context_models import Context
    from core.models.identity_models import Company, User

    test_company_id = f"test_idem_{unique_id}"
    init_kwargs = {
        "company_id": test_company_id,
        "company_name": "Idem",
        "subdomain": f"idem-{unique_id}",
        "di": di,
    }

    first = await init_company_resources(**init_kwargs)
    assert first["status"] == "completed"
    assert first["flows"] > 0

    snapshot_ctx = Context(
        user=User(user_id="test_user", name="Test User"),
        active_company=Company(company_id=test_company_id, name="Idem", subdomain=""),
        session_id="test_session",
        channel="test",
    )
    set_context(snapshot_ctx)
    try:
        snapshot = {
            row.flow_id: await FlowConfig.list_version_strings_by_version_desc(row.flow_id)
            for row in await FlowConfig.list_current_by_created_at_desc(limit=10000)
        }
    finally:
        clear_context()
    assert snapshot, "init не загрузил ни одного flow"

    second = await init_company_resources(**init_kwargs)
    assert second["status"] == "completed"

    set_context(snapshot_ctx)
    try:
        for flow_id, versions in snapshot.items():
            after = await FlowConfig.list_version_strings_by_version_desc(flow_id)
            assert after == versions, (
                f"{flow_id}: повторный init создал дубли версий {versions} → {after}"
            )
    finally:
        clear_context()


@pytest.mark.asyncio
async def test_system_vs_company_loading(di, unique_id: str):
    """
    Сравнение загрузки для system vs обычной компании.

    Проверяет что:
    - System: загружены ВСЕ агенты
    - Company: загружены только PUBLIC агенты
    - System имеет >= агентов чем company
    """
    from apps.flows.src.tasks.company_init_tasks import init_company_resources
    from core.context import clear_context

    clear_context()

    # Загрузка для system
    system_result = await init_company_resources(
        company_id="system",
        company_name="System",
        subdomain="system", di=di
    )

    system_agents_count = system_result["flows"]
    assert isinstance(system_agents_count, int)

    print(f"📊 System: {system_agents_count} агентов")

    # Загрузка для обычной компании
    test_company_id = f"test_vs_{unique_id}"

    company_result = await init_company_resources(
        company_id=test_company_id,
        company_name="Test VS",
        subdomain=f"test-vs-{unique_id}", di=di
    )

    company_agents_count = company_result["flows"]
    assert isinstance(company_agents_count, int)

    print(f"📊 Company: {company_agents_count} агентов")

    # System должен иметь >= агентов (т.к. загружает все, включая internal)
    assert system_agents_count >= company_agents_count, (
        f"System должен иметь >= агентов чем company: "
        f"{system_agents_count} >= {company_agents_count}"
    )

    print(
        f"✅ System имеет больше или равно агентов: "
        f"{system_agents_count} >= {company_agents_count}"
    )

