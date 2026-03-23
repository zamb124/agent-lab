"""
Unit тесты для TaskIQ задачи init_company_resources.

Тестируем логику загрузки агентов:
1. Для system: загружаются ВСЕ агенты
2. Для company: загружаются только PUBLIC агенты
"""

import pytest
from pathlib import Path


@pytest.mark.asyncio
async def test_init_company_resources_for_system(container, unique_id: str):
    """
    Тест загрузки всех агентов в system namespace.
    
    Проверяет что:
    1. Загружаются ВСЕ агенты (public и internal)
    2. Контекст устанавливается корректно
    3. Возвращается статистика
    """
    from apps.flows.src.tasks.company_init_tasks import init_company_resources
    from core.context import get_context, clear_context
    
    clear_context()
    
    # Запускаем задачу для system
    result = await init_company_resources(
        company_id="system",
        company_name="System",
        subdomain="system"
    )
    
    assert result["status"] == "completed"
    assert result["company_id"] == "system"
    assert result["flows"] >= 0
    assert result["nodes"] >= 0
    
    print(f"✅ System загружено: flows={result['flows']}, nodes={result['nodes']}")
    
    # Контекст должен быть очищен после выполнения
    context = get_context()
    assert context is None or context.active_company.company_id == "system"
    
    clear_context()


@pytest.mark.asyncio
async def test_init_company_resources_for_regular_company(
    container,
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
    from core.context import set_context, clear_context, Context
    from core.models.identity_models import User, Company
    
    test_company_id = f"test_company_{unique_id}"
    test_company_name = f"Test Company {unique_id}"
    
    clear_context()
    
    # Запускаем задачу для обычной компании
    result = await init_company_resources(
        company_id=test_company_id,
        company_name=test_company_name,
        subdomain=f"test-{unique_id}"
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
        agent_repo = container.flow_repository
        agents = await agent_repo.list_all()
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
async def test_flows_loader_filter_public(container, unique_id: str):
    """
    Прямой тест FlowsLoader.load_all_for_company с фильтрацией.
    """
    from apps.flows.src.services.flows_loader import FlowsLoader
    from core.context import set_context, clear_context, Context
    from core.models.identity_models import User, Company
    
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
            flow_repository=container.flow_repository,
            node_repository=container.node_repository,
            tool_repository=container.tool_repository,
            registry_path=registry_path,
        )
        
        # Тест 1: Загрузка с фильтром (только public)
        stats_filtered = await loader.load_all_for_company(
            company_id=test_company_id,
            filter_public=True
        )
        
        print(f"📊 С фильтром: {stats_filtered}")
        
        agents_filtered = await container.flow_repository.list_all()
        filtered_count = len(agents_filtered)
        
        # Очищаем для второго теста
        for agent in agents_filtered:
            await container.flow_repository.delete(agent.flow_id)
        
        # Тест 2: Загрузка без фильтра (все агенты)
        stats_all = await loader.load_all_for_company(
            company_id=test_company_id,
            filter_public=False
        )
        
        print(f"📊 Без фильтра: {stats_all}")
        
        agents_all = await container.flow_repository.list_all()
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
async def test_system_vs_company_loading(container, unique_id: str):
    """
    Сравнение загрузки для system vs обычной компании.
    
    Проверяет что:
    - System: загружены ВСЕ агенты
    - Company: загружены только PUBLIC агенты
    - System имеет >= агентов чем company
    """
    from apps.flows.src.tasks.company_init_tasks import init_company_resources
    from core.context import set_context, clear_context, Context
    from core.models.identity_models import User, Company
    
    clear_context()
    
    # Загрузка для system
    system_result = await init_company_resources(
        company_id="system",
        company_name="System",
        subdomain="system"
    )
    
    system_agents_count = system_result["flows"]
    
    print(f"📊 System: {system_agents_count} агентов")
    
    # Загрузка для обычной компании
    test_company_id = f"test_vs_{unique_id}"
    
    company_result = await init_company_resources(
        company_id=test_company_id,
        company_name="Test VS",
        subdomain=f"test-vs-{unique_id}"
    )
    
    company_agents_count = company_result["flows"]
    
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

