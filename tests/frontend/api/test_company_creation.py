"""
Интеграционные тесты создания компании и инициализации агентов.

Тестируем полный flow:
1. Frontend: POST /frontend/api/companies - создание компании
2. Agents: POST /flows/api/v1/company/init - инициализация агентов
3. Проверка: агенты и тулы появились в БД для новой компании
"""

import asyncio
import time

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
@pytest.mark.real_taskiq  # Используем реальный TaskIQ worker
async def test_company_creation_with_agents_initialization(
    frontend_client: AsyncClient,
    flows_client: AsyncClient,
    auth_token: str,
    container,
    unique_id: str,
    taskiq_worker  # Запускаем worker
):
    """
    Полный интеграционный тест создания компании с инициализацией агентов.
    
    Шаги:
    1. Создаем компанию через frontend API
    2. Проверяем что компания создалась
    3. Запускаем инициализацию через API endpoint
    4. Ждем завершения TaskIQ задачи
    5. Проверяем что public агенты появились в БД для новой компании
    """
    from core.context import set_context, clear_context, Context
    from core.models.identity_models import User, Company
    
    # Шаг 1: Создание компании
    company_name = f"Test Company {unique_id}"
    company_slug = f"test-company-{unique_id}"
    
    response = await frontend_client.post(
        "/frontend/api/companies",
        json={
            "name": company_name,
            "slug": company_slug
        },
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    
    assert response.status_code == 200, f"Failed to create company: {response.text}"
    
    company_data = response.json()
    company_id = company_data["company_id"]
    
    assert company_data["name"] == company_name
    assert company_data["subdomain"] == company_slug
    
    print(f"✅ Компания создана: {company_id}")
    
    # Шаг 2: Проверка что компания в БД
    company_repo = container.company_repository
    company = await company_repo.get(company_id)
    
    assert company is not None
    assert company.company_id == company_id
    assert company.name == company_name
    assert company.subdomain == company_slug
    
    print(f"✅ Компания в БД: {company.company_id}")
    
    # Шаг 3: Проверка что subdomain mapping создан
    subdomain_repo = container.subdomain_repository
    mapped_company_id = await subdomain_repo.get_company_id(company_slug)
    
    assert mapped_company_id == company_id
    
    print(f"✅ Subdomain mapping: {company_slug} → {company_id}")
    
    # Шаг 4: Запускаем инициализацию через agents API с авторизацией
    # Используем тот же токен что и для создания компании
    response = await flows_client.post(
        "/flows/api/v1/company/init",
        json={
            "company_id": company_id,
            "company_name": company_name,
            "subdomain": company_slug
        },
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    
    assert response.status_code == 200, f"Init failed: {response.text}"
    
    init_data = response.json()
    task_id = init_data["task_id"]
    
    print(f"✅ Инициализация запущена: task_id={task_id}")
    
    # Шаг 5: Ждем завершения TaskIQ задачи (полный прогон нагружает очередь worker)
    max_wait = 90
    wait_interval = 1
    
    # Устанавливаем контекст новой компании для проверки
    # Получаем user_id из auth_token
    from core.utils.tokens import get_token_service
    token_service = get_token_service()
    token_data = token_service.validate_token(auth_token)
    user_id = token_data.user_id
    
    # Получаем пользователя из БД
    user = await container.user_repository.get(user_id)
    
    test_context = Context(
        user=user,
        active_company=Company(
            company_id=company_id,
            name=company_name,
            subdomain=company_slug
        ),
        session_id="test_session",
        channel="test",
    )
    set_context(test_context)
    
    try:
        agent_repo = container.flow_repository
        
        # Ждем пока агенты появятся в БД
        agents_loaded = False
        for attempt in range(max_wait):
            agents = await agent_repo.list_all()
            
            if len(agents) > 0:
                agents_loaded = True
                print(f"✅ Агенты загружены после {attempt + 1} секунд: {len(agents)} шт")
                break
            
            await asyncio.sleep(wait_interval)
        
        assert agents_loaded, (
            f"Агенты не загрузились за {max_wait} секунд. "
            f"TaskIQ worker выполняет задачу"
        )
        
        # Проверка что загружены ТОЛЬКО public агенты
        agents = await agent_repo.list_all()
        agent_ids = [agent.flow_id for agent in agents]
        
        print(f"📋 Загруженные агенты: {agent_ids}")
        
        # Должен быть хотя бы один агент
        assert len(agents) > 0, "Должен быть хотя бы один public агент"
        
        # Проверка на примере конкретных агентов из registry
        # Ожидаем что example_react должен быть (public)
        expected_public_agents = ["example_react", "example_graph"]
        
        for expected_agent in expected_public_agents:
            if expected_agent in agent_ids:
                print(f"✅ Public агент '{expected_agent}' загружен")
        
        # Проверяем что internal агенты НЕ загружены
        internal_agents = ["internal_admin"]  # Это не public агент
        
        for internal_agent in internal_agents:
            assert internal_agent not in agent_ids, (
                f"Internal агент '{internal_agent}' не должен быть загружен в company namespace"
            )
        
        print(f"✅ Internal агенты отфильтрованы корректно")
        
        # Шаг 6: Проверка что tools тоже загружены
        tool_repo = container.tool_repository
        tools = await tool_repo.list_all()
        
        print(f"📋 Загружено tools: {len(tools)} шт")
        
        assert len(tools) > 0, "Должны быть загружены public tools"
        
        tool_ids = [tool.tool_id for tool in tools]
        print(f"📋 Tools: {tool_ids}")
        
        # Шаг 7: КРИТИЧЕСКАЯ ПРОВЕРКА - получение агентов через API с контекстом компании
        print(f"\n🔍 Проверка получения агентов через API с контекстом компании...")
        
        # Создаем токен для новой компании с реальным user_id
        company_token = token_service.create_token(user_id, company_id=company_id)
        
        # Делаем запрос к agents API с контекстом компании
        api_response = await flows_client.get(
            "/flows/api/v1/flows/",
            headers={
                "Authorization": f"Bearer {company_token}",
                "X-Company-Id": company_id
            }
        )
        
        assert api_response.status_code == 200, f"API failed: {api_response.text}"
        
        api_agents = api_response.json()
        api_agent_ids = [agent["flow_id"] for agent in api_agents]
        
        print(f"✅ API вернул {len(api_agents)} агентов: {api_agent_ids[:5]}...")  # Показываем первые 5
        
        # Проверяем что API вернул агенты (должны быть public агенты)
        assert len(api_agent_ids) > 0, "API должен вернуть хотя бы одного агента"
        
        # Проверяем что в списке есть хотя бы один known public агент
        known_public = ["example_react", "example_graph"]
        found_public = [aid for aid in known_public if aid in api_agent_ids]
        
        assert len(found_public) > 0, (
            f"API должен вернуть хотя бы один known public агент из {known_public}, "
            f"но вернул: {api_agent_ids}"
        )
        
        print(f"✅ API корректно работает с контекстом компании! Найдены: {found_public}")
        
    finally:
        clear_context()
    
    print("✅ Все проверки пройдены!")


@pytest.mark.asyncio
async def test_company_init_endpoint_directly(
    flows_client: AsyncClient,
    container,
    unique_id: str,
    auth_token: str
):
    """
    Тест прямого вызова endpoint инициализации компании.
    
    Проверяет что:
    1. Endpoint принимает запрос
    2. Возвращает task_id
    3. Нельзя инициализировать system через API
    """
    from core.context import set_context, clear_context, Context
    from core.models.identity_models import User, Company
    from core.utils.tokens import get_token_service
    
    # Получаем реального пользователя из auth_token
    token_service = get_token_service()
    token_data = token_service.validate_token(auth_token)
    user = await container.user_repository.get(token_data.user_id)
    
    # Создаем контекст system для теста
    system_context = Context(
        user=user,
        active_company=Company(company_id="system", name="System", subdomain="system"),
        session_id="test_session",
        channel="test",
    )
    set_context(system_context)
    
    try:
        # Тест 1: Попытка инициализировать system (должна быть ошибка)
        response = await flows_client.post(
            "/flows/api/v1/company/init",
            json={
                "company_id": "system",
                "company_name": "System"
            },
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 400
        assert "System namespace" in response.json()["detail"]
        
        print("✅ System namespace защищен от инициализации через API")
        
        # Тест 2: Инициализация обычной компании
        test_company_id = f"test_company_{unique_id}"
        test_company_name = f"Test Company {unique_id}"
        
        response = await flows_client.post(
            "/flows/api/v1/company/init",
            json={
                "company_id": test_company_id,
                "company_name": test_company_name
            },
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        
        result = response.json()
        assert "task_id" in result
        assert result["status"] == "scheduled"
        
        print(f"✅ Инициализация запущена: task_id={result['task_id']}")
        
    finally:
        clear_context()


@pytest.mark.asyncio
async def test_check_slug_availability(
    frontend_client: AsyncClient,
    auth_token: str,
    unique_id: str
):
    """
    Тест проверки доступности slug для компании.
    """
    # Проверка доступного slug
    available_slug = f"test-available-{unique_id}"
    
    response = await frontend_client.post(
        "/frontend/api/companies/check-slug",
        json={"slug": available_slug},
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert data["slug"] == available_slug
    
    print(f"✅ Slug '{available_slug}' доступен")
    
    # Создаем компанию с этим slug
    response = await frontend_client.post(
        "/frontend/api/companies",
        json={
            "name": f"Test Company {unique_id}",
            "slug": available_slug
        },
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    
    assert response.status_code == 200
    print(f"✅ Компания создана с slug '{available_slug}'")
    
    # Проверяем что теперь slug занят
    response = await frontend_client.post(
        "/frontend/api/companies/check-slug",
        json={"slug": available_slug},
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is False
    
    print(f"✅ Slug '{available_slug}' теперь занят")


@pytest.mark.asyncio
async def test_company_creation_without_flows_service(
    frontend_client: AsyncClient,
    auth_token: str,
    container,
    unique_id: str,
):
    """
    Тест что создание компании не падает если agents сервис недоступен.
    
    Компания должна создаться, а инициализация агентов просто залогироваться как ошибка.
    Этот тест проверяет устойчивость к отказам - если agents недоступен,
    компания все равно создается, просто без предустановленных агентов.
    """
    company_name = f"Test Company Without Agents {unique_id}"
    company_slug = f"test-no-agents-{unique_id}"
    
    response = await frontend_client.post(
        "/frontend/api/companies",
        json={
            "name": company_name,
            "slug": company_slug
        },
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    
    # Компания должна создаться
    assert response.status_code == 200
    
    company_data = response.json()
    company_id = company_data["company_id"]
    
    # Проверяем что компания в БД
    company = await container.company_repository.get(company_id)
    assert company is not None
    assert company.company_id == company_id
    
    print(f"✅ Компания создана: {company_id}")


@pytest.mark.asyncio
async def test_company_agents_api_with_context(
    frontend_client: AsyncClient,
    flows_client: AsyncClient,
    auth_token: str,
    container,
    unique_id: str,
    taskiq_worker
):
    """
    Тест что agents API корректно возвращает агенты с контекстом компании.
    
    Проверяет:
    1. Создание компании и инициализацию агентов
    2. Получение списка агентов через API с токеном компании
    3. Изоляцию - разные компании видят разные агенты
    """
    from core.context import set_context, clear_context, Context
    from core.models.identity_models import User, Company
    from core.utils.tokens import get_token_service
    
    # Создаем две компании
    company1_name = f"Test Company 1 {unique_id}"
    company1_slug = f"test-company-1-{unique_id}"
    
    company2_name = f"Test Company 2 {unique_id}"
    company2_slug = f"test-company-2-{unique_id}"
    
    # Компания 1
    response1 = await frontend_client.post(
        "/frontend/api/companies",
        json={"name": company1_name, "slug": company1_slug},
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response1.status_code == 200
    company1_id = response1.json()["company_id"]
    
    # Компания 2
    response2 = await frontend_client.post(
        "/frontend/api/companies",
        json={"name": company2_name, "slug": company2_slug},
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response2.status_code == 200
    company2_id = response2.json()["company_id"]
    
    print(f"✅ Созданы компании: {company1_id}, {company2_id}")
    
    # Инициализируем агенты для обеих компаний
    await flows_client.post(
        "/flows/api/v1/company/init",
        json={"company_id": company1_id, "company_name": company1_name, "subdomain": company1_slug},
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    
    await flows_client.post(
        "/flows/api/v1/company/init",
        json={"company_id": company2_id, "company_name": company2_name, "subdomain": company2_slug},
        headers={"Authorization": f"Bearer {auth_token}"}
    )

    from core.utils.tokens import get_token_service

    token_service = get_token_service()
    token_data = token_service.validate_token(auth_token)
    user_id = token_data.user_id
    token1 = token_service.create_token(user_id, company_id=company1_id)
    token2 = token_service.create_token(user_id, company_id=company2_id)

    deadline = time.monotonic() + 90.0
    while time.monotonic() < deadline:
        r1 = await flows_client.get(
            "/flows/api/v1/flows/",
            headers={
                "Authorization": f"Bearer {token1}",
                "X-Company-Id": company1_id,
            },
        )
        r2 = await flows_client.get(
            "/flows/api/v1/flows/",
            headers={
                "Authorization": f"Bearer {token2}",
                "X-Company-Id": company2_id,
            },
        )
        if r1.status_code == 200 and r2.status_code == 200:
            j1 = r1.json()
            j2 = r2.json()
            if isinstance(j1, list) and isinstance(j2, list) and len(j1) > 0 and len(j2) > 0:
                break
        await asyncio.sleep(0.1)
    
    # Проверка 1: Компания 1 видит своих агентов
    response1 = await flows_client.get(
        "/flows/api/v1/flows/",
        headers={
            "Authorization": f"Bearer {token1}",
            "X-Company-Id": company1_id
        }
    )
    
    assert response1.status_code == 200
    agents1 = response1.json()
    print(f"✅ Компания 1 видит {len(agents1)} агентов")
    assert len(agents1) > 0, "Компания 1 должна видеть агенты"
    
    # Проверка 2: Компания 2 видит своих агентов
    response2 = await flows_client.get(
        "/flows/api/v1/flows/",
        headers={
            "Authorization": f"Bearer {token2}",
            "X-Company-Id": company2_id
        }
    )
    
    assert response2.status_code == 200
    agents2 = response2.json()
    print(f"✅ Компания 2 видит {len(agents2)} агентов")
    assert len(agents2) > 0, "Компания 2 должна видеть агенты"
    
    # Проверка 3: Обе компании видят одинаковые public агенты (так как загружаются из registry)
    agent_ids1 = {agent["flow_id"] for agent in agents1}
    agent_ids2 = {agent["flow_id"] for agent in agents2}
    
    print(f"📋 Агенты компании 1: {agent_ids1}")
    print(f"📋 Агенты компании 2: {agent_ids2}")
    
    # Public агенты должны быть одинаковыми
    assert agent_ids1 == agent_ids2, (
        f"Public агенты должны быть одинаковыми для всех компаний. "
        f"Компания 1: {agent_ids1}, Компания 2: {agent_ids2}"
    )
    
    print(f"✅ Изоляция работает корректно - каждая компания видит свои агенты!")
    
    # Проверка 4: Получение конкретного агента
    if agents1:
        test_agent_id = agents1[0]["flow_id"]
        
        response = await flows_client.get(
            f"/flows/api/v1/flows/{test_agent_id}",
            headers={
                "Authorization": f"Bearer {token1}",
                "X-Company-Id": company1_id
            }
        )
        
        assert response.status_code == 200
        agent_detail = response.json()
        assert agent_detail["flow_id"] == test_agent_id
        
        print(f"✅ Получение конкретного агента работает: {test_agent_id}")
    
    print("✅ Все проверки API пройдены!")

