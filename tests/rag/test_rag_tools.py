"""
Тесты для RAG инструментов для агентов.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.tools.rag_tools import (
    search_knowledge_base,
    upload_document_to_knowledge_base,
    list_documents_in_knowledge_base
)
from app.models.rag_models import RAGSearchResult, RAGDocument


@pytest.fixture
def mock_context():
    """Фикстура для мока контекста"""
    from app.models.rag_models import AgentRAGConfig
    
    context = MagicMock()
    context.session_id = "session_123"
    context.user.user_id = "user_456"
    context.active_company.company_id = "company_789"
    
    mock_agent_config = MagicMock()
    mock_agent_config.agent_id = "agent_001"
    mock_agent_config.rag_config = None
    context.agent_config = mock_agent_config
    
    mock_flow_config = MagicMock()
    mock_flow_config.flow_id = "test_flow"
    mock_flow_config.rag_config = AgentRAGConfig(
        enabled=True,
        namespace_scope="flow",
        search_scopes=["flow", "company"]
    )
    context.flow_config = mock_flow_config
    
    return context


@pytest.fixture
def mock_rag_provider():
    """Фикстура для мока RAG провайдера"""
    provider = AsyncMock()
    
    provider.search_multiple_namespaces = AsyncMock(return_value={
        "company_789_agent_agent_001": [
            RAGSearchResult(
                content="Информация из документа агента",
                score=0.95,
                document_id="doc1",
                document_name="agent_doc.pdf",
                namespace="company_789_agent_agent_001",
                metadata={}
            )
        ],
        "company_789": [
            RAGSearchResult(
                content="Информация из общего документа",
                score=0.85,
                document_id="doc2",
                document_name="company_doc.txt",
                namespace="company_789",
                metadata={}
            )
        ]
    })
    
    provider.upload_document_from_s3 = AsyncMock(return_value=RAGDocument(
        document_id="new_doc_123",
        name="uploaded_file.pdf",
        namespace="company_789_agent_agent_001",
        status="processing"
    ))
    
    provider.list_documents = AsyncMock(return_value=[
        RAGDocument(
            document_id="doc1",
            name="document1.pdf",
            namespace="company_789_agent_agent_001",
            status="ready",
            created_at="2025-01-01T00:00:00Z"
        ),
        RAGDocument(
            document_id="doc2",
            name="document2.txt",
            namespace="company_789_agent_agent_001",
            status="processing",
            created_at="2025-01-02T00:00:00Z"
        )
    ])
    
    return provider


class TestSearchKnowledgeBase:
    """Тесты для инструмента поиска в базе знаний"""
    
    @pytest.mark.asyncio
    async def test_search_rag_disabled(self, mock_context, mock_rag_provider):
        """Тест когда RAG отключен"""
        mock_context.flow_config.rag_config = None
        
        with patch("app.tools.rag_tools.get_context", return_value=mock_context):
            with patch("app.tools.rag_tools.get_default_rag_provider", return_value=mock_rag_provider):
                result = await search_knowledge_base.ainvoke(
                    {"query": "test query"},
                    config={}
                )
        
        assert result == "RAG не настроен для этого flow"
    
    @pytest.mark.asyncio
    async def test_search_success(self, mock_context, mock_rag_provider):
        """Тест успешного поиска"""
        mock_get_ns = AsyncMock(return_value="mock_ns_id")
        
        with patch("app.tools.rag_tools.get_context", return_value=mock_context):
            with patch("app.tools.rag_tools.get_default_rag_provider", return_value=mock_rag_provider):
                with patch("app.tools.rag_tools.get_or_create_namespace", new=mock_get_ns):
                    result = await search_knowledge_base.ainvoke(
                        {"query": "test query"},
                        config={}
                    )
        
        assert "Найдено 2 релевантных фрагментов" in result
        assert "agent_doc.pdf" in result
        assert "company_doc.txt" in result
        assert "релевантность: 0.95" in result
        
        mock_rag_provider.search_multiple_namespaces.assert_called_once()
        call_args = mock_rag_provider.search_multiple_namespaces.call_args
        
        assert call_args[1]["query"] == "test query"
        assert call_args[1]["limit"] == 5
    
    @pytest.mark.asyncio
    async def test_search_no_results(self, mock_context, mock_rag_provider):
        """Тест когда ничего не найдено"""
        mock_get_ns = AsyncMock(return_value="mock_ns_id")
        mock_rag_provider.search_multiple_namespaces = AsyncMock(return_value={
            "mock_ns_id": []
        })
        
        with patch("app.tools.rag_tools.get_context", return_value=mock_context):
            with patch("app.tools.rag_tools.get_default_rag_provider", return_value=mock_rag_provider):
                with patch("app.tools.rag_tools.get_or_create_namespace", new=mock_get_ns):
                    result = await search_knowledge_base.ainvoke(
                        {"query": "non existent"},
                        config={}
                    )
        
        assert "ничего не найдено" in result.lower()
    
    @pytest.mark.asyncio
    async def test_search_no_scopes_configured(self, mock_context, mock_rag_provider):
        """Тест когда не настроены скоупы"""
        from app.models.rag_models import AgentRAGConfig
        
        mock_context.flow_config.rag_config = AgentRAGConfig(
            enabled=True,
            namespace_scope="flow",
            search_scopes=[]
        )
        
        with patch("app.tools.rag_tools.get_context", return_value=mock_context):
            with patch("app.tools.rag_tools.get_default_rag_provider", return_value=mock_rag_provider):
                result = await search_knowledge_base.ainvoke(
                    {"query": "test"},
                    config={}
                )
        
        assert "Не настроены скоупы поиска" in result


class TestUploadDocumentToKnowledgeBase:
    """Тесты для инструмента загрузки документов"""
    
    @pytest.mark.asyncio
    async def test_upload_rag_disabled(self, mock_context, mock_rag_provider):
        """Тест когда RAG отключен"""
        mock_context.flow_config.rag_config = None
        
        with patch("app.tools.rag_tools.get_context", return_value=mock_context):
            with patch("app.tools.rag_tools.get_default_rag_provider", return_value=mock_rag_provider):
                result = await upload_document_to_knowledge_base.ainvoke(
                    {"file_id": "file_123"},
                    config={}
                )
        
        assert result == "RAG не настроен для этого flow"
    
    @pytest.mark.asyncio
    async def test_upload_file_not_found(self, mock_context):
        """Тест когда файл не найден"""
        mock_storage = AsyncMock()
        mock_storage.get = AsyncMock(return_value=None)
        
        with patch("app.tools.rag_tools.get_context", return_value=mock_context):
            with patch("app.core.storage.Storage", return_value=mock_storage):
                result = await upload_document_to_knowledge_base.ainvoke(
                    {"file_id": "nonexistent"},
                    config={}
                )
        
        assert "не найден" in result.lower()
    
    @pytest.mark.asyncio
    async def test_upload_success(self, mock_context, mock_rag_provider):
        """Тест успешной загрузки"""
        from app.models.file_models import FileRecord
        
        mock_get_ns = AsyncMock(return_value="mock_ns_id")
        
        mock_file_record = FileRecord(
            file_id="file_123",
            provider="yandex",
            original_name="document.pdf",
            s3_key="uploads/document.pdf",
            s3_bucket="test-bucket",
            content_type="application/pdf",
            file_size=1024
        )
        
        mock_file_processor = AsyncMock()
        mock_file_processor.get_file_record = AsyncMock(return_value=mock_file_record)
        
        with patch("app.tools.rag_tools.get_context", return_value=mock_context):
            with patch("app.tools.rag_tools.get_default_file_processor", return_value=mock_file_processor):
                with patch("app.tools.rag_tools.get_default_rag_provider", return_value=mock_rag_provider):
                    with patch("app.tools.rag_tools.get_or_create_namespace", new=mock_get_ns):
                        result = await upload_document_to_knowledge_base.ainvoke(
                            {"file_id": "file_123", "description": "Test doc"},
                            config={}
                        )
        
        assert "успешно добавлен" in result
        assert "new_doc_123" in result
        
        mock_rag_provider.upload_document_from_s3.assert_called_once()
        call_args = mock_rag_provider.upload_document_from_s3.call_args
        
        assert call_args[1]["s3_key"] == "uploads/document.pdf"
        assert call_args[1]["metadata"]["description"] == "Test doc"
    
    @pytest.mark.asyncio
    async def test_upload_to_company_scope(self, mock_context, mock_rag_provider):
        """Тест загрузки в скоуп компании"""
        from app.models.rag_models import AgentRAGConfig
        from app.models.file_models import FileRecord
        
        mock_get_ns = AsyncMock(return_value="mock_ns_id")
        mock_context.flow_config.flow_id = "test_flow"
        mock_context.flow_config.rag_config = AgentRAGConfig(
            enabled=True,
            namespace_scope="company",
            search_scopes=["company"]
        )
        
        mock_file_record = FileRecord(
            file_id="file_123",
            provider="yandex",
            original_name="doc.pdf",
            s3_key="doc.pdf",
            s3_bucket="test-bucket",
            content_type="application/pdf",
            file_size=1024
        )
        
        mock_file_processor = AsyncMock()
        mock_file_processor.get_file_record = AsyncMock(return_value=mock_file_record)
        
        with patch("app.tools.rag_tools.get_context", return_value=mock_context):
            with patch("app.tools.rag_tools.get_default_file_processor", return_value=mock_file_processor):
                with patch("app.tools.rag_tools.get_default_rag_provider", return_value=mock_rag_provider):
                    with patch("app.tools.rag_tools.get_or_create_namespace", new=mock_get_ns):
                        result = await upload_document_to_knowledge_base.ainvoke(
                            {"file_id": "file_123"},
                            config={}
                        )
        
        assert "общую базу компании" in result
        
        mock_rag_provider.upload_document_from_s3.assert_called_once()


class TestListDocumentsInKnowledgeBase:
    """Тесты для инструмента списка документов"""
    
    @pytest.mark.asyncio
    async def test_list_rag_disabled(self, mock_context, mock_rag_provider):
        """Тест когда RAG отключен"""
        mock_context.flow_config.rag_config = None
        
        with patch("app.tools.rag_tools.get_context", return_value=mock_context):
            with patch("app.tools.rag_tools.get_default_rag_provider", return_value=mock_rag_provider):
                result = await list_documents_in_knowledge_base.ainvoke({}, config={})
        
        assert result == "RAG не настроен для этого flow"
    
    @pytest.mark.asyncio
    async def test_list_empty(self, mock_context, mock_rag_provider):
        """Тест когда нет документов"""
        mock_get_ns = AsyncMock(return_value="mock_ns_id")
        mock_rag_provider.list_documents = AsyncMock(return_value=[])
        
        with patch("app.tools.rag_tools.get_context", return_value=mock_context):
            with patch("app.tools.rag_tools.get_default_rag_provider", return_value=mock_rag_provider):
                with patch("app.tools.rag_tools.get_or_create_namespace", new=mock_get_ns):
                    result = await list_documents_in_knowledge_base.ainvoke({}, config={})
        
        assert "пока нет документов" in result.lower()
    
    @pytest.mark.asyncio
    async def test_list_success(self, mock_context, mock_rag_provider):
        """Тест успешного получения списка"""
        mock_get_ns = AsyncMock(return_value="mock_ns_id")
        
        with patch("app.tools.rag_tools.get_context", return_value=mock_context):
            with patch("app.tools.rag_tools.get_default_rag_provider", return_value=mock_rag_provider):
                with patch("app.tools.rag_tools.get_or_create_namespace", new=mock_get_ns):
                    result = await list_documents_in_knowledge_base.ainvoke({}, config={})
        
        assert "Документы в базе знаний (2)" in result
        assert "document1.pdf" in result
        assert "document2.txt" in result
        assert "✅" in result
        assert "⏳" in result
        assert "doc1" in result
        assert "doc2" in result

