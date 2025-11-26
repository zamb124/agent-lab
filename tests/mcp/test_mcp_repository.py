"""
Юнит тесты для MCPServerRepository.
"""

import pytest
from apps.agents.models.mcp_models import MCPServerConfig, MCPTransportType


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
    success = await mcp_repo.set(sample_server_config)
    assert success is True
    
    retrieved = await mcp_repo.get("test_server")
    assert retrieved is not None
    assert retrieved.server_id == "test_server"
    assert retrieved.company_id == "test_company"
    assert retrieved.name == "Test MCP Server"
    assert retrieved.url == "https://mcp.example.com/mcp"


@pytest.mark.asyncio
async def test_get_nonexistent_server(mcp_repo):
    """Тест получения несуществующего сервера"""
    result = await mcp_repo.get("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_delete_server(mcp_repo, sample_server_config):
    """Тест удаления MCP сервера"""
    await mcp_repo.set(sample_server_config)
    
    retrieved = await mcp_repo.get("test_server")
    assert retrieved is not None
    
    success = await mcp_repo.delete("test_server")
    assert success is True
    
    retrieved = await mcp_repo.get("test_server")
    assert retrieved is None


@pytest.mark.asyncio
async def test_list_all_servers(mcp_repo, test_company):
    """Тест получения списка всех серверов компании"""
    import asyncio
    
    existing_servers = await mcp_repo.list_all(limit=1000)
    for server in existing_servers:
        await mcp_repo.delete(server.server_id)
    
    await asyncio.sleep(0.1)
    
    remaining_servers = await mcp_repo.list_all(limit=1000)
    assert len(remaining_servers) == 0, f"Остались серверы после очистки: {[s.server_id for s in remaining_servers]}"
    
    servers = [
        MCPServerConfig(
            server_id=f"server_{i}",
            company_id=test_company.company_id,
            name=f"Server {i}",
            url=f"https://mcp{i}.example.com/mcp"
        )
        for i in range(3)
    ]
    
    for server in servers:
        await mcp_repo.set(server)
    
    all_servers = await mcp_repo.list_all()
    assert len(all_servers) == 3
    
    server_ids = {s.server_id for s in all_servers}
    assert server_ids == {"server_0", "server_1", "server_2"}


@pytest.mark.asyncio
async def test_list_active_servers(mcp_repo, test_company):
    """Тест получения только активных серверов"""
    existing_servers = await mcp_repo.list_all(limit=1000)
    for server in existing_servers:
        await mcp_repo.delete(server.server_id)
    
    remaining_servers = await mcp_repo.list_all(limit=1000)
    assert len(remaining_servers) == 0, f"Остались серверы после очистки: {[s.server_id for s in remaining_servers]}"
    
    active_server = MCPServerConfig(
        server_id="active_server",
        company_id=test_company.company_id,
        name="Active Server",
        url="https://mcp1.example.com/mcp",
        is_active=True
    )
    
    inactive_server = MCPServerConfig(
        server_id="inactive_server",
        company_id=test_company.company_id,
        name="Inactive Server",
        url="https://mcp2.example.com/mcp",
        is_active=False
    )
    
    await mcp_repo.set(active_server)
    await mcp_repo.set(inactive_server)
    
    active_servers = await mcp_repo.list_active()
    assert len(active_servers) == 1
    assert active_servers[0].server_id == "active_server"


@pytest.mark.asyncio
async def test_company_isolation(mcp_repo, company_repo, subdomain_repo):
    """Тест изоляции между компаниями"""
    from core.context import set_context, Context
    from core.models import Company, User, UserStatus
    from core.db.repositories.subdomain_repository import SubdomainMapping
    
    company1 = Company(
        company_id="company_1",
        subdomain="company_1",
        name="Company 1",
        status="active"
    )
    await company_repo.set(company1)
    await subdomain_repo.set(SubdomainMapping(subdomain="company_1", company_id="company_1"))
    
    user1 = User(user_id="user1", name="User 1", status=UserStatus.ACTIVE, companies={"company_1": ["user"]}, active_company_id="company_1")
    context1 = Context(user=user1, platform="test", active_company=company1)
    set_context(context1)
    
    server1 = MCPServerConfig(
        server_id="server_1",
        company_id="company_1",
        name="Server 1",
        url="https://mcp1.example.com/mcp"
    )
    await mcp_repo.set(server1)
    
    company2 = Company(
        company_id="company_2",
        subdomain="company_2",
        name="Company 2",
        status="active"
    )
    await company_repo.set(company2)
    await subdomain_repo.set(SubdomainMapping(subdomain="company_2", company_id="company_2"))
    
    user2 = User(user_id="user2", name="User 2", status=UserStatus.ACTIVE, companies={"company_2": ["user"]}, active_company_id="company_2")
    context2 = Context(user=user2, platform="test", active_company=company2)
    set_context(context2)
    
    server2 = MCPServerConfig(
        server_id="server_2",
        company_id="company_2",
        name="Server 2",
        url="https://mcp2.example.com/mcp"
    )
    await mcp_repo.set(server2)
    
    set_context(context1)
    company1_servers = await mcp_repo.list_all()
    assert len(company1_servers) == 1, f"Company 1 должна видеть 1 сервер, видит: {len(company1_servers)}"
    assert company1_servers[0].server_id == "server_1"
    
    set_context(context2)
    company2_servers = await mcp_repo.list_all()
    assert len(company2_servers) == 1, f"Company 2 должна видеть 1 сервер, видит: {len(company2_servers)}"
    assert company2_servers[0].server_id == "server_2"
    
    set_context(context1)
    await mcp_repo.delete("server_1")
    await company_repo.delete("company_1")
    await subdomain_repo.delete("company_1")
    
    set_context(context2)
    await mcp_repo.delete("server_2")
    await company_repo.delete("company_2")
    await subdomain_repo.delete("company_2")


@pytest.mark.asyncio
async def test_update_server(mcp_repo, sample_server_config):
    """Тест обновления конфигурации сервера"""
    await mcp_repo.set(sample_server_config)
    
    sample_server_config.name = "Updated Name"
    sample_server_config.is_active = False
    await mcp_repo.set(sample_server_config)
    
    retrieved = await mcp_repo.get("test_server")
    assert retrieved.name == "Updated Name"
    assert retrieved.is_active is False
