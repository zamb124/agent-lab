"""
End-to-end тесты RAG системы с flow и агентами.
"""

import pytest

from apps.agents.models import FlowConfig
from core.rag.models import AgentRAGConfig


class TestFlowToAgentRAGConfig:
    """Тесты передачи RAG конфигурации из flow в агента"""
    
    def test_flow_config_accessible_by_tools(self, test_context):
        """Тест что tools могут получить RAG конфигурацию из flow"""
        from apps.agents.tools.misc.rag_tools import _get_rag_config_from_context
        from apps.agents.flows.knowledge_bot_flow import knowledge_bot_flow
        
        test_context.flow_config = knowledge_bot_flow
        test_context.agent_config = None
        
        rag_config = _get_rag_config_from_context(test_context)
        
        assert rag_config is not None
        assert rag_config.enabled is True
        assert rag_config.namespace_scope == "company"
    
    def test_custom_flow_rag_config(self, test_context):
        """Тест кастомной RAG конфигурации flow"""
        from apps.agents.tools.misc.rag_tools import _get_rag_config_from_context
        
        flow_rag = AgentRAGConfig(
            enabled=True,
            namespace_scope="session",
            search_scopes=["session", "flow"]
        )
        
        test_context.flow_config = FlowConfig(
            flow_id="custom_flow",
            name="Custom Flow",
            entry_point_agent="test",
            source="test",
            rag_config=flow_rag
        )
        test_context.agent_config = None
        
        rag_config = _get_rag_config_from_context(test_context)
        
        assert rag_config.namespace_scope == "session"
        assert rag_config.search_scopes == ["session", "flow"]
