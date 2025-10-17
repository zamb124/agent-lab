"""
Тесты интеграции RAG с flow и агентами.
"""

import pytest

from app.flows.knowledge_bot_flow import knowledge_bot_flow
from app.agents.knowledge_bot.agent import KnowledgeBotAgent
from app.models.rag_models import AgentRAGConfig


class TestFlowRAGConfig:
    """Тесты RAG конфигурации во flow"""
    
    def test_flow_has_rag_config(self):
        """Тест что flow имеет RAG конфигурацию"""
        assert knowledge_bot_flow.rag_config is not None
        assert isinstance(knowledge_bot_flow.rag_config, AgentRAGConfig)
    
    def test_rag_config_enabled(self):
        """Тест что RAG включен"""
        assert knowledge_bot_flow.rag_config.enabled is True
    
    def test_rag_config_namespace_scope(self):
        """Тест настройки скоупа хранения"""
        assert knowledge_bot_flow.rag_config.namespace_scope == "company"
    
    def test_rag_config_search_scopes(self):
        """Тест настройки скоупов поиска"""
        assert "company" in knowledge_bot_flow.rag_config.search_scopes
        assert "flow" in knowledge_bot_flow.rag_config.search_scopes
    
    def test_rag_config_auto_index(self):
        """Тест настройки автоиндексации"""
        assert knowledge_bot_flow.rag_config.auto_index_messages is False


@pytest.mark.skip(reason="Требуют rag.enabled=true в конфиге")
class TestAgentRAGTools:
    """Тесты доступа агента к RAG tools"""
    
    def test_agent_has_rag_tools(self):
        """Тест что агент имеет RAG инструменты"""
        from app.tools.misc.rag_tools import (
            search_knowledge_base,
            upload_document_to_knowledge_base,
            list_documents_in_knowledge_base
        )
        
        agent = KnowledgeBotAgent
        
        assert search_knowledge_base in agent.tools
        assert upload_document_to_knowledge_base in agent.tools
        assert list_documents_in_knowledge_base in agent.tools
    
    def test_agent_prompt_mentions_rag(self):
        """Тест что промпт упоминает RAG возможности"""
        agent = KnowledgeBotAgent
        prompt = agent.prompt
        
        assert "знани" in prompt.lower()
        assert "search_knowledge_base" in prompt


class TestRAGConfigParsing:
    """Тесты парсинга RAG конфигурации из разных форматов"""
    
    def test_parse_from_dict(self):
        """Тест парсинга из словаря"""
        from app.models import FlowConfig
        
        flow = FlowConfig(
            name="Test",
            entry_point_agent="test.agent",
            rag_config={
                "enabled": True,
                "namespace_scope": "flow",
                "search_scopes": ["flow"]
            }
        )
        
        assert flow.rag_config is not None
        assert flow.rag_config.enabled is True
        assert flow.rag_config.namespace_scope == "flow"
    
    def test_parse_from_json_string_storage(self):
        """Тест парсинга из JSON строки (как из БД)"""
        from app.models import FlowConfig
        import json
        
        flow_data = {
            "name": "Test",
            "entry_point_agent": "test.agent",
            "rag_config": {
                "enabled": True,
                "namespace_scope": "company",
                "search_scopes": ["company", "session"]
            }
        }
        
        flow_json = json.dumps(flow_data)
        flow = FlowConfig.model_validate_json(flow_json)
        
        assert flow.rag_config is not None
        assert flow.rag_config.enabled is True
        assert "company" in flow.rag_config.search_scopes
    
    def test_default_rag_config(self):
        """Тест что RAG включен по умолчанию"""
        from app.models import FlowConfig

        flow = FlowConfig(
            name="Test",
            entry_point_agent="test.agent"
        )

        assert flow.rag_config is not None
        assert flow.rag_config.enabled is True
        assert flow.rag_config.namespace_scope == "flow"
        assert flow.rag_config.search_scopes == ["flow"]


class TestRAGNamespaceGeneration:
    """Тесты генерации namespace ID"""
    
    def test_company_namespace(self):
        """Тест генерации namespace для компании"""
        company_id = "test_company_123"
        namespace_id = f"company_{company_id}"
        
        assert namespace_id == "company_test_company_123"
    
    def test_agent_namespace(self):
        """Тест генерации namespace для агента"""
        company_id = "test_company_123"
        agent_id = "support_agent"
        namespace_id = f"company_{company_id}_agent_{agent_id}"
        
        assert namespace_id == "company_test_company_123_agent_support_agent"
    
    def test_session_namespace(self):
        """Тест генерации namespace для сессии"""
        session_id = "session_abc123"
        namespace_id = f"session_{session_id}"
        
        assert namespace_id == "session_session_abc123"

