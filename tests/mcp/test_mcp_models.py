"""
Юнит тесты для MCP моделей.
"""

import pytest
from datetime import datetime, timezone
from app.models.mcp_models import MCPServerConfig, MCPTransportType
from app.models.core_models import CodeMode


def test_mcp_server_config_creation():
    """Тест создания MCPServerConfig"""
    config = MCPServerConfig(
        server_id="test_server",
        company_id="company_123",
        name="Test MCP Server",
        description="Test description",
        url="https://mcp.example.com/mcp",
        transport_type=MCPTransportType.HTTP,
        headers={"Authorization": "Bearer token"},
        timeout=30
    )
    
    assert config.server_id == "test_server"
    assert config.company_id == "company_123"
    assert config.name == "Test MCP Server"
    assert config.url == "https://mcp.example.com/mcp"
    assert config.transport_type == MCPTransportType.HTTP
    assert config.headers == {"Authorization": "Bearer token"}
    assert config.timeout == 30
    assert config.is_active is True
    assert config.auto_sync_tools is True
    assert config.cached_tools == []


def test_mcp_server_config_defaults():
    """Тест значений по умолчанию"""
    config = MCPServerConfig(
        server_id="test_server",
        company_id="company_123",
        name="Test Server",
        url="https://mcp.example.com/mcp"
    )
    
    assert config.transport_type == MCPTransportType.HTTP
    assert config.timeout == 30
    assert config.is_active is True
    assert config.auto_sync_tools is True
    assert config.headers == {}


def test_mcp_server_config_sse_transport():
    """Тест SSE транспорта"""
    config = MCPServerConfig(
        server_id="sse_server",
        company_id="company_123",
        name="SSE Server",
        url="https://mcp.example.com/mcp",
        transport_type=MCPTransportType.SSE
    )
    
    assert config.transport_type == MCPTransportType.SSE


def test_mcp_server_config_serialization():
    """Тест сериализации в JSON"""
    config = MCPServerConfig(
        server_id="test_server",
        company_id="company_123",
        name="Test Server",
        url="https://mcp.example.com/mcp",
        headers={"Authorization": "@var:api_key"}
    )
    
    json_str = config.model_dump_json()
    assert "test_server" in json_str
    assert "company_123" in json_str
    assert "@var:api_key" in json_str
    
    # Десериализация
    restored = MCPServerConfig.model_validate_json(json_str)
    assert restored.server_id == config.server_id
    assert restored.company_id == config.company_id
    assert restored.headers == config.headers


def test_code_mode_mcp_tool():
    """Тест нового CodeMode.MCP_TOOL"""
    assert CodeMode.MCP_TOOL == "mcp_tool"
    assert CodeMode.MCP_TOOL in [CodeMode.CODE_REFERENCE, CodeMode.INLINE_CODE, CodeMode.MCP_TOOL]

