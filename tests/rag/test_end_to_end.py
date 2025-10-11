"""
End-to-end тесты RAG системы с flow и агентами.
Проверяют полный workflow от конфигурации до использования.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, ANY

from app.flows.knowledge_bot_flow import knowledge_bot_flow
from app.models import AgentConfig, FlowConfig
from app.models.rag_models import AgentRAGConfig, RAGSearchResult, RAGDocument
from unittest.mock import AsyncMock


class TestFlowToAgentRAGConfig:
    """Тесты передачи RAG конфигурации из flow в агента"""
    
    @pytest.mark.asyncio
    async def test_flow_config_accessible_by_tools(self):
        """Тест что tools могут получить RAG конфигурацию из flow"""
        from app.tools.rag_tools import _get_rag_config_from_context
        
        mock_context = MagicMock()
        mock_context.flow_config = knowledge_bot_flow
        mock_context.agent_config = None
        
        rag_config = _get_rag_config_from_context(mock_context)
        
        assert rag_config is not None
        assert rag_config.enabled is True
        assert rag_config.namespace_scope == "company"
    
    @pytest.mark.asyncio
    async def test_agent_config_override_flow(self):
        """Тест что агент может переопределить RAG конфигурацию flow"""
        from app.tools.rag_tools import _get_rag_config_from_context
        
        mock_context = MagicMock()
        mock_context.flow_config = knowledge_bot_flow
        
        agent_rag = AgentRAGConfig(
            enabled=True,
            namespace_scope="flow",
            search_scopes=["flow"]
        )
        
        mock_agent_config = MagicMock()
        mock_agent_config.rag_config = agent_rag
        mock_context.agent_config = mock_agent_config
        
        rag_config = _get_rag_config_from_context(mock_context)
        
        assert rag_config.namespace_scope == "flow"
        assert rag_config.search_scopes == ["flow"]


class TestEndToEndRAGWorkflow:
    """End-to-end тесты полного workflow RAG"""
    
    @pytest.mark.asyncio
    async def test_complete_workflow_with_mocks(self):
        """
        Тест полного workflow:
        1. Flow с RAG конфигурацией
        2. Агент с RAG tools
        3. Загрузка документа
        4. Поиск информации
        """
        from app.tools.rag_tools import search_knowledge_base, upload_document_to_knowledge_base
        
        mock_context = MagicMock()
        mock_context.flow_config = knowledge_bot_flow
        mock_context.active_company.company_id = "test_company"
        mock_context.session_id = "session_123"
        mock_context.user.user_id = "user_456"
        
        mock_agent_config = MagicMock()
        mock_agent_config.agent_id = "knowledge_bot"
        mock_agent_config.rag_config = None
        mock_context.agent_config = mock_agent_config
        
        mock_get_ns = AsyncMock(return_value="mock_ns_id")
        
        mock_storage = AsyncMock()
        mock_storage.get = AsyncMock(return_value='{"s3_key": "test.pdf", "original_name": "test.pdf"}')
        
        mock_rag_provider = AsyncMock()
        mock_rag_provider.upload_document_from_s3 = AsyncMock(return_value=RAGDocument(
            document_id="doc_123",
            name="test.pdf",
            namespace="company_test_company",
            status="processing"
        ))
        mock_rag_provider.search_multiple_namespaces = AsyncMock(return_value={
            "company_test_company": [
                RAGSearchResult(
                    content="Найденная информация",
                    score=0.95,
                    document_id="doc_123",
                    document_name="test.pdf",
                    namespace="company_test_company",
                    metadata={}
                )
            ]
        })
        
        # Создаем мок FileRecord
        from app.models import FileRecord, FileStatus
        mock_file_record = FileRecord(
            file_id="file_123",
            provider="vkcloud",
            original_name="test.pdf",
            s3_key="test.pdf",
            s3_bucket="vkbucket",
            content_type="application/pdf",
            file_size=1024,
            status=FileStatus.UPLOADED
        )
        
        mock_file_processor = AsyncMock()
        mock_file_processor.get_file_record = AsyncMock(return_value=mock_file_record)
        
        with patch("app.tools.rag_tools.get_context", return_value=mock_context):
            with patch("app.tools.rag_tools.get_default_file_processor", return_value=mock_file_processor):
                with patch("app.tools.rag_tools.get_default_rag_provider", return_value=mock_rag_provider):
                    with patch("app.tools.rag_tools.get_or_create_namespace", new=mock_get_ns):
                        upload_result = await upload_document_to_knowledge_base.ainvoke(
                            {"file_id": "file_123", "description": "Test"},
                            config={}
                        )
                        
                        assert "успешно добавлен" in upload_result
                        assert "test.pdf" in upload_result
                        
                        search_result = await search_knowledge_base.ainvoke(
                            {"query": "test query"},
                            config={}
                        )
                        
                        assert "Найдено" in search_result
                        assert "test.pdf" in search_result
                        assert "0.95" in search_result
        
        mock_rag_provider.upload_document_from_s3.assert_called_once()
        upload_call = mock_rag_provider.upload_document_from_s3.call_args
        assert upload_call[1]["s3_key"] == "test.pdf"
        
        mock_rag_provider.search_multiple_namespaces.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_agent_scope_isolation(self):
        """Тест изоляции данных по скоупам flow"""
        from app.tools.rag_tools import upload_document_to_knowledge_base
        
        mock_get_ns = AsyncMock(return_value="mock_ns_id")
        mock_context = MagicMock()
        
        agent_rag = AgentRAGConfig(
            enabled=True,
            namespace_scope="flow",
            search_scopes=["flow"]
        )
        
        mock_flow = MagicMock()
        mock_flow.flow_id = "test_flow"
        mock_flow.rag_config = agent_rag
        mock_context.flow_config = mock_flow
        
        mock_context.active_company.company_id = "company_123"
        mock_context.user.user_id = "user_789"
        
        mock_agent_config = MagicMock()
        mock_agent_config.agent_id = "agent_456"
        mock_agent_config.rag_config = None
        mock_context.agent_config = mock_agent_config
        
        from app.models import FileRecord, FileStatus
        mock_file_record = FileRecord(
            file_id="file_123",
            provider="vkcloud",
            original_name="doc.pdf",
            s3_key="doc.pdf",
            s3_bucket="vkbucket",
            content_type="application/pdf",
            file_size=1024,
            status=FileStatus.UPLOADED
        )
        
        mock_file_processor = AsyncMock()
        mock_file_processor.get_file_record = AsyncMock(return_value=mock_file_record)
        
        mock_rag_provider = AsyncMock()
        mock_rag_provider.upload_document_from_s3 = AsyncMock(return_value=RAGDocument(
            document_id="doc_123",
            name="doc.pdf",
            namespace="mock_ns_id",
            status="processing"
        ))
        
        with patch("app.tools.rag_tools.get_context", return_value=mock_context):
            with patch("app.tools.rag_tools.get_default_file_processor", return_value=mock_file_processor):
                with patch("app.tools.rag_tools.get_default_rag_provider", return_value=mock_rag_provider):
                    with patch("app.tools.rag_tools.get_or_create_namespace", new=mock_get_ns):
                        result = await upload_document_to_knowledge_base.ainvoke(
                            {"file_id": "file_123"},
                            config={}
                        )
        
        assert "базу текущего flow" in result or "базу" in result
        
        mock_rag_provider.upload_document_from_s3.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_session_scope_isolation(self):
        """Тест изоляции данных по сессиям"""
        from app.tools.rag_tools import upload_document_to_knowledge_base
        
        mock_context = MagicMock()
        
        session_rag = AgentRAGConfig(
            enabled=True,
            namespace_scope="session",
            search_scopes=["session"]
        )
        
        mock_flow = MagicMock()
        mock_flow.rag_config = session_rag
        mock_context.flow_config = mock_flow
        
        mock_context.active_company.company_id = "company_123"
        mock_context.session_id = "session_xyz"
        mock_context.user.user_id = "user_789"
        
        mock_agent_config = MagicMock()
        mock_agent_config.agent_id = "agent_456"
        mock_agent_config.rag_config = None
        mock_context.agent_config = mock_agent_config
        
        from app.models import FileRecord, FileStatus
        mock_file_record = FileRecord(
            file_id="file_123",
            provider="vkcloud",
            original_name="doc.pdf",
            s3_key="doc.pdf",
            s3_bucket="vkbucket",
            content_type="application/pdf",
            file_size=1024,
            status=FileStatus.UPLOADED
        )
        
        mock_file_processor = AsyncMock()
        mock_file_processor.get_file_record = AsyncMock(return_value=mock_file_record)
        
        mock_rag_provider = AsyncMock()
        mock_rag_provider.upload_document_from_s3 = AsyncMock(return_value=RAGDocument(
            document_id="doc_session",
            name="doc.pdf",
            namespace="session_session_xyz",
            status="processing"
        ))
        
        mock_get_ns = AsyncMock(return_value="mock_ns_id")
        
        with patch("app.tools.rag_tools.get_context", return_value=mock_context):
            with patch("app.tools.rag_tools.get_default_file_processor", return_value=mock_file_processor):
                with patch("app.tools.rag_tools.get_default_rag_provider", return_value=mock_rag_provider):
                    with patch("app.tools.rag_tools.get_or_create_namespace", new=mock_get_ns):
                        result = await upload_document_to_knowledge_base.ainvoke(
                            {"file_id": "file_123"},
                            config={}
                        )
        
        assert "базу текущей сессии" in result
        
        mock_rag_provider.upload_document_from_s3.assert_called_once()

