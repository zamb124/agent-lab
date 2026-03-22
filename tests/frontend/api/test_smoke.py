"""
Smoke тесты для быстрой проверки работоспособности системы.

Минимальный набор тестов для проверки что:
- Сервисы поднимаются
- Базовые endpoint работают
- Контейнеры корректно настроены
"""

import pytest


@pytest.mark.asyncio
async def test_flows_service_health(flows_client):
    """Проверка что agents сервис работает"""
    # Health endpoint создается автоматически в create_service_app
    # Префикс сервиса: /agents
    response = await flows_client.get("/flows/health")
    assert response.status_code == 200
    print("✅ Agents service: UP")


@pytest.mark.asyncio
async def test_frontend_service_health(frontend_client):
    """Проверка что frontend сервис работает"""
    response = await frontend_client.get("/api/health")
    assert response.status_code == 200
    print("✅ Frontend service: UP")


@pytest.mark.asyncio
async def test_container_setup(container):
    """Проверка что DI контейнер настроен корректно"""
    assert container.flow_repository is not None
    assert container.tool_repository is not None
    assert container.node_repository is not None
    assert container.company_repository is not None
    assert container.user_repository is not None
    assert container.subdomain_repository is not None
    print("✅ Container: OK")


@pytest.mark.asyncio
async def test_redis_connection(container):
    """Проверка подключения к Redis"""
    redis = container.redis_client
    
    # Простой ping
    await redis.set("test_key", "test_value")
    value = await redis.get("test_key")
    
    assert value == "test_value"
    
    await redis.delete("test_key")
    print("✅ Redis: Connected")


@pytest.mark.asyncio
async def test_registry_file_exists():
    """Проверка что registry.yaml существует и корректен"""
    from pathlib import Path
    import yaml
    
    registry_path = Path(__file__).parent.parent.parent.parent / "apps" / "flows" / "registry.yaml"
    
    assert registry_path.exists(), f"Registry не найден: {registry_path}"
    
    with open(registry_path, "r", encoding="utf-8") as f:
        registry = yaml.safe_load(f)
    
    assert "flows" in registry, "Registry должен содержать секцию flows"
    assert "tools" in registry, "Registry должен содержать секцию tools"
    assert "defaults" in registry, "Registry должен содержать секцию defaults"
    
    flows = registry["flows"]
    public_flows = [f for f in flows if isinstance(f, dict) and f.get("public")]
    
    assert len(public_flows) > 0, "Должен быть хотя бы один public flow"
    
    print(f"✅ Registry: OK ({len(flows)} flows, {len(public_flows)} public)")


@pytest.mark.asyncio
async def test_auth_token_creation(auth_token):
    """Проверка создания auth токена"""
    assert auth_token is not None
    assert len(auth_token) > 0
    print(f"✅ Auth token: Created")


@pytest.mark.asyncio  
async def test_company_api_endpoint_exists(flows_client):
    """Проверка что endpoint /company/init зарегистрирован"""
    # Запрос без тела должен вернуть 422 (validation error), а не 404
    response = await flows_client.post("/flows/api/v1/company/init")
    
    # 422 = endpoint существует, но запрос некорректен
    # 404 = endpoint не найден
    assert response.status_code != 404, "Endpoint /company/init не зарегистрирован"
    
    print("✅ Company init endpoint: Registered")


@pytest.mark.asyncio
async def test_service_client_available(container):
    """Проверка что ServiceClient доступен через контейнер"""
    from core.clients.service_client import ServiceClient
    
    client = container.service_client
    assert isinstance(client, ServiceClient)
    
    # Проверяем что это один и тот же экземпляр (кэширование через @lazy)
    client2 = container.service_client
    assert client is client2
    
    print("✅ ServiceClient: Available")

