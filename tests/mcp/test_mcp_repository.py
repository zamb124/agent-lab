"""
Юнит тесты для MCPServerRepository.
"""

import pytest
from app.models.mcp_models import MCPServerConfig, MCPTransportType
from app.db.repositories.mcp_repository import MCPServerRepository
from app.db.repositories.storage import Storage


@pytest.fixture
async def storage():
    """Фикстура для Storage"""
    storage = Storage()
    yield storage
    # Очистка после тестов
    keys = await storage.list_by_prefix("mcp_server:", limit=1000)
    for key in keys:
        await storage.delete(key)


@pytest.fixture
def mcp_repo(storage):
    """Фикстура для MCPServerRepository"""
    return MCPServerRepository(storage)


@pytest.fixture
def sample_server_config():
    """Фикстура с примером конфигурации сервера"""
    return MCPServerConfig(
        server_id="test_server",
        company_id="test_company",
        name="Test MCP Server",
        url="https://mcp.example.com/mcp",
        transport_type=MCPTransportType.HTTP
    )


@pytest.mark.asyncio
async def test_save_and_get_server(mcp_repo, sample_server_config):
    """Тест сохранения и получения MCP сервера"""
    # Сохраняем
    success = await mcp_repo.set(sample_server_config)
    assert success is True
    
    # Получаем
    retrieved = await mcp_repo.get("test_server", "test_company")
    assert retrieved is not None
    assert retrieved.server_id == "test_server"
    assert retrieved.company_id == "test_company"
    assert retrieved.name == "Test MCP Server"
    assert retrieved.url == "https://mcp.example.com/mcp"


@pytest.mark.asyncio
async def test_get_nonexistent_server(mcp_repo):
    """Тест получения несуществующего сервера"""
    result = await mcp_repo.get("nonexistent", "test_company")
    assert result is None


@pytest.mark.asyncio
async def test_delete_server(mcp_repo, sample_server_config):
    """Тест удаления MCP сервера"""
    # Сохраняем
    await mcp_repo.set(sample_server_config)
    
    # Проверяем что существует
    retrieved = await mcp_repo.get("test_server", "test_company")
    assert retrieved is not None
    
    # Удаляем
    success = await mcp_repo.delete("test_server", "test_company")
    assert success is True
    
    # Проверяем что удален
    retrieved = await mcp_repo.get("test_server", "test_company")
    assert retrieved is None


@pytest.mark.asyncio
async def test_list_all_servers(mcp_repo):
    """Тест получения списка всех серверов компании"""
    # Создаем несколько серверов
    servers = [
        MCPServerConfig(
            server_id=f"server_{i}",
            company_id="test_company",
            name=f"Server {i}",
            url=f"https://mcp{i}.example.com/mcp"
        )
        for i in range(3)
    ]
    
    for server in servers:
        await mcp_repo.set(server)
    
    # Получаем список
    all_servers = await mcp_repo.list_all(company_id="test_company")
    assert len(all_servers) == 3
    
    server_ids = {s.server_id for s in all_servers}
    assert server_ids == {"server_0", "server_1", "server_2"}


@pytest.mark.asyncio
async def test_list_active_servers(mcp_repo):
    """Тест получения только активных серверов"""
    # Создаем активный и неактивный серверы
    active_server = MCPServerConfig(
        server_id="active_server",
        company_id="test_company",
        name="Active Server",
        url="https://mcp1.example.com/mcp",
        is_active=True
    )
    
    inactive_server = MCPServerConfig(
        server_id="inactive_server",
        company_id="test_company",
        name="Inactive Server",
        url="https://mcp2.example.com/mcp",
        is_active=False
    )
    
    await mcp_repo.set(active_server)
    await mcp_repo.set(inactive_server)
    
    # Получаем только активные
    active_servers = await mcp_repo.list_active(company_id="test_company")
    assert len(active_servers) == 1
    assert active_servers[0].server_id == "active_server"


@pytest.mark.asyncio
async def test_company_isolation(mcp_repo):
    """Тест изоляции между компаниями"""
    # Создаем серверы для разных компаний
    server1 = MCPServerConfig(
        server_id="server_1",
        company_id="company_1",
        name="Server 1",
        url="https://mcp1.example.com/mcp"
    )
    
    server2 = MCPServerConfig(
        server_id="server_2",
        company_id="company_2",
        name="Server 2",
        url="https://mcp2.example.com/mcp"
    )
    
    await mcp_repo.set(server1)
    await mcp_repo.set(server2)
    
    # Проверяем что каждая компания видит только свои серверы
    company1_servers = await mcp_repo.list_all(company_id="company_1")
    assert len(company1_servers) == 1
    assert company1_servers[0].server_id == "server_1"
    
    company2_servers = await mcp_repo.list_all(company_id="company_2")
    assert len(company2_servers) == 1
    assert company2_servers[0].server_id == "server_2"


@pytest.mark.asyncio
async def test_update_server(mcp_repo, sample_server_config):
    """Тест обновления конфигурации сервера"""
    # Сохраняем
    await mcp_repo.set(sample_server_config)
    
    # Обновляем
    sample_server_config.name = "Updated Name"
    sample_server_config.is_active = False
    await mcp_repo.set(sample_server_config)
    
    # Проверяем обновление
    retrieved = await mcp_repo.get("test_server", "test_company")
    assert retrieved.name == "Updated Name"
    assert retrieved.is_active is False

